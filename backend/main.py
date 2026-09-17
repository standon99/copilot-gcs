import asyncio
import copy
import hashlib
import json
import math
import multiprocessing as mp
import os
import queue
import secrets
import socket
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import HOME, PROFILES, ROOT, RUNTIME
from .fence import FenceEdit, fence_changes, fence_snapshot
from .gateway import gateway_main
from .interaction import parameter_context, validate_edits
from .lab import CATALOG, score
from .metadata import FIRMWARE_COMMIT, metadata, validate_parameter
from .navigation import navigation_cue
from .planning import Draft, Intent, apply_patch, check, revise
from .provider import Provider, sandbox_command
from .settings import DEFAULT_PROMPTS, Preferences, credential_for, settings
from .store import Store
from .telemetry import Telemetry, finite

ctx = mp.get_context("spawn")
store = Store()
provider = Provider()
vehicles = {}
jobs = {}
sessions = {}
tasks = set()
launch_lock = asyncio.Lock()


def background(coro):
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def event(vid, kind, payload):
    return store.event(vid, kind, finite(payload))


class Vehicle:
    def __init__(self, ident, profile, endpoint, owned=False, sim=None):
        self.id = ident
        self.profile = profile
        self.endpoint = endpoint
        self.owned = owned
        self.sim = sim
        self.folder = RUNTIME / ident
        self.folder.mkdir(parents=True, exist_ok=True)
        self.events = ctx.Queue(4000)
        self.commands = ctx.Queue(30)
        self.results = ctx.Queue()
        self.process = ctx.Process(
            target=gateway_main,
            args=(endpoint, profile, self.events, self.commands, self.results, str(self.folder)),
            daemon=True,
        )
        self.telemetry = Telemetry(ident, profile)
        self.params = {}
        self.error = None
        self.lease = None
        self.lease_until = 0
        self.draft = Draft().model_dump()
        self.revisions = [copy.deepcopy(self.draft)]
        self.review = None
        self.active = None
        self.intent_proposal = None
        self.monitor_enabled = True
        self.monitor_track = "operational"
        self.assessment = None
        self.monitor_status = "waiting"
        self.next_monitor = time.time() + settings.value.monitor_interval
        self.inference = None
        self.chat = []
        self.predictions = []
        self.fault_restore = {}
        self.fence_busy = False
        self.parameter_apply_busy = False
        self.parameter_proposals = []
        self.trial = None
        self.trial_task = None
        self.closed = False
        self.record = (self.folder / "telemetry.jsonl").open("a")
        self.record_bytes = 0
        self.recording = True
        self.recording_error = None
        self.process.start()

    def snapshot(self):
        return {
            **self.telemetry.snapshot(),
            "name": self.profile.capitalize() + " · " + self.id[:6],
            "owned": self.owned,
            "endpoint": self.endpoint,
            "error": self.error,
            "parameters": len(self.params),
            "draft_revision": self.draft["revision"],
            "active_revision": self.active["revision"] if self.active else None,
            "fence": fence_snapshot(self.params),
            "navigation_cue": navigation_cue(self.telemetry, self.active),
            "rules": self.telemetry.rules(self.active),
            "assessment": self.assessment,
            "assessment_stale": self.assessment is None
            or time.time() - self.assessment["observed_at"] > 45,
            "monitor_status": self.monitor_status,
            "monitor_enabled": self.monitor_enabled,
            "monitor_effective": self.monitor_enabled and settings.value.monitor_enabled,
            "next_monitor_at": self.next_monitor,
            "monitor_track": self.monitor_track,
            "lease_remaining": max(0, round(self.lease_until - time.time())),
            "recording": self.recording,
            "recording_error": self.recording_error,
            "trial": {k: v for k, v in self.trial.items() if k not in ("scenario", "restore")}
            if self.trial and self.trial["state"] != "complete"
            else self.trial,
        }

    async def stop(self):
        self.closed = True
        pending = [t for t in (self.inference, self.trial_task) if t and not t.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for job in jobs.values():
            if job["vehicle"] == self.id and job["status"] == "pending":
                job.update(status="failed", error="Session stopped; operation completion unknown")
                event(self.id, "command_result", public_job(job))
        try:
            self.commands.put_nowait({"action": "shutdown"})
        except queue.Full:
            pass
        await asyncio.to_thread(self.process.join, 2)
        if self.process.is_alive():
            self.process.terminate()
            await asyncio.to_thread(self.process.join, 2)
        if self.sim and self.sim.poll() is None:
            self.sim.terminate()
            try:
                await asyncio.to_thread(self.sim.wait, timeout=3)
            except subprocess.TimeoutExpired:
                self.sim.kill()
        self.record.close()
        for q in (self.events, self.commands, self.results):
            q.close()
            q.cancel_join_thread()
        self.events = self.commands = self.results = None
        if not self.process.is_alive():
            self.process.close()


def vehicle(vid):
    if vid not in vehicles:
        raise HTTPException(404, "Vehicle session not found")
    return vehicles[vid]


def authorize(v, request):
    sid = request.cookies.get("copilot_session")
    if not v.owned:
        raise HTTPException(403, "External connections are read-only in this SITL release")
    if v.lease != sid or v.lease_until < time.time():
        raise HTTPException(409, "Claim control of this vehicle before sending a command")
    s = v.telemetry.snapshot()
    if s["heartbeat_age"] is None or s["heartbeat_age"] > 3:
        raise HTTPException(409, "Heartbeat is stale")
    h = v.telemetry.latest.get("HEARTBEAT", {}).get("data", {})
    if h.get("type") != PROFILES[v.profile]["type"]:
        raise HTTPException(409, "Detected vehicle profile does not match connection profile")
    if v.error:
        raise HTTPException(409, v.error)
    v.lease_until = time.time() + 30


def submit(v, action, args=None, request_id=None):
    # Idempotency is scoped to connection, action and exact arguments.
    signature = hashlib.sha256(
        json.dumps([v.id, action, args], sort_keys=True).encode()
    ).hexdigest()
    if request_id:
        for job in jobs.values():
            if job.get("request_id") == request_id and job["vehicle"] == v.id:
                if job["signature"] != signature:
                    raise HTTPException(409, "Idempotency key reused with different action")
                return job
    jid = uuid.uuid4().hex
    j = {
        "id": jid,
        "vehicle": v.id,
        "action": action,
        "status": "pending",
        "created_at": time.time(),
        "request_id": request_id,
        "signature": signature,
    }
    try:
        v.commands.put_nowait(
            {
                "job": jid,
                "action": action,
                "args": args or {},
                "epoch": v.telemetry.epoch,
                "expires_at": time.time() + 30,
            }
        )
    except queue.Full:
        raise HTTPException(429, "Vehicle command queue is full")
    jobs[jid] = j
    event(v.id, "command_submitted", {"job": jid, "action": action, "args": args or {}})
    return j


async def await_job(j, timeout=60):
    deadline = time.monotonic() + timeout
    while j["status"] == "pending" and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    if j["status"] == "pending":
        raise RuntimeError("Job deadline expired; inspect its final state before retrying")
    if j["status"] == "failed":
        raise RuntimeError(j.get("error", "Operation failed"))
    return j


async def monitor(v):
    observation = v.telemetry.observations(v.active, v.monitor_track)
    v.monitor_status = "assessing"
    try:
        result = await provider.monitor(observation)
        if v.closed or observation["epoch"] != v.telemetry.epoch:
            return
        result["track"] = v.monitor_track
        v.assessment = result
        v.predictions.append(result)
        v.predictions = v.predictions[-1000:]
        v.monitor_status = "available"
        event(v.id, "assessment", result)
        # Store exactly what the model saw for audit, never credentials or private truth.
        with (v.folder / "inference.jsonl").open("a") as f:
            f.write(json.dumps({"observations": observation, "prediction": result}) + "\n")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        v.monitor_status = "unavailable: " + str(exc)[:180]
        event(v.id, "inference_error", {"error": str(exc)[:180]})
        try:
            with (v.folder / "inference.jsonl").open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "observations": observation,
                            "failed_at": time.time(),
                            "error": str(exc)[:300],
                            "rejected_outputs": getattr(exc, "outputs", []),
                        }
                    )
                    + "\n"
                )
        except OSError:
            v.recording_error = "Inference audit recording failed"
    finally:
        v.next_monitor = time.time() + settings.value.monitor_interval
        v.inference = None


