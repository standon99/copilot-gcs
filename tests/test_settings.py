import json
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock

import pytest

from backend import settings as settings_module
from backend.fence import FenceEdit, fence_changes
from backend.provider import Provider, sandbox_command
from backend.settings import Preferences, SettingsStore, credential_for


def test_preferences_persist_and_reject_stale_writer(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    changed = Preferences(
        monitor_interval=300,
        monitor_enabled=False,
        watch_min_interval=120,
        watch_inference_enabled=False,
        model="local-model",
        base_url="http://localhost:11434",
    )
    changed.prompts.monitor += " Keep explanations concise."
    result = store.save(changed)
    assert result["revision"] == 1
    assert SettingsStore(path).get() == result
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(ValueError, match="another window"):
        store.save(changed)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://localhost:8080/v1",
        "https://user:password@example.org/v1",
        "https://example.org/v1?key=x",
        "http://localhost:11434/v1/chat/completions",
    ],
)
def test_invalid_endpoint(url):
    with pytest.raises(ValueError):
        Preferences(base_url=url)


def test_cloud_key_is_scoped_to_original_https_origin(monkeypatch):
    monkeypatch.setattr(settings_module, "API_KEY", "dummy-test-secret")
    monkeypatch.setattr(settings_module, "BASE_URL", "https://ollama.com/v1")
    assert credential_for("https://ollama.com/v1") == "dummy-test-secret"
    for endpoint in ("http://localhost:11434/v1", "https://example.org/v1", "http://ollama.com/v1"):
        assert credential_for(endpoint) == ""


async def test_monitor_uses_persisted_prompt_and_model(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    prefs = Preferences(model="my-model")
    prefs.prompts.monitor += " A custom persisted instruction."
    store.save(prefs)
    provider = Provider(store)
    provider.complete = AsyncMock(
        return_value=({"status": "nominal", "summary": "ok", "incidents": []}, {})
    )
    await provider.monitor({"observed_at": 1, "samples": [], "extrema_10s": {}})
    assert provider.complete.call_args.args[0] == prefs.prompts.monitor
    assert provider.complete.call_args.kwargs["options"]["model"] == "my-model"


async def test_local_worker_can_infer_and_list_models_without_cloud_key():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            received.append({"authorization": self.headers.get("Authorization"), "path": self.path})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": "local-test"}]}).encode())

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append(
                {**body, "authorization": self.headers.get("Authorization"), "path": self.path}
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]}).encode()
            )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        options = Preferences(
            base_url=f"http://127.0.0.1:{server.server_port}/v1", model="local-test"
        ).model_dump()
        provider = Provider()
        result, _ = await provider.complete("Test prompt", {}, options=options)
        models, _ = await provider.complete("", {}, options=options, operation="models")
        assert result == {"ok": True} and models == ["local-test"]
        assert received[0]["messages"][0]["content"] == "Test prompt"
        assert all(r["authorization"] is None for r in received)
        if sys.platform == "darwin":
            command, _ = sandbox_command(options["base_url"])
            # An allowed model port must not grant access to another loopback service.
            other = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            code = f"import socket; socket.create_connection(('127.0.0.1', {other.server_port}),timeout=1)"
            denied = subprocess.run([*command[:-1], "-c", code], capture_output=True)
            other.server_close()
            assert denied.returncode != 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_fence_ceiling_datum_and_conflict():
    values = {
        "FENCE_ENABLE": 0,
        "FENCE_TYPE": 7,
        "FENCE_ACTION": 1,
        "FENCE_RADIUS": 300,
        "FENCE_MARGIN": 2,
        "FENCE_ALT_MAX": 100,
        "FENCE_ALT_MAX_TP": 0,
    }
    params = {k: {"value": v} for k, v in values.items()}
    edit = FenceEdit(enabled=True, radius=200, action=1, max_alt=80, expected=values)
    changed = fence_changes("copter", params, edit)
    assert changed["FENCE_ALT_MAX_TP"] == 1 and changed["FENCE_TYPE"] == 3
    assert list(changed)[-1] == "FENCE_ENABLE"
    params["FENCE_RADIUS"]["value"] = 350
    with pytest.raises(ValueError, match="changed"):
        fence_changes("copter", params, edit)
    with pytest.raises(ValueError, match="Rover"):
        fence_changes("rover", params, edit)
