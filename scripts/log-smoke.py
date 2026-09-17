"""Verify advertised-size DataFlash transfer against an owned, disarmed simulator."""

import hashlib
import json
import time

import integration as api


def main():
    api.call("GET", "/bootstrap")
    v = api.call("POST", "/sitl", {"profile": "copter"})
    vid = v["id"]
    prefix = f"/vehicles/{vid}"
    try:
        api.call("POST", prefix + "/monitor", {"enabled": False})
        time.sleep(15)
        api.call("POST", prefix + "/lease", {})
        params = api.call("GET", prefix + "/parameters")["items"]
        original = next(x["value"] for x in params if x["name"] == "LOG_DISARMED")
        for expected, value in ((original, 1), (1, 0)):
            api.wait(
                api.call(
                    "POST",
                    prefix + "/parameters",
                    {"name": "LOG_DISARMED", "expected": expected, "value": value},
                )
            )
            time.sleep(5)
        entries = api.action(vid, "log_list")["logs"]
        entry = next(x for x in entries if x["size"] > 0)
        # Deliberately wrong client size: the gateway must refresh authoritative metadata.
        result = api.action(vid, "log_download", {"id": entry["id"], "size": 1})
        folder = api.ROOT / "runtime/copilot" / vid
        downloaded = (folder / result["file"]).read_bytes()
        native = (folder / "logs" / f"{entry['id']:08d}.BIN").read_bytes()
        assert len(downloaded) == result["bytes"] > 1
        assert downloaded == native[: len(downloaded)]
        assert downloaded[:2] == bytes.fromhex("a395")
        assert hashlib.sha256(downloaded).hexdigest() == result["sha256"]
        response = api.client.get(f"/api/recordings/{vid}/download/{result['file']}")
        assert response.status_code == 200 and response.content == downloaded
        report = {
            "vehicle": vid,
            "tested_at": time.time(),
            **result,
            "native_prefix_equal": True,
            "http_download_equal": True,
            "client_size_ignored": True,
        }
        (api.ROOT / "runtime/copilot/log-smoke.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2), flush=True)
    finally:
        api.call("DELETE", prefix)


if __name__ == "__main__":
    main()