async def pump():
    while True:
        for v in list(vehicles.values()):
            if v.closed:
                continue
            for _ in range(500):
                try:
                    e = v.events.get_nowait()
                except queue.Empty:
                    break
                if e["kind"] == "message":
                    if e["type"] == "PARAM_VALUE":
                        v.params[e["data"]["name"]] = e["data"]
                    else:
                        v.telemetry.ingest(e)
                        if v.recording:
                            line = json.dumps(finite(e)) + "\n"
                            try:
                                v.record.write(line)
                                v.record_bytes += len(line)
                            except OSError:
                                v.recording = False
                                v.recording_error = (
                                    "Normalized recording failed; live telemetry continues"
                                )
                            if v.record_bytes > 256 * 1024 * 1024:
                                v.recording = False
                                event(
                                    v.id,
                                    "recording_stopped",
                                    {"reason": "256 MiB normalized recording quota reached"},
                                )
                elif e["kind"] == "error":
                    v.error = e["error"]
                    event(v.id, "gateway_error", e)
                elif e["kind"] == "recording_error":
                    v.recording_error = e["error"]
                elif e["kind"] == "reboot":
                    v.active = None
                    v.review = None
                    v.params.clear()
                    event(v.id, "reboot", e)
            for _ in range(50):
                try:
                    result = v.results.get_nowait()
                except queue.Empty:
                    break
                if result["job"] in jobs:
                    j = jobs[result["job"]]
                    j.update(result)
                    j["completed_at"] = time.time()
                    event(v.id, "command_result", public_job(j))
                    if j["action"] == "mission_upload" and j["status"] == "verified":
                        v.active = j.pop("_snapshot")
                        v.active["home"] = j.pop("_home")
                        store.put("active:" + v.id, v.active)
            if not v.process.is_alive():
                if not v.error:
                    v.error = "Gateway process exited; restart the session"
                for j in jobs.values():
                    if j["vehicle"] == v.id and j["status"] == "pending":
                        j.update(
                            status="failed", error="Gateway exited; operation completion unknown"
                        )
            if (
                v.monitor_enabled
                and settings.value.monitor_enabled
                and not v.inference
                and time.time() >= v.next_monitor
                and v.telemetry.latest
            ):
                v.inference = background(monitor(v))
            if v.recording:
                try:
                    v.record.flush()
                except OSError:
                    v.recording = False
                    v.recording_error = "Recording flush failed"
        await asyncio.sleep(0.05)


@asynccontextmanager
async def lifespan(app):
    worker = asyncio.create_task(pump())
    yield
    worker.cancel()
    for task in list(tasks):
        task.cancel()
    for v in list(vehicles.values()):
        await v.stop()
    await asyncio.gather(worker, *list(tasks), return_exceptions=True)


