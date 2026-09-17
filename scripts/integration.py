"""Exercise the running local server using owned SITL only; no credentials in output."""

import json
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
client = httpx.Client(
    base_url="http://127.0.0.1:8080", headers={"X-Copilot-Request": "1"}, timeout=90
)
results = []


def call(method, path, body=None):
    r = client.request(method, "/api" + path, json=body)
    if r.is_error:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r.json()


def wait(job):
    for _ in range(3000 if job.get("action") == "log_download" else 300):
        j = call("GET", "/jobs/" + job["id"])
        if j["status"] != "pending":
            if j["status"] == "failed":
                raise RuntimeError(j.get("error"))
            return j
        time.sleep(0.2)
    raise RuntimeError("job timeout")


def action(vid, kind, args=None):
    call("POST", f"/vehicles/{vid}/lease", {})
    return wait(
        call(
            "POST",
            f"/vehicles/{vid}/actions",
            {"action": kind, "args": args or {}, "request_id": uuid.uuid4().hex},
        )
    )


def arm_when_ready(vid, timeout=75):
    """Retry only explicit autopilot rejection while its startup checks settle."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return action(vid, "arm", {"armed": True})
        except RuntimeError as exc:
            if "MAV_RESULT=4" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(5)


def start_when_ready(vid, timeout=75):
    """HOLD/FBWA can arm before GPS aiding is ready for AUTO; keep native checks."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return action(vid, "start")
        except RuntimeError as exc:
            if "MAV_RESULT=4" not in str(exc) or time.monotonic() >= deadline:
                raise
            time.sleep(5)


def run():
    call("GET", "/bootstrap")
    vs = call("GET", "/vehicles")
    for profile in ("copter", "plane", "rover"):
        v = next((v for v in vs if v["profile"] == profile), None)
        if not v:
            v = call("POST", "/sitl", {"profile": profile})
            time.sleep(25)
        vid = v["id"]
        prefix = f"/vehicles/{vid}"
        call("POST", prefix + "/lease", {})
        params = call("GET", prefix + "/parameters")["items"]
        p = next(p for p in params if p["name"] == "LOG_DISARMED")
        # Write the same value: exercises conflict detection, PARAM_SET and separate readback without changing identity.
        result = wait(
            call(
                "POST",
                prefix + "/parameters",
                {"name": p["name"], "value": p["value"], "expected": p["value"]},
            )
        )
        assert result["status"] == "verified"
        print(profile, "parameter verified", flush=True)
        w = call("GET", prefix + "/workspace")
        draft = w["draft"]
        draft["waypoints"] = [
            {
                "id": "w1",
                "command": 16,
                "lat": -35.3630,
                "lon": 149.1653,
                "alt": 0 if profile == "rover" else 30,
                "frame": 3,
            },
            {"id": "rtl", "command": 20, "lat": 0, "lon": 0, "alt": 0, "frame": 3},
        ]
        call("PUT", prefix + "/draft", {"expected_revision": draft["revision"], "draft": draft})
        w = call("POST", prefix + "/review", {})
        result = wait(
            call(
                "POST",
                prefix + "/upload",
                {"review_id": w["review"]["id"], "request_id": uuid.uuid4().hex},
            )
        )
        assert result["status"] == "verified"
        print(profile, "mission upload/readback verified", flush=True)
        mode = "GUIDED" if profile == "copter" else "LOITER" if profile == "plane" else "HOLD"
        assert action(vid, "mode", {"mode": mode})["status"] == "verified"
        result = action(vid, "mission_download")
        assert len(result["items"]) == 3
        result = action(vid, "log_list")
        print(profile, "onboard logs", len(result["logs"]), flush=True)
        results.append(
            {
                "profile": profile,
                "id": vid,
                "parameter": "verified",
                "mission_upload": "verified",
                "mode": "verified",
                "mission_download": "verified",
                "logs": len(result["logs"]),
            }
        )
    # Security: no cookie, foreign origin, missing CSRF header.
    assert httpx.get("http://127.0.0.1:8080/api/vehicles").status_code == 401
    assert (
        client.get(
            "http://127.0.0.1:8080/api/vehicles", headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "http://127.0.0.1:8080/api/sitl",
            json={"profile": "copter"},
            headers={"X-Copilot-Request": ""},
        ).status_code
        == 403
    )
    path = ROOT / "runtime/copilot/integration-results.json"
    path.write_text(
        json.dumps(
            {"tested_at": time.time(), "vehicles": results, "http_security": "passed"}, indent=2
        )
    )
    print("Integration passed; report:", path)


if __name__ == "__main__":
    run()
