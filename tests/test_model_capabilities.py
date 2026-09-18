import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from backend import inference_worker
from backend.inference_worker import model_capabilities, provider_error
from backend.provider import Provider
from backend.settings import Preferences

IMAGE_MESSAGES = [
    {
        "role": "user",
        "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64,test"}}],
    }
]


@pytest.fixture
def endpoint():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(
                {"path": self.path, "body": body, "auth": self.headers.get("Authorization")}
            )
            if self.path == "/api/show":
                data = {"capabilities": ["completion", "tools"]}
                if body["model"] == "vision":
                    data["capabilities"].append("vision")
                elif body["model"] == "vision-no-tools":
                    data["capabilities"] = ["completion", "vision"]
                elif body["model"] == "unknown":
                    data = {"error": "Not implemented"}
            else:
                data = {"choices": [{"message": {"content": "A fence preview"}}]}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def test_text_model_blocks_image_before_inference_and_caches_metadata(endpoint):
    base, received = endpoint
    options = Preferences(base_url=base, model="text").model_dump()
    provider = Provider()
    caps = await provider.model_capabilities(options)
    assert caps["vision"] is False and caps["tools"] is True
    for _ in range(2):
        with pytest.raises(
            ValueError, match="does not accept images.*No inference request was sent"
        ):
            await provider.tool_turn("system", IMAGE_MESSAGES, [{"type": "function"}], options)
    assert [r["path"] for r in received] == ["/api/show"]
    assert received[0]["auth"] is None
    # Text chat still works with the same model.
    await provider.tool_turn("system", [{"role": "user", "content": "hello"}], [], options)
    assert received[-1]["path"] == "/v1/chat/completions"


@pytest.mark.parametrize("model", ["vision", "unknown"])
async def test_vision_or_unknown_endpoint_preserves_image_and_native_tools(endpoint, model):
    base, received = endpoint
    options = Preferences(base_url=base, model=model).model_dump()
    provider = Provider()
    tools = [{"type": "function", "function": {"name": "get_mission"}}]
    result, _ = await provider.tool_turn("system", IMAGE_MESSAGES, tools, options)
    assert result["content"] == "A fence preview"
    assert [r["path"] for r in received] == ["/api/show", "/v1/chat/completions"]
    assert received[-1]["body"]["messages"] == IMAGE_MESSAGES
    assert received[-1]["body"]["tools"] == tools
    assert all(r["auth"] is None for r in received)


async def test_capabilities_are_scoped_to_endpoint_and_model(endpoint):
    base, received = endpoint
    provider = Provider()
    a = Preferences(base_url=base, model="text").model_dump()
    b = {**a, "model": "vision"}
    c = {**b, "base_url": base.replace("127.0.0.1", "localhost")}
    assert (await provider.model_capabilities(a))["vision"] is False
    assert (await provider.model_capabilities(b))["vision"] is True
    assert (await provider.model_capabilities(c))["base_url"] == c["base_url"]
    assert len(received) == 3


async def test_vision_model_without_tools_is_blocked(endpoint):
    base, received = endpoint
    with pytest.raises(ValueError, match="does not support tool calls"):
        await Provider().tool_turn(
            "system",
            IMAGE_MESSAGES,
            [{"type": "function"}],
            Preferences(base_url=base, model="vision-no-tools").model_dump(),
        )
    assert len(received) == 1


@pytest.mark.parametrize(
    "status,data",
    [(404, {}), (200, {}), (200, {"capabilities": []}), (200, {"capabilities": "vision"})],
)
def test_unsupported_metadata_is_unknown(status, data):
    def respond(request):
        assert str(request.url) == "https://example.test/prefix/api/show"
        return httpx.Response(status, json=data)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert model_capabilities(
            client, {"base_url": "https://example.test/prefix/v1", "model": "custom"}, {}
        ) == {"vision": None, "tools": None}


def test_provider_error_is_actionable_without_reflecting_secrets():
    for status in [400, 401, 403, 429, 500]:
        r = httpx.Response(status, json={"error": {"message": "private-token prompt image"}})
        error = provider_error(r, IMAGE_MESSAGES)
        assert str(status) in error and "private-token" not in error and "prompt image" not in error
    assert "map-image" in provider_error(httpx.Response(400), IMAGE_MESSAGES)


def test_timeout_points_to_setting_without_reflecting_request(monkeypatch, capsys):
    def timeout(request):
        raise httpx.ReadTimeout("private credential or provider text")

    client = httpx.Client(transport=httpx.MockTransport(timeout))
    monkeypatch.setattr(inference_worker.httpx, "Client", lambda **kwargs: client)
    monkeypatch.setattr(
        inference_worker.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "timeout": 45,
                    "api_key": "private-key",
                    "base_url": "https://example.test/v1",
                    "model": "vision",
                    "messages": IMAGE_MESSAGES,
                }
            )
        ),
    )
    inference_worker.main()
    error = json.loads(capsys.readouterr().out)["error"]
    assert "45-second timeout" in error and "Settings" in error and "private" not in error