app = FastAPI(title="ArduPilot Safety Copilot", lifespan=lifespan)


def origin_valid(origin, host):
    if not origin:
        return True
    parsed = urlparse(origin)
    return parsed.scheme in ("http", "https") and parsed.netloc == host


@app.middleware("http")
async def local_security(request, call_next):
    host = request.headers.get("host", "")
    if host.split(":")[0] not in ("localhost", "127.0.0.1", "testserver"):
        return JSONResponse({"detail": "Loopback Host required"}, 403)
    if not origin_valid(request.headers.get("origin"), host):
        return JSONResponse({"detail": "Cross-origin requests are not permitted"}, 403)
    if request.url.path.startswith("/api/") and request.url.path not in (
        "/api/bootstrap",
        "/api/health",
    ):
        if request.cookies.get("copilot_session") not in sessions:
            return JSONResponse({"detail": "Open the local application first"}, 401)
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and request.headers.get("x-copilot-request") != "1"
    ):
        return JSONResponse({"detail": "Local request header required"}, 403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; connect-src 'self' ws://127.0.0.1:* ws://localhost:* https://*.arcgisonline.com https://*.openstreetmap.org; worker-src 'self' blob:; frame-ancestors 'none'"
    )
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "vehicles": len(vehicles)}


@app.get("/api/bootstrap")
async def bootstrap(request: Request):
    sid = request.cookies.get("copilot_session")
    if sid not in sessions:
        sid = secrets.token_urlsafe(32)
        sessions[sid] = time.time()
    response = JSONResponse(
        {
            "profiles": PROFILES,
            "model": settings.value.model,
            "provider": settings.value.base_url,
            "configured": bool(credential_for(settings.value.base_url))
            or settings.value.base_url != "https://ollama.com/v1",
            "filesystem_isolated": sandbox_command()[1],
            "home": HOME,
            "monitor_interval": settings.value.monitor_interval,
            "monitor_enabled": settings.value.monitor_enabled,
            "capabilities": {
                "owned_sitl_write": True,
                "external_write": False,
                "terrain": False,
                "physical_vehicle_validated": False,
            },
            "scenarios": {
                k: {"label": v["label"], "profiles": v["profiles"]} for k, v in CATALOG.items()
            },
        }
    )
    response.set_cookie("copilot_session", sid, httponly=True, samesite="strict", max_age=86400)
    return response


@app.get("/api/vehicles")
async def vehicle_list():
    return [v.snapshot() for v in vehicles.values()]


@app.get("/api/settings")
async def read_settings():
    return {
        "preferences": settings.get(),
        "defaults": DEFAULT_PROMPTS,
        "credential_attached": bool(credential_for(settings.value.base_url)),
    }


