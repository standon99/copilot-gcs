import asyncio
import hashlib
import json
import os
import sys
import time
from typing import Literal

from pydantic import BaseModel, Field

from .config import ROOT
from .inference_worker import has_image
from .monitoring import AutomaticBudget, AutomaticRateLimited
from .settings import credential_for, local_port, settings


class Incident(BaseModel):
    severity: Literal["info", "warning", "critical", "unknown"]
    summary: str = Field(max_length=2000)
    evidence: list[str] = Field(default_factory=list, max_length=30)
    recommendation: str = Field(default="", max_length=2000)


class Assessment(BaseModel):
    status: Literal["nominal", "concern", "insufficient_data"]
    summary: str = Field(max_length=4000)
    incidents: list[Incident] = Field(default_factory=list, max_length=15)


class AssessmentValidationError(ValueError):
    def __init__(self, message, outputs):
        super().__init__(message)
        self.outputs = outputs


def decode_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


def sandbox_command(base_url=None):
    base = [sys.executable, "-I", str(ROOT / "backend/inference_worker.py")]
    if sys.platform != "darwin":
        return base, False
    # Trusted Python and CA certificates remain readable, workspace state does not.
    from .config import RUNTIME

    denied = [ROOT / ".env", ROOT / "runtime", RUNTIME, ROOT / "ardupilot", ROOT / ".git"]
    port = local_port(base_url) if base_url else None
    profile = (
        '(version 1)(allow default)(deny file-write*)(allow file-write* (literal "/dev/null"))'
        '(deny network-outbound (remote ip "localhost:*"))'
        + (f'(allow network-outbound (remote tcp "localhost:{port}"))' if port else "")
        + "".join("(deny file-read* (subpath " + json.dumps(str(p)) + "))" for p in denied)
    )
    return ["/usr/bin/sandbox-exec", "-p", profile, *base], True


