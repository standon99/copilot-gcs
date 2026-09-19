"""Isolated inference worker. Bounded JSON events over anonymous pipes.

On macOS the parent applies a filesystem sandbox denying local secrets,
recordings and simulator truth. The key only arrives through stdin.
"""

import itertools
import json
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_EVENT_BYTES = 1024 * 1024
REASONING_FIELDS = ("reasoning", "reasoning_content", "thinking")


class StreamError(ValueError):
    """Application-owned error text; never contains provider payloads."""


def reasoning_field(message):
    return next(
        (
            (key, message[key])
            for key in REASONING_FIELDS
            if isinstance(message.get(key), str) and message[key]
        ),
        (None, ""),
    )


def emit(event):
    print(json.dumps(event), flush=True)


def bounded_lines(response):
    """Bound both the full response and an unterminated SSE line."""
    pending = b""
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise StreamError(
                "Model response exceeded the transport size limit; no turn changes applied"
            )
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            if len(line) > MAX_EVENT_BYTES:
                raise StreamError("Model stream event exceeded the size limit")
            yield line.rstrip(b"\r").decode("utf-8")
        if len(pending) > MAX_EVENT_BYTES:
            raise StreamError("Model stream event exceeded the size limit")
    if pending:
        yield pending.rstrip(b"\r").decode("utf-8")


def response_message(data, include_thinking=False):
    choice = data["choices"][0]
    raw = choice["message"]
    message = {"role": "assistant", "content": raw.get("content") or ""}
    if not isinstance(message["content"], str) or len(message["content"]) > 16000:
        raise StreamError("Model reply exceeded the text limit or used an unsupported format")
    if raw.get("tool_calls"):
        message["tool_calls"] = raw["tool_calls"]
    key, thinking = reasoning_field(raw)
    if include_thinking and key:
        if len(thinking) > 32000:
            raise StreamError("Model thinking exceeded the text limit")
        message[key] = thinking
    return {
        "content": message["content"],
        "message": message,
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage") or {},
    }


def complete_tool(call):
    """Recognize a complete call before disambiguating a reused provider index."""
    function = call.get("function") or {}
    if not call.get("id") or not function.get("name"):
        return False
    try:
        return isinstance(json.loads(function.get("arguments", "")), dict)
    except (ValueError, TypeError):
        return False


def read_stream(response, on_event=emit):
    """Assemble indexed tool fragments; only return a complete response for execution."""
    message = {"role": "assistant", "content": ""}
    calls, usage, indexes = {}, {}, {}
    finish = None
    thinking_key = None
    event_lines = []
    event_size = 0
    # Flush a final event even if the provider omits the trailing blank line.
    for line in itertools.chain(bounded_lines(response), [""]):
        if line.startswith("data:"):
            event_lines.append(line[5:].lstrip(" "))
            event_size += len(line)
            if event_size > MAX_EVENT_BYTES:
                raise StreamError("Model stream event exceeded the size limit")
            continue
        if line or not event_lines:
            continue
        payload = "\n".join(event_lines)
        event_lines, event_size = [], 0
        if payload == "[DONE]":
            break
        data = json.loads(payload)
        if not isinstance(data, dict) or "error" in data:
            raise StreamError("Provider reported an error during the streamed response")
        if isinstance(data.get("usage"), dict):
            usage = data["usage"]
        choices = data.get("choices") or []
        if not choices:
            continue
        if len(choices) != 1 or choices[0].get("index", 0) != 0:
            raise StreamError("Provider returned unexpected response choices")
        choice = choices[0]
        delta = choice.get("delta") or {}
        if finish is not None and delta:
            raise StreamError("Provider sent content after completing the response")
        if choice.get("finish_reason") is not None:
            if finish is not None:
                raise StreamError("Provider completed the response more than once")
            finish = choice["finish_reason"]
        key, thinking = reasoning_field(delta)
        if key:
            if thinking_key and thinking_key != key:
                raise StreamError("Provider changed thinking format during the response")
            thinking_key = key
        for field, value, target, limit in (
            ("thinking", thinking, key, 32000),
            ("content", delta.get("content"), "content", 16000),
        ):
            if value is None or value == "":
                continue
            if not isinstance(value, str) or len(message.get(target, "")) + len(value) > limit:
                raise StreamError(
                    "Model streamed text exceeded the limit or used an unsupported format"
                )
            message[target] = message.get(target, "") + value
            on_event({"event": "delta", "field": field, "text": value})
        for fragment in delta.get("tool_calls") or []:
            wire_index = fragment.get("index")
            if type(wire_index) is not int or not 0 <= wire_index < 8:
                raise StreamError("Invalid streamed tool call index")
            index = indexes.get(wire_index, wire_index)
            existing = calls.get(index)
            if existing and fragment.get("id") and complete_tool(existing):
                # Ollama cloud can emit a complete tool per chunk, each with index 0.
                # Distinct complete calls with distinct IDs must not be concatenated.
                if not complete_tool(fragment) or any(
                    c["id"] == fragment["id"] for c in calls.values()
                ):
                    raise StreamError("Ambiguous or repeated streamed tool call")
                index = max(calls) + 1
                indexes[wire_index] = index
            if index not in calls and len(calls) >= 8:
                raise StreamError("Model response exceeded the tool call limit")
            call = calls.setdefault(
                index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
            )
            if fragment.get("type", "function") != "function":
                raise StreamError("Unsupported streamed tool call type")
            for source, destination, name, limit in (
                (fragment, call, "id", 200),
                (fragment.get("function") or {}, call["function"], "name", 80),
                (fragment.get("function") or {}, call["function"], "arguments", 60000),
            ):
                value = source.get(name)
                if value is not None:
                    if not isinstance(value, str) or len(destination[name]) + len(value) > limit:
                        raise StreamError("Invalid or oversized streamed tool call")
                    destination[name] += value
            on_event({"event": "phase", "phase": "receiving_tools"})
    if finish is None:
        raise StreamError("Model stream ended before a complete response; no turn changes applied")
    if finish not in ("stop", "tool_calls", "length", "content_filter"):
        raise StreamError("Provider returned an unsupported completion status")
    if calls:
        if sorted(calls) != list(range(len(calls))):
            raise StreamError("Model stream is missing a tool call")
        message["tool_calls"] = [calls[i] for i in sorted(calls)]
    return {
        "content": message["content"],
        "message": message,
        "finish_reason": finish,
        "usage": usage,
        "streamed": True,
    }


