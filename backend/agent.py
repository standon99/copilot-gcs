"""Finite native function-call loop. Only tool arguments/results form the public trace."""

import asyncio
import json
import time

from .agent_tools import TurnConflict, tool_schemas


class TurnLimit(RuntimeError):
    pass


async def run_turn(provider, turn, system, context, options, run, guard_settings):
    content = json.dumps(context, allow_nan=False)
    if turn.map_image:
        content = [
            {"type": "text", "text": content},
            {"type": "image_url", "image_url": {"url": turn.map_image.image}},
        ]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    toolset = tool_schemas(turn.read_only)
    seen = set()
    repeated_errors = {}
    usage = {}
    meta = {}
    started = time.monotonic()
    # Per-request deadlines plus a finite whole-turn bound, including queue time.
    deadline = min(600, options["agent_max_rounds"] * (options["inference_timeout"] + 5))
    for index in range(options["agent_max_rounds"]):
        turn.guard()
        guard_settings()
        run.update(round=index + 1, status="running")
        remaining = deadline - (time.monotonic() - started)
        if remaining <= 0:
            raise TurnLimit("Turn deadline reached; no turn changes applied")
        message, meta = await asyncio.wait_for(
            provider.tool_turn(system, messages, toolset, options), remaining
        )
        turn.guard()
        guard_settings()
        for key, value in meta.get("usage", {}).items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
        calls = message.get("tool_calls") or []
        if not calls:
            reply = message.get("content")
            if not isinstance(reply, str) or not reply.strip() or len(reply) > 16000:
                raise ValueError("Provider returned no usable final reply")
            missing = turn.missing_validation()
            if missing:
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "gcs_feedback": "Call validate_mission on the final working draft before finishing",
                                "vehicles": missing,
                            }
                        ),
                    }
                )
                continue
            return reply, {
                **meta,
                "usage": usage,
                "rounds": index + 1,
                "tool_calls": len(run["steps"]),
                "latency_s": round(time.monotonic() - started, 2),
            }
        if len(calls) > 8 or len(run["steps"]) + len(calls) > 40:
            raise TurnLimit("Tool call limit reached; no turn changes applied")
        assistant = {"role": "assistant", "content": "", "tool_calls": []}
        parsed = []
        for call in calls:
            ident = call.get("id")
            function = call.get("function", {})
            name, raw = function.get("name"), function.get("arguments")
            if not isinstance(ident, str) or not ident or ident in seen or len(ident) > 200:
                raise ValueError("Invalid or repeated tool call ID")
            if (
                not isinstance(name, str)
                or len(name) > 80
                or not isinstance(raw, str)
                or len(raw) > 60000
            ):
                raise ValueError("Invalid tool call envelope")
            seen.add(ident)
            assistant["tool_calls"].append(
                {"id": ident, "type": "function", "function": {"name": name, "arguments": raw}}
            )
            parsed.append((ident, name, raw))
        messages.append(assistant)
        for ident, name, raw in parsed:
            step = {
                "id": ident,
                "name": name,
                "round": index + 1,
                "at": time.time(),
                "status": "running",
            }
            run["steps"].append(step)
            try:
                args = json.loads(raw)
                step["arguments"] = args
                result = {"ok": True, "result": turn.execute(name, args)}
                step["status"] = "ok"
            except TurnConflict:
                raise
            except (ValueError, TypeError, KeyError) as exc:
                result = {"ok": False, "error": str(exc)[:1500]}
                step["status"] = "error"
            serialized = json.dumps(result, allow_nan=False)
            if len(serialized) > 100000:
                raise TurnLimit("Tool result too large; request a smaller page")
            step["result"] = result
            messages.append({"role": "tool", "tool_call_id": ident, "content": serialized})
            if not result["ok"]:
                signature = name + serialized + json.dumps(step.get("arguments"), sort_keys=True)
                repeated_errors[signature] = repeated_errors.get(signature, 0) + 1
                if repeated_errors[signature] >= 3:
                    raise TurnLimit("Repeated identical tool error; no turn changes applied")
        # Images are separately size bounded. Do not retain hidden reasoning or arbitrary provider fields.
        text_size = sum(len(m["content"]) for m in messages if isinstance(m.get("content"), str))
        if text_size > 350000:
            raise TurnLimit("Turn context limit reached; no turn changes applied")
    raise TurnLimit(
        "Maximum model rounds reached; no turn changes applied. Narrow the request or adjust Settings."
    )
