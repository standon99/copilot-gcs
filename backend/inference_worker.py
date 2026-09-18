"""One-shot inference worker. JSON over anonymous pipes, no tools or API access.

On macOS the parent applies a filesystem sandbox denying local secrets,
recordings and simulator truth. The key only arrives through stdin.
"""

import json
import sys
from urllib.parse import urlsplit, urlunsplit

import httpx


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
            r = client.post(
                request["base_url"] + "/chat/completions",
                headers=headers,
                json={
                    "model": request["model"],
                    "messages": request["messages"],
                    "stream": False,
                    "temperature": 0.2,
                    "max_tokens": request.get("max_tokens", 3500),
                    **(
                        {"tools": request["tools"], "tool_choice": "auto"}
                        if request.get("tools")
                        else {}
                    ),
                },
            )
            if r.status_code != 200:
                print(json.dumps({"error": provider_error(r, request["messages"])}))
                return
            data = r.json()
            raw = data["choices"][0]["message"]
            message = {"role": "assistant", "content": raw.get("content") or ""}
            if raw.get("tool_calls"):
                message["tool_calls"] = raw["tool_calls"]
            # Private reasoning fields are neither logged nor returned to the UI.
            print(
                json.dumps(
                    {
                        "content": message["content"],
                        "message": message,
                        "finish_reason": data["choices"][0].get("finish_reason"),
                        "usage": data.get("usage", {}),
                    }
                )
            )
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