class Provider:
    def __init__(self, settings_store=None):
        self.settings = settings_store or settings
        self.capability_cache = {}
        self.monitor_slots = asyncio.Semaphore(2)
        self.planner_slots = asyncio.Semaphore(1)
        path = getattr(self.settings, "path", None)
        self.automatic_budget = AutomaticBudget(
            path.parent / "automatic-usage.json" if path else None
        )

    def automatic_ready(self, now=None):
        return self.automatic_budget.ready(self.settings.value.automatic_min_interval, now)

    async def model_capabilities(self, options):
        key = (options["base_url"], options["model"])
        cached = self.capability_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        result, _ = await self.request("", [], options, operation="capabilities")
        caps = {"model": key[1], "base_url": key[0], **result["capabilities"]}
        ttl = 300 if caps["vision"] is not None else 30
        # Bound entries when operators explore many models/endpoints.
        if len(self.capability_cache) >= 64:
            self.capability_cache.pop(next(iter(self.capability_cache)))
        self.capability_cache[key] = (time.monotonic() + ttl, caps)
        return caps

    async def complete(
        self, system, payload, monitor=False, options=None, operation="chat", image=None
    ):
        options = options or self.settings.get()
        content = json.dumps(payload, allow_nan=False)
        if image:
            content = [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": image}},
            ]
        result, meta = await self.request(
            system,
            [{"role": "system", "content": system}, {"role": "user", "content": content}],
            options,
            monitor=monitor,
            operation=operation,
        )
        return (result["models"] if operation == "models" else decode_json(result["content"])), meta

    async def tool_turn(self, system, messages, tools, options, on_event=None):
        result, meta = await self.request(
            system, messages, options, operation="tools", tools=tools, on_event=on_event
        )
        if result.get("finish_reason") == "length":
            raise ValueError(
                "Model output token limit reached. Narrow the request or adjust Output tokens per chat call in Settings."
            )
        if result.get("finish_reason") == "content_filter":
            raise ValueError("Provider stopped this response; no turn changes applied")
        return result["message"], meta

    async def request(
        self, system, messages, options, monitor=False, operation="chat", tools=None, on_event=None
    ):
        if on_event:
            on_event({"event": "phase", "phase": "queued"})
        if has_image(messages):
            caps = await self.model_capabilities(options)
            if caps["vision"] is False:
                raise ValueError(
                    f"{options['model']} does not accept images. Choose a vision model in Settings, "
                    "save, and attach the map again. No inference request was sent."
                )
            if tools and caps["tools"] is False:
                raise ValueError(
                    f"{options['model']} does not support tool calls. Choose a model that supports "
                    "both images and tools in Settings. No inference request was sent."
                )
        key = credential_for(options["base_url"])
        timeout = (
            min(5, options["inference_timeout"])
            if operation == "capabilities"
            else options["inference_timeout"]
        )
        async with self.monitor_slots if monitor else self.planner_slots:
            if monitor:
                self.automatic_budget.reserve(self.settings.value.automatic_min_interval)
            command, isolated = sandbox_command(options["base_url"])
            env = {
                k: v
                for k, v in os.environ.items()
                if k in ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SYSTEMROOT")
            }
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",
                env=env,
                limit=4 * 1024 * 1024,
            )
            request = {
                "base_url": options["base_url"],
                "operation": operation,
                "model": options["model"],
                "api_key": key,
                "timeout": timeout,
                "messages": messages,
                "tools": tools,
                "stream": operation == "tools",
                "max_tokens": options.get("agent_max_tokens", 2500)
                if operation == "tools"
                else 3500,
            }
            started = time.time()
            if on_event:
                on_event({"event": "phase", "phase": "waiting"})
            try:
                if operation == "tools":
                    result = await asyncio.wait_for(
                        self.read_worker(proc, request, on_event), timeout + 5
                    )
                else:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(json.dumps(request).encode()), timeout + 5
                    )
                    result = json.loads(stdout)
            except BaseException as exc:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
                if isinstance(exc, asyncio.TimeoutError):
                    raise RuntimeError(
                        f"Model request exceeded the {timeout}-second timeout; adjust Inference timeout in Settings if needed"
                    ) from exc
                raise
            if proc.returncode:
                raise RuntimeError(
                    "Isolated inference worker failed to start or exited unexpectedly"
                )
            if "error" in result:
                raise RuntimeError(result["error"])
            return result, {
                "model": options["model"],
                "latency_s": round(time.time() - started, 2),
                "usage": result.get("usage", {}),
                "filesystem_isolated": isolated,
                "settings_revision": options["revision"],
                "endpoint": options["base_url"],
                "prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
                "streamed": result.get("streamed", False),
            }

    @staticmethod
    async def read_worker(proc, request, on_event):
        """Drain events while the isolated worker runs; no tools execute here."""

        async def drain_errors():
            while await proc.stderr.read(4096):
                pass  # Never surface raw subprocess/provider output.

        errors = asyncio.create_task(drain_errors())
        try:
            proc.stdin.write(json.dumps(request).encode())
            await proc.stdin.drain()
            proc.stdin.close()
            result = None
            size = 0
            async for line in proc.stdout:
                size += len(line)
                if size > 8 * 1024 * 1024:
                    raise RuntimeError("Inference worker output exceeded the size limit")
                data = json.loads(line)
                if not isinstance(data, dict) or result is not None:
                    raise RuntimeError("Invalid inference worker response")
                if data.get("event") == "delta":
                    if data.get("field") not in ("content", "thinking") or not isinstance(
                        data.get("text"), str
                    ):
                        raise RuntimeError("Invalid inference worker text event")
                    if on_event:
                        on_event(data)
                elif data.get("event") == "phase" and data.get("phase") == "receiving_tools":
                    if on_event:
                        on_event(data)
                elif "event" not in data:
                    result = data
                else:
                    raise RuntimeError("Invalid inference worker event")
            await proc.wait()
            if result is None:
                raise RuntimeError("Inference worker ended without a complete response")
            return result
        finally:
            errors.cancel()
            await asyncio.gather(errors, return_exceptions=True)

    async def monitor(self, observations):
        options = self.settings.get()
        system = options["prompts"]["monitor"]
        started = time.time()
        outputs = []
        payload = observations
        ids = {s["evidence_id"] for s in observations["samples"]}
        for stat in observations["extrema_10s"].values():
            ids.update([stat["min_evidence"], stat["max_evidence"]])
        ids.update(s["evidence_id"] for s in observations.get("status_messages", []))
        for attempt in range(2):
            remaining = options["inference_timeout"] + 5 - (time.time() - started)
            if remaining <= 0:
                raise AssessmentValidationError("Assessment deadline expired", outputs)
            try:
                raw, meta = await asyncio.wait_for(
                    self.complete(system, payload, monitor=True, options=options), remaining
                )
                outputs.append(raw)
                result = Assessment.model_validate(raw).model_dump()
                for incident in result["incidents"]:
                    if not incident["evidence"] or not set(incident["evidence"]) <= ids:
                        raise ValueError(
                            "Every incident must cite exact supplied telemetry evidence_id strings; waypoint IDs and invented IDs are not evidence. Nominal status may use an empty incidents array."
                        )
                break
            except AutomaticRateLimited:
                if attempt:
                    raise AssessmentValidationError(
                        "Invalid assessment; repair blocked by the hard usage limit", outputs
                    )
                raise
            except (ValueError, TypeError) as exc:
                if attempt == 1:
                    raise AssessmentValidationError(
                        "Model schema/evidence validation failed after one repair", outputs
                    ) from exc
                payload = {
                    "observations": observations,
                    "validation_error": str(exc)[:1000],
                    "previous_output": outputs[-1] if outputs else None,
                    "instruction": "Repair the JSON format/evidence references using only the SAME observations. No new data or scenario information is available.",
                }
        meta["latency_s"] = round(time.time() - started, 2)
        meta["repair_attempted"] = len(outputs) > 1
        return {
            **result,
            **meta,
            "observed_at": observations["observed_at"],
            "completed_at": time.time(),
            "observation_schema": observations.get("schema", "observations.native.v1"),
            "prompt_sha256": hashlib.sha256(system.encode()).hexdigest(),
            "validation_outputs": outputs if len(outputs) > 1 else [],
        }