def chat_request(client, request, headers):
    streaming = request.get("stream", False)
    body = {
        "model": request["model"],
        "messages": request["messages"],
        "stream": streaming,
        "temperature": 0.2,
        "max_tokens": request.get("max_tokens", 3500),
        **({"stream_options": {"include_usage": True}} if streaming else {}),
        **({"tools": request["tools"], "tool_choice": "auto"} if request.get("tools") else {}),
    }
    with client.stream(
        "POST", request["base_url"] + "/chat/completions", headers=headers, json=body
    ) as response:
        if response.status_code != 200:
            return {"error": provider_error(response, request["messages"])}
        if streaming and "text/event-stream" in response.headers.get("content-type", "").lower():
            return read_stream(response)
        # Some compatible endpoints return one JSON reply despite stream=true.
        # Accept that same response, without another inference request.
        data = json.loads("\n".join(bounded_lines(response)))
        result = response_message(data, include_thinking=streaming)
        result["streamed"] = False
        if streaming:
            _, thinking = reasoning_field(result["message"])
            for field, value in (("thinking", thinking), ("content", result["content"])):
                if value:
                    emit({"event": "delta", "field": field, "text": value})
        return result


def model_capabilities(client, request, headers):
    """Optional Ollama metadata, on the configured origin only. No inference."""
    url = urlsplit(request["base_url"])
    if not url.path.endswith("/v1"):
        return {"vision": None, "tools": None}
    endpoint = urlunsplit((url.scheme, url.netloc, url.path[:-3] + "/api/show", "", ""))
    try:
        response = client.post(endpoint, headers=headers, json={"model": request["model"]})
        data = response.json() if response.status_code == 200 else {}
        caps = data.get("capabilities") if isinstance(data, dict) else None
        if isinstance(caps, list) and caps and all(isinstance(c, str) for c in caps):
            return {"vision": "vision" in caps, "tools": "tools" in caps}
    except (httpx.HTTPError, ValueError):
        pass
    # Other OpenAI-compatible endpoints need not implement this metadata API.
    return {"vision": None, "tools": None}


def has_image(messages):
    return any(
        isinstance(m.get("content"), list)
        and any(p.get("type") == "image_url" for p in m["content"] if isinstance(p, dict))
        for m in messages
    )


def provider_error(response, messages):
    """Classify errors without reflecting provider bodies, prompts or secrets."""
    status = response.status_code
    if status in (401, 403):
        return f"Provider authentication/access failed (HTTP {status}); check the endpoint and credential"
    if status == 429:
        return "Provider usage/rate limit reached (HTTP 429); wait or check your provider allowance"
    if status == 400 and has_image(messages):
        return (
            "Provider rejected the map-image request (HTTP 400); check that the selected "
            "model supports images and tool calls in Settings"
        )
    if status >= 500:
        return f"Provider service error (HTTP {status}); try again later"
    return f"Provider rejected the request (HTTP {status}); check the selected model and endpoint"


def main():
    request = json.loads(sys.stdin.read())
    try:
        with httpx.Client(timeout=request["timeout"], trust_env=False) as client:
            headers = (
                {"Authorization": "Bearer " + request["api_key"]} if request["api_key"] else {}
            )
            if request.get("operation") == "capabilities":
                print(json.dumps({"capabilities": model_capabilities(client, request, headers)}))
                return
            if request.get("operation") == "models":
                r = client.get(request["base_url"] + "/models", headers=headers)
                if r.status_code != 200:
                    print(json.dumps({"error": provider_error(r, [])}))
                    return
                print(
                    json.dumps(
                        {
                            "models": [
                                x["id"] for x in r.json()["data"] if isinstance(x.get("id"), str)
                            ]
                        }
                    )
                )
                return
            emit(chat_request(client, request, headers))
    except StreamError as exc:
        emit({"error": str(exc)})
    except httpx.TimeoutException:
        print(
            json.dumps(
                {
                    "error": f"Model request exceeded the {request['timeout']}-second timeout; adjust Inference timeout in Settings if needed"
                }
            )
        )
    except Exception as exc:
        # Never reflect headers, response bodies, request payloads or keys.
        print(json.dumps({"error": type(exc).__name__ + ": inference request failed"}))


if __name__ == "__main__":
    main()