@app.put("/api/settings")
async def save_settings(body: Preferences):
    if any(v.trial_task and not v.trial_task.done() for v in vehicles.values()):
        raise HTTPException(
            409, "Finish or cancel active trials before changing inference settings"
        )
    try:
        settings.save(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    pending = [v.inference for v in vehicles.values() if v.inference and not v.inference.done()]
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for v in vehicles.values():
        v.next_monitor = time.time() + settings.value.monitor_interval
    event(
        None,
        "inference_settings_saved",
        {
            "revision": settings.value.revision,
            "model": settings.value.model,
            "monitor_enabled": settings.value.monitor_enabled,
        },
    )
    return await read_settings()


@app.post("/api/settings/models")
async def provider_models(body: Preferences):
    try:
        models, _ = await provider.complete("", {}, options=body.model_dump(), operation="models")
        return {"models": models}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.post("/api/settings/test")
async def provider_test(body: Preferences):
    try:
        result, meta = await provider.complete(
            'Return only JSON {"ok":true}. This is a connection test.',
            {},
            options=body.model_dump(),
        )
        if result.get("ok") is not True:
            raise ValueError("Model responded but did not return the required JSON")
        return {"ok": True, **meta}
    except Exception as exc:
        raise HTTPException(502, str(exc))


class Launch(BaseModel):
    profile: str


@app.post("/api/sitl")
async def launch(body: Launch):
    async with launch_lock:
        return await launch_owned(body)


async def launch_owned(body: Launch):
    if body.profile not in PROFILES:
        raise HTTPException(422, "Unknown profile")
    if len(vehicles) >= 6:
        raise HTTPException(409, "Maximum six simultaneous sessions")
    p = PROFILES[body.profile]
    binary = ROOT / "ardupilot/build/sitl/bin" / p["binary"]
    if not binary.exists():
        raise HTTPException(409, "SITL binary missing; run scripts/build-sitl.sh")
    ident = uuid.uuid4().hex[:12]
    folder = RUNTIME / ident
    folder.mkdir()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    rc_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rc_socket.bind(("127.0.0.1", 0))
    rc_port = rc_socket.getsockname()[1]
    rc_socket.close()
    env = {
        k: v
        for k, v in os.environ.items()
        if not any(s in k for s in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    }
    output = (folder / "sitl.log").open("wb")
    used_slots = {getattr(v, "spawn_slot", None) for v in vehicles.values()}
    slot = next(i for i in range(6) if i not in used_slots)
    spawn_home = {
        **HOME,
        "lat": HOME["lat"] + slot * 0.00018,
        "lon": HOME["lon"] + (slot % 2) * 0.00022,
    }
    sim = subprocess.Popen(
        [
            str(binary),
            "--model",
            p["model"],
            "--speedup",
            "1",
            "--home",
            f"{spawn_home['lat']},{spawn_home['lon']},{spawn_home['alt']},353",
            "--defaults",
            str(ROOT / "ardupilot" / p["defaults"]),
            "--serial0",
            f"tcp:{port}:wait",
            "--serial1",
            "none",
            "--serial2",
            "none",
            "--base-port",
            str(port),
            "--rc-in-port",
            str(rc_port),
        ],
        cwd=folder,
        stdout=output,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    output.close()
    await asyncio.sleep(1)
    if sim.poll() is not None:
        raise HTTPException(500, "SITL exited during launch; inspect local simulator log")
    v = Vehicle(ident, body.profile, f"tcp:127.0.0.1:{port}", True, sim)
    v.spawn_slot = slot
    vehicles[ident] = v
    event(
        ident, "session_started", {"profile": body.profile, "endpoint": v.endpoint, "owned": True}
    )
    return v.snapshot()


class Connection(BaseModel):
    profile: str
    endpoint: str = Field(max_length=200)


@app.post("/api/connections")
async def connect(body: Connection):
    if body.profile not in PROFILES:
        raise HTTPException(422, "Unknown profile")
    # Avoid arbitrary devices, file URLs or destinations; external local adapters are read-only.
    import re

    if not re.fullmatch(r"(tcp|udpin):127\.0\.0\.1:[0-9]{2,5}", body.endpoint):
        raise HTTPException(422, "Use tcp:127.0.0.1:PORT or udpin:127.0.0.1:PORT")
    if any(v.endpoint == body.endpoint for v in vehicles.values()):
        raise HTTPException(409, "Endpoint already has an owning reader")
    ident = uuid.uuid4().hex[:12]
    v = Vehicle(ident, body.profile, body.endpoint)
    vehicles[ident] = v
    return v.snapshot()


@app.delete("/api/vehicles/{vid}")
async def disconnect(vid: str, request: Request):
    v = vehicle(vid)
    if (
        v.lease
        and v.lease != request.cookies.get("copilot_session")
        and v.lease_until > time.time()
    ):
        raise HTTPException(409, "Another browser holds control")
    await v.stop()
    del vehicles[vid]
    event(vid, "session_stopped", {})
    return {"stopped": True}


@app.post("/api/vehicles/{vid}/lease")
async def lease(vid: str, request: Request):
    v = vehicle(vid)
    sid = request.cookies["copilot_session"]
    if v.lease != sid and v.lease_until > time.time():
        raise HTTPException(409, "Another browser holds the control lease")
    v.lease = sid
    v.lease_until = time.time() + 30
    return {"expires_at": v.lease_until}


@app.get("/api/vehicles/{vid}/workspace")
async def workspace(vid: str):
    v = vehicle(vid)
    return {
        "vehicle_id": vid,
        "draft": v.draft,
        "review": v.review,
        "active": v.active,
        "chat": v.chat,
        "intent_proposal": v.intent_proposal,
        "parameter_proposals": v.parameter_proposals,
        "checks": check(v.draft, v.profile, v.telemetry.snapshot()["home"]),
    }


class Edit(BaseModel):
    expected_revision: int
    draft: Draft


def save_draft(v, d):
    v.draft = d
    v.revisions.append(copy.deepcopy(d))
    v.revisions = v.revisions[-100:]
    v.review = None
    store.put("draft:" + v.id, d)
    event(v.id, "draft_revision", d)


@app.put("/api/vehicles/{vid}/draft")
async def edit(vid: str, body: Edit):
    v = vehicle(vid)
    try:
        d = revise(v.draft, body.draft.model_dump(), body.expected_revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    save_draft(v, d)
    return await workspace(vid)


@app.post("/api/vehicles/{vid}/undo")
async def undo(vid: str, body: dict):
    v = vehicle(vid)
    if body.get("expected_revision") != v.draft["revision"]:
        raise HTTPException(409, "Draft revision changed")
    if len(v.revisions) < 2:
        raise HTTPException(409, "No previous draft")
    d = copy.deepcopy(v.revisions[-2])
    d["revision"] = v.draft["revision"] + 1
    save_draft(v, d)
    return await workspace(vid)


@app.post("/api/vehicles/{vid}/review")
async def review(vid: str):
    v = vehicle(vid)
    s = v.telemetry.snapshot()
    result = check(v.draft, v.profile, s["home"])
    v.review = {
        **result,
        "id": uuid.uuid4().hex,
        "created_at": time.time(),
        "epoch": s["epoch"],
        "home": s["home"],
        "parameter_hash": parameter_hash(v),
    }
    event(vid, "plan_review", v.review)
    return await workspace(vid)


def parameter_hash(v):
    return hashlib.sha256(
        json.dumps(
            {k: p["value"] for k, p in sorted(v.params.items()) if not k.startswith("SIM_")},
            sort_keys=True,
        ).encode()
    ).hexdigest()


@app.post("/api/vehicles/{vid}/upload")
async def upload(vid: str, request: Request, body: dict):
    v = vehicle(vid)
    authorize(v, request)
    r = v.review
    s = v.telemetry.snapshot()
    if not r or body.get("review_id") != r["id"] or r["revision"] != v.draft["revision"]:
        raise HTTPException(409, "Review this exact draft before upload")
    if not r["upload_allowed"]:
        raise HTTPException(409, "Resolve blocking review findings before upload")
    if (
        not s["home"]
        or r["home"] != s["home"]
        or r["epoch"] != s["epoch"]
        or r["parameter_hash"] != parameter_hash(v)
    ):
        raise HTTPException(409, "Vehicle/home/configuration changed; refresh the review")
    if s["armed"]:
        raise HTTPException(409, "Disarm before replacing the onboard mission")
    j = submit(
        v,
        "mission_upload",
        {"waypoints": copy.deepcopy(v.draft["waypoints"]), "home": s["home"]},
        body.get("request_id"),
    )
    j["_snapshot"] = copy.deepcopy(v.draft)
    j["_home"] = copy.deepcopy(s["home"])
    return public_job(j)


class Action(BaseModel):
    action: str
    args: dict = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, max_length=100)


@app.post("/api/vehicles/{vid}/actions")
async def action(vid: str, body: Action, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    s = v.telemetry.snapshot()
    if (v.fence_busy or v.parameter_apply_busy) and body.action in ("arm", "start", "takeoff"):
        raise HTTPException(409, "Wait for the configuration update to finish")
    if body.action not in (
        "arm",
        "mode",
        "takeoff",
        "start",
        "mission_download",
        "parameters",
        "log_list",
        "log_download",
    ):
        raise HTTPException(422, "Action unsupported")
    if body.action == "mode" and body.args.get("mode") not in PROFILES[v.profile]["modes"]:
        raise HTTPException(422, "Unsupported mode for this profile")
    if body.action == "arm" and not isinstance(body.args.get("armed"), bool):
        raise HTTPException(422, "armed must be boolean")
    if body.action == "takeoff" and (
        v.profile != "copter"
        or s["mode"] != "GUIDED"
        or not s["armed"]
        or not 1 <= body.args.get("alt", 0) <= 120
    ):
        raise HTTPException(409, "Takeoff requires armed Copter in GUIDED, altitude 1–120 m")
    if body.action == "start" and (not v.active or not s["armed"]):
        raise HTTPException(409, "Start requires an armed vehicle and verified uploaded mission")
    return public_job(submit(v, body.action, body.args, body.request_id))


@app.get("/api/vehicles/{vid}/parameters")
async def parameters(vid: str):
    v = vehicle(vid)
    meta = metadata(v.profile) if v.owned else {}
    return {
        "vehicle_id": vid,
        "items": [
            {**p, "metadata": meta.get(p["name"], {})}
            for p in sorted(v.params.values(), key=lambda p: p["name"])
        ],
        "expected": max((p["count"] for p in v.params.values()), default=0),
        "metadata_commit": FIRMWARE_COMMIT if meta else None,
    }


@app.get("/api/vehicles/{vid}/fence")
async def read_fence(vid: str):
    v = vehicle(vid)
    return {
        **fence_snapshot(v.params),
        "vehicle_id": vid,
        "actions": metadata(v.profile).get("FENCE_ACTION", {}).get("Values", {}),
    }


@app.put("/api/vehicles/{vid}/fence")
async def write_fence(vid: str, body: FenceEdit, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    if (
        v.telemetry.snapshot()["armed"]
        or v.fence_busy
        or v.parameter_apply_busy
        or (v.trial_task and not v.trial_task.done())
    ):
        raise HTTPException(409, "Disarm and finish other fence/trial operations first")
    try:
        changes = fence_changes(v.profile, v.params, body)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    applied = []
    v.fence_busy = True
    try:
        # Disable first while disarmed; enable only after every selected setting verifies.
        sequence = [("FENCE_ENABLE", 0), *changes.items()]
        expected = dict(body.expected)
        for name, value in sequence:
            if v.closed:
                raise RuntimeError("Session stopped")
            if expected[name] != value:
                await await_job(
                    submit(
                        v,
                        "parameter_write",
                        {"name": name, "value": value, "expected": expected[name]},
                    )
                )
                applied.append({"name": name, "value": value})
                expected[name] = value
        event(vid, "fence_verified", {"applied": applied})
        return {"status": "verified", "applied": applied, **await read_fence(vid)}
    except Exception as exc:
        raise HTTPException(
            409,
            {
                "message": "Fence update incomplete; inspect and reload before retrying",
                "error": str(exc),
                "applied": applied,
            },
        )
    finally:
        v.fence_busy = False


class ParameterEdit(BaseModel):
    name: str = Field(pattern=r"^[A-Z0-9_]{1,16}$")
    value: float = Field(allow_inf_nan=False)
    expected: float = Field(allow_inf_nan=False)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex)


@app.post("/api/vehicles/{vid}/parameters")
async def parameter_write(vid: str, body: ParameterEdit, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    if v.parameter_apply_busy:
        raise HTTPException(409, "Wait for the parameter proposal to finish")
    if v.fence_busy and body.name.startswith("FENCE_"):
        raise HTTPException(409, "A fence update is in progress")
    if body.name.startswith("SIM_"):
        raise HTTPException(403, "Use the separate SITL laboratory for simulator parameters")
    if body.name not in v.params:
        raise HTTPException(404, "Parameter not discovered")
    try:
        validate_parameter(v.profile, body.name, body.value)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return public_job(submit(v, "parameter_write", body.model_dump(), body.request_id))


def public_job(j):
    return {k: v for k, v in j.items() if not k.startswith("_")}


@app.get("/api/jobs/{jid}")
async def job(jid: str):
    if jid not in jobs:
        raise HTTPException(404, "Unknown job")
    return public_job(jobs[jid])


class Interaction(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    targets: list[str] = Field(min_length=1, max_length=6)
    enabled: bool = False


@app.post("/api/interaction")
async def interaction(body: Interaction):
    if not body.enabled or len(set(body.targets)) != len(body.targets):
        raise HTTPException(422, "Enable interaction mode and select unique target vehicles")
    snapshots = {}
    for vid in body.targets:
        v = vehicle(vid)
        snapshots[vid] = {
            "vehicle_id": vid,
            "label": v.snapshot()["name"],
            "profile": v.profile,
            "epoch": v.telemetry.epoch,
            "draft": copy.deepcopy(v.draft),
            "parameters": parameter_context(v.profile, v.params, body.message),
            "live_state": v.telemetry.snapshot(),
            "supported_commands": PROFILES[v.profile]["commands"],
            "previous_messages": copy.deepcopy(v.chat[-6:]),
        }
    try:
        raw, meta = await provider.complete(
            settings.value.prompts.interaction,
            {"request": body.message, "selected_vehicles": list(snapshots.values())},
        )
        reply, prepared = validate_edits(raw, snapshots, vehicles)
    except Exception as exc:
        raise HTTPException(502, "No interaction changes applied: " + str(exc)[:300])
    changes = {}
    for edit in prepared:
        v = edit["vehicle"]
        if edit["draft"] is not None:
            changes[v.id] = {
                "before": snapshots[v.id]["draft"],
                "after": edit["draft"],
                "operations": edit["operations"],
            }
            save_draft(v, edit["draft"])
        if edit["parameters"]:
            proposal = {
                "id": uuid.uuid4().hex,
                "vehicle_id": v.id,
                "epoch": v.telemetry.epoch,
                "created_at": time.time(),
                "expires_at": time.time() + 300,
                "parameters": edit["parameters"],
                "status": "pending",
                "results": [],
                "model": meta,
            }
            v.parameter_proposals.append(proposal)
            v.parameter_proposals = v.parameter_proposals[-30:]
            event(v.id, "parameters_proposed", proposal)
    for vid in body.targets:
        v = vehicle(vid)
        v.chat.append(
            {"role": "user", "text": body.message, "ts": time.time(), "targets": body.targets}
        )
        entry = {
            "role": "assistant",
            "text": reply,
            "ts": time.time(),
            "change": changes.get(vid),
            "model": meta,
        }
        v.chat.append(entry)
        event(vid, "interaction", entry)
    return {"reply": reply, "workspaces": [await workspace(vid) for vid in body.targets]}


def parameter_proposal(v, pid):
    for proposal in v.parameter_proposals:
        if proposal["id"] == pid:
            return proposal
    raise HTTPException(404, "Parameter proposal not found on this vehicle")


@app.post("/api/vehicles/{vid}/parameter-proposals/{pid}/discard")
async def discard_parameters(vid: str, pid: str):
    v = vehicle(vid)
    p = parameter_proposal(v, pid)
    if p["status"] != "pending":
        raise HTTPException(409, "Only pending proposals can be discarded")
    p["status"] = "discarded"
    event(vid, "parameters_discarded", p)
    return await workspace(vid)


@app.post("/api/vehicles/{vid}/parameter-proposals/{pid}/apply")
async def apply_parameters(vid: str, pid: str, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    p = parameter_proposal(v, pid)
    if p["status"] == "verified":
        return await workspace(vid)
    if p["status"] != "pending" or p["epoch"] != v.telemetry.epoch or p["expires_at"] < time.time():
        raise HTTPException(409, "Proposal is stale or already attempted; request a new proposal")
    if (
        v.telemetry.snapshot()["armed"]
        or v.fence_busy
        or v.parameter_apply_busy
        or (v.trial_task and not v.trial_task.done())
    ):
        raise HTTPException(409, "Disarm and finish configuration updates or diagnostics first")
    for param in p["parameters"]:
        current = v.params.get(param["name"])
        if not current or not math.isclose(
            current["value"], param["expected"], rel_tol=1e-6, abs_tol=1e-5
        ):
            raise HTTPException(409, "Parameter changed since proposal; request a new proposal")
        try:
            validate_parameter(v.profile, param["name"], param["value"])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
    p["status"] = "applying"
    v.parameter_apply_busy = True
    try:
        for param in p["parameters"]:
            if v.closed or v.telemetry.epoch != p["epoch"] or v.telemetry.snapshot()["armed"]:
                raise RuntimeError("Vehicle state changed; remaining writes stopped")
            j = submit(v, "parameter_write", {k: param[k] for k in ("name", "value", "expected")})
            p["results"].append({"name": param["name"], "job_id": j["id"]})
            await await_job(j)
            p["results"][-1]["result"] = public_job(j)
        p["status"] = "verified"
    except Exception as exc:
        p["status"] = "failed"
        p["error"] = (
            "Stopped: "
            + str(exc)[:300]
            + ". Earlier verified writes remain applied; inspect results before retrying."
        )
    finally:
        v.parameter_apply_busy = False
        event(vid, "parameters_proposal_result", p)
    return await workspace(vid)


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    edit_authorized: bool = False


@app.post("/api/vehicles/{vid}/chat")
async def chat(vid: str, body: Chat):
    v = vehicle(vid)
    base = copy.deepcopy(v.draft)
    entry = {"role": "user", "text": body.message, "ts": time.time()}
    v.chat.append(entry)
    payload = {
        "request": body.message,
        "edit_authorized": body.edit_authorized,
        "profile": v.profile,
        "supported_commands": PROFILES[v.profile]["commands"],
        "draft": base,
        "checks": check(base, v.profile, v.telemetry.snapshot()["home"]),
        "live_state": v.telemetry.snapshot(),
        "observations": v.telemetry.observations(v.active, "operational"),
        "previous_messages": v.chat[-10:],
    }
    try:
        result, meta = await provider.complete(settings.value.prompts.planner, payload)
        if not isinstance(result.get("reply"), str) or len(result["reply"]) > 16000:
            raise ValueError("Invalid planner reply")
        ops = result.get("operations", [])
        if not isinstance(ops, list):
            raise ValueError("Invalid planner operations")
        if ops and not body.edit_authorized:
            raise ValueError("Review-only response attempted a draft edit; no changes applied")
        change = None
        if ops:
            d = apply_patch(v.draft, ops, base["revision"])
            save_draft(v, d)
            change = {"before": base, "after": d, "operations": ops}
        entry = {
            "role": "assistant",
            "text": result["reply"],
            "ts": time.time(),
            "change": change,
            "model": meta,
        }
        v.chat.append(entry)
        event(vid, "planner", entry)
        return await workspace(vid)
    except Exception as exc:
        entry = {
            "role": "error",
            "text": "Copilot unavailable: " + str(exc)[:300],
            "ts": time.time(),
        }
        v.chat.append(entry)
        raise HTTPException(502, entry["text"])


@app.post("/api/vehicles/{vid}/intent/interpret")
async def interpret_intent(vid: str):
    v = vehicle(vid)
    revision = v.draft["revision"]
    brief = v.draft["intent"]["brief"]
    if not brief.strip():
        raise HTTPException(422, "Write a mission statement first")
    try:
        raw, meta = await provider.complete(
            settings.value.prompts.intent,
            {"profile": v.profile, "statement": brief, "existing": v.draft["intent"]},
        )
        intent = Intent.model_validate(raw["intent"]).model_dump()
        intent["brief"] = brief
        v.intent_proposal = {
            "id": uuid.uuid4().hex,
            "base_revision": revision,
            "intent": intent,
            "explanation": str(raw.get("explanation", ""))[:8000],
            "model": meta,
        }
        event(vid, "intent_proposed", v.intent_proposal)
        return await workspace(vid)
    except Exception as exc:
        raise HTTPException(502, "Intent interpretation failed: " + str(exc)[:200])


@app.post("/api/vehicles/{vid}/intent/accept")
async def accept_intent(vid: str, body: dict):
    v = vehicle(vid)
    p = v.intent_proposal
    if not p or p["id"] != body.get("proposal_id") or p["base_revision"] != v.draft["revision"]:
        raise HTTPException(409, "Intent proposal is stale; interpret the current draft again")
    d = copy.deepcopy(v.draft)
    d["intent"] = p["intent"]
    save_draft(v, revise(v.draft, d, p["base_revision"]))
    v.intent_proposal = None
    return await workspace(vid)


@app.post("/api/vehicles/{vid}/monitor")
async def monitoring(vid: str, body: dict):
    v = vehicle(vid)
    if v.trial_task and not v.trial_task.done():
        raise HTTPException(409, "Monitoring is locked during a trial")
    v.monitor_enabled = bool(body.get("enabled", True))
    v.monitor_track = "telemetry" if body.get("track") == "telemetry" else "operational"
    if not v.monitor_enabled and v.inference:
        v.inference.cancel()
        await asyncio.gather(v.inference, return_exceptions=True)
    v.next_monitor = time.time() + settings.value.monitor_interval
    return v.snapshot()


@app.get("/api/events")
async def events(vehicle_id: str | None = None):
    return store.events(vehicle_id)


@app.get("/api/vehicles/{vid}/messages")
async def messages(vid: str):
    return list(vehicle(vid).telemetry.messages)


@app.get("/api/vehicles/{vid}/evidence/{evidence_id}")
async def evidence(vid: str, evidence_id: str):
    v = vehicle(vid)
    match = next(
        (e for e in reversed(v.telemetry.history) if e["evidence_id"] == evidence_id), None
    )
    if not match:
        raise HTTPException(404, "Evidence aged out of memory; retrieve the recorded telemetry")
    return match


@app.get("/api/recordings")
async def recordings():
    return [
        {
            "id": p.parent.name,
            "bytes": p.stat().st_size,
            "modified": p.stat().st_mtime,
            "live": p.parent.name in vehicles,
        }
        for p in RUNTIME.glob("*/telemetry.jsonl")
    ]


def recording_folder(ident):
    if not ident.isalnum() or len(ident) > 32:
        raise HTTPException(422, "Invalid recording ID")
    folder = RUNTIME / ident
    if not folder.is_dir():
        raise HTTPException(404, "Recording missing")
    return folder


@app.get("/api/recordings/{ident}/download/{filename}")
async def recording_download(ident: str, filename: str):
    folder = recording_folder(ident)
    import re

    if filename not in (
        "telemetry.jsonl",
        "telemetry.tlog",
        "inference.jsonl",
    ) and not re.fullmatch(r"dataflash-[0-9]+\.bin", filename):
        raise HTTPException(403, "File unavailable")
    path = folder / filename
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path, filename=filename)


@app.get("/api/recordings/{ident}/replay")
async def replay(ident: str, at: float | None = None):
    return await asyncio.to_thread(replay_data, ident, at)


def replay_data(ident, at=None):
    path = recording_folder(ident) / "telemetry.jsonl"
    if not path.exists():
        raise HTTPException(404, "Recording missing")
    telemetry = Telemetry(ident, "unknown")
    start = None
    end = None
    points = []
    with path.open() as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            start = e["ts"] if start is None else start
            end = e["ts"]
            if at is not None and e["ts"] > at:
                continue
            telemetry.ingest(e)
            if e["type"] == "GLOBAL_POSITION_INT" and (
                not points or e["ts"] - points[-1]["ts"] >= 1
            ):
                p = e["data"]
                points.append(
                    {
                        "ts": e["ts"],
                        "lat": p["lat"] / 1e7,
                        "lon": p["lon"] / 1e7,
                        "alt": p["relative_alt"] / 1000,
                    }
                )
    return {
        "historical": True,
        "start": start,
        "end": end,
        "at": at or end,
        "snapshot": telemetry.snapshot(at or end),
        "points": points[-3600:],
        "messages": list(telemetry.messages),
        "write_capability": False,
    }


class Trial(BaseModel):
    scenario: str
    duration: int = Field(default=90, ge=30, le=600)
    seed: int = 0
    track: str = "telemetry"


async def run_trial(v, body):
    import random

    trial = v.trial
    try:
        if v.inference:
            v.inference.cancel()
            await asyncio.gather(v.inference, return_exceptions=True)
        v.monitor_track = "telemetry" if body.track == "telemetry" else "operational"
        v.monitor_enabled = True
        trial["state"] = "baseline"
        v.next_monitor = 0
        await asyncio.sleep(20 + random.Random(body.seed).uniform(0, 10))
        restore = {}
        scenario = CATALOG[body.scenario]
        for name, val in scenario["parameters"].items():
            if name not in v.params:
                raise RuntimeError("Fault parameter unavailable on pinned firmware: " + name)
            restore[name] = v.params[name]["value"]
            v.fault_restore[name] = restore[name]
            await await_job(submit(v, "inject", {"name": name, "value": val}), 15)
        trial["onset"] = time.time()
        trial["state"] = "observing"
        # Ground truth lives only in the denied runtime tree, never observation strings.
        truth = {
            "scenario": body.scenario,
            "seed": body.seed,
            "onset": trial["onset"],
            "profile": v.profile,
            "armed": v.telemetry.snapshot()["armed"],
            "track": v.monitor_track,
        }
        (v.folder / f"truth-{trial['id']}.json").write_text(json.dumps(truth))
        await asyncio.sleep(body.duration)
        trial["end"] = time.time()
        trial["state"] = "locking predictions"
        if v.inference:
            await asyncio.gather(v.inference, return_exceptions=True)
        predictions = copy.deepcopy(
            [p for p in v.predictions if trial["onset"] <= p["observed_at"] <= trial["end"]]
        )
        encoded = json.dumps(predictions, sort_keys=True).encode()
        prediction_path = v.folder / f"predictions-{trial['id']}.json"
        with prediction_path.open("xb") as f:
            f.write(encoded)
        prediction_path.chmod(0o444)
        trial["prediction_sha256"] = hashlib.sha256(encoded).hexdigest()
        evidence_times = {
            e["evidence_id"]: e["ts"] for e in [*v.telemetry.history, *v.telemetry.messages]
        }
        trial["results"] = score(
            predictions, body.scenario, trial["onset"], trial["end"], evidence_times
        )
        trial["results"]["filesystem_isolated"] = sandbox_command()[1]
        trial["results"]["phase_at_injection"] = "armed" if truth["armed"] else "disarmed"
        trial["results"]["successful_inference"] = bool(predictions)
        trial["scenario"] = body.scenario
        trial["state"] = "restoring"
    except asyncio.CancelledError:
        trial["state"] = "cancelled"
        raise
    except Exception as exc:
        trial["state"] = "failed"
        trial["error"] = str(exc)
    finally:
        for name, val in list(v.fault_restore.items()):
            if v.closed:
                break
            try:
                await await_job(submit(v, "inject", {"name": name, "value": val}), 15)
                del v.fault_restore[name]
            except Exception:
                trial["restore_required"] = True
        if trial["state"] == "restoring":
            trial["state"] = "complete"
        event(v.id, "trial_result", trial)


@app.post("/api/vehicles/{vid}/trials")
async def trial_start(vid: str, body: Trial, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    if v.parameter_apply_busy or v.fence_busy:
        raise HTTPException(409, "Wait for configuration updates to finish")
    if not settings.value.monitor_enabled:
        raise HTTPException(
            409, "Enable automatic assessments in Settings before a monitored trial"
        )
    if body.scenario not in CATALOG or v.profile not in CATALOG[body.scenario]["profiles"]:
        raise HTTPException(422, "Scenario unavailable for this vehicle")
    if v.trial_task and not v.trial_task.done():
        raise HTTPException(409, "A trial or its restoration is already running")
    if v.fault_restore:
        raise HTTPException(
            409, "Previous fault restoration failed; stop and relaunch this simulator"
        )
    v.trial = {
        "id": uuid.uuid4().hex,
        "state": "starting",
        "duration": body.duration,
        "seed": body.seed,
        "started_at": time.time(),
    }
    v.trial_task = background(run_trial(v, body))
    return v.trial


@app.post("/api/vehicles/{vid}/trials/cancel")
async def trial_cancel(vid: str, request: Request):
    v = vehicle(vid)
    authorize(v, request)
    if v.trial_task and not v.trial_task.done():
        v.trial_task.cancel()
        await asyncio.gather(v.trial_task, return_exceptions=True)
    return v.trial


@app.websocket("/api/ws")
async def websocket(ws: WebSocket):
    host = ws.headers.get("host", "")
    if (
        host.split(":")[0] not in ("localhost", "127.0.0.1")
        or not ws.headers.get("origin")
        or not origin_valid(ws.headers.get("origin"), host)
        or ws.cookies.get("copilot_session") not in sessions
    ):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_json(
                {
                    "vehicles": [v.snapshot() for v in vehicles.values()],
                    "jobs": [public_job(j) for j in list(jobs.values())[-30:]],
                }
            )
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        pass


web = ROOT / "web/dist"
if web.exists():
    app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/icon.svg")
    @app.get("/favicon.png")
    @app.get("/apple-touch-icon.png")
    def brand_icon(request: Request):
        return FileResponse(web / request.scope["route"].path.lstrip("/"))

    @app.get("/")
    def index():
        return FileResponse(web / "index.html")
