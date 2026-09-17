"""One-shot inference worker. JSON over anonymous pipes, no tools or API access.

On macOS the parent applies a filesystem sandbox denying local secrets,
recordings and simulator truth. The key only arrives through stdin.
"""

import json
import sys

import httpx


def main():
    request = json.loads(sys.stdin.read())
    try:
        with httpx.Client(timeout=request["timeout"], trust_env=False) as client:
            headers = (
                {"Authorization": "Bearer " + request["api_key"]} if request["api_key"] else {}
            )
            if request.get("operation") == "models":
                r = client.get(request["base_url"] + "/models", headers=headers)
                if r.status_code != 200:
                    print(json.dumps({"error": f"Provider HTTP {r.status_code}"}))
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
                    "max_tokens": 3500,
                },
            )
            if r.status_code != 200:
                print(json.dumps({"error": f"Provider HTTP {r.status_code}"}))
                return
            data = r.json()
            content = data["choices"][0]["message"].get("content") or ""
            print(json.dumps({"content": content, "usage": data.get("usage", {})}))
    except Exception as exc:
        # Never reflect headers, response bodies, request payloads or keys.
        print(json.dumps({"error": type(exc).__name__ + ": inference request failed"}))


if __name__ == "__main__":
    main()
