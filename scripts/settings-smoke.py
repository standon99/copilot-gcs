"""Live API scheduling/endpoint/fault-lifecycle test using a local stub, not LLM accuracy.

Requires the application running with no active trials. Restores provider preferences
and stops only its own simulator. The stub makes no cloud calls.
"""

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import integration as api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="Ground-station origin")
    args = parser.parse_args()
    api.client.base_url = args.url
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            assert self.headers.get("Authorization") is None
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append({"at": time.time(), "model": request["model"]})
            self.send_response(200)
            self.end_headers()
            content = {
                "status": "insufficient_data",
                "summary": "Local transport test stub, not an assessment",
                "incidents": [],
            }
            self.wfile.write(
                json.dumps({"choices": [{"message": {"content": json.dumps(content)}}]}).encode()
            )

    api.call("GET", "/bootstrap")
    original = api.call("GET", "/settings")["preferences"]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    vid = None
    try:
        changed = {
            **original,
            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "model": "local-stub-transport-test",
            "monitor_interval": 10,
            "automatic_min_interval": 10,
            "monitor_enabled": True,
            "watch_inference_enabled": False,
        }
        api.call("PUT", "/settings", changed)
        v = api.call("POST", "/sitl", {"profile": "rover"})
        vid = v["id"]
        prefix = f"/vehicles/{vid}"
        for _ in range(30):
            time.sleep(1)
            v = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)
            if v["assessment"]:
                break
        assert v["assessment"]["model"] == changed["model"]
        assert v["assessment"]["endpoint"] == changed["base_url"]
        api.call("POST", prefix + "/lease", {})
        original_gps = next(
            x["value"]
            for x in api.call("GET", prefix + "/parameters")["items"]
            if x["name"] == "SIM_GPS1_ENABLE"
        )
        api.call("POST", prefix + "/trials", {"scenario": "gps_loss", "duration": 30, "seed": 2})
        # Active trials must freeze preferences, including custom prompts/model selection.
        response = api.client.put("/api/settings", json=api.call("GET", "/settings")["preferences"])
        assert response.status_code == 409
        for _ in range(40):
            time.sleep(1)
            v = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)
            if v["trial"]["state"] == "observing":
                break
        assert v["trial"]["state"] == "observing"
        params = api.call("GET", prefix + "/parameters")["items"]
        assert next(x["value"] for x in params if x["name"] == "SIM_GPS1_ENABLE") == 0
        api.call("POST", prefix + "/lease", {})
        api.call("POST", prefix + "/trials/cancel", {})
        params = api.call("GET", prefix + "/parameters")["items"]
        assert next(x["value"] for x in params if x["name"] == "SIM_GPS1_ENABLE") == original_gps
        paused = api.call("GET", "/settings")["preferences"]
        paused["monitor_enabled"] = False
        api.call("PUT", "/settings", paused)
        count = len(received)
        time.sleep(12)
        assert len(received) == count
        report = {
            "local_provider_selected": True,
            "assessment_model_verified": True,
            "settings_locked_during_trial": True,
            "gps_injection_observed": True,
            "cancel_restored_parameter": True,
            "pause_stopped_calls": True,
            "stub_requests": len(received),
            "cloud_calls": 0,
            "not_an_accuracy_test": True,
        }
        (api.ROOT / "runtime/copilot/settings-smoke.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        if vid:
            api.call("DELETE", f"/vehicles/{vid}")
        original["revision"] = api.call("GET", "/settings")["preferences"]["revision"]
        api.call("PUT", "/settings", original)
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
