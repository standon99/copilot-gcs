"""Create owned simulators, verify real motion, then stop only those instances.

This script intentionally arms SIMULATORS. It has no external connection path.
"""

import argparse
import json
import time
from pathlib import Path

import integration as api


def main(profiles):
    api.call("GET", "/bootstrap")
    results = []
    for profile in profiles:
        v = api.call("POST", "/sitl", {"profile": profile})
        vid = v["id"]
        p = f"/vehicles/{vid}"
        print(profile, "owned flight test", vid, flush=True)
        try:
            time.sleep(30)
            api.call("POST", p + "/monitor", {"enabled": False})
            api.call("POST", p + "/lease", {})
            draft = api.call("GET", p + "/workspace")["draft"]
            points = []
            if profile != "rover":
                points.append(
                    {
                        "id": "takeoff",
                        "command": 22,
                        "lat": -35.3620,
                        "lon": 149.1650,
                        "alt": 30,
                        "frame": 3,
                        "p1": 15 if profile == "plane" else 0,
                    }
                )
            points.extend(
                [
                    {
                        "id": "route",
                        "command": 16,
                        "lat": -35.3605,
                        "lon": 149.1650,
                        "alt": 0 if profile == "rover" else 40,
                        "frame": 3,
                    },
                    {"id": "return", "command": 20, "lat": 0, "lon": 0, "alt": 0, "frame": 3},
                ]
            )
            draft["waypoints"] = points
            api.call("PUT", p + "/draft", {"expected_revision": draft["revision"], "draft": draft})
            w = api.call("POST", p + "/review", {})
            api.wait(api.call("POST", p + "/upload", {"review_id": w["review"]["id"]}))
            api.action(
                vid,
                "mode",
                {
                    "mode": "GUIDED"
                    if profile == "copter"
                    else "FBWA"
                    if profile == "plane"
                    else "HOLD"
                },
            )
            api.arm_when_ready(vid)
            if profile == "copter":
                api.action(vid, "takeoff", {"alt": 15})
            else:
                api.start_when_ready(vid)
            peak_alt = 0
            peak_speed = 0
            state = None
            for _ in range(30):
                time.sleep(1)
                state = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)
                peak_alt = max(peak_alt, state["position"]["relative"])
                peak_speed = max(peak_speed, state["speed"] or 0)
                if profile == "copter" and peak_alt > 10:
                    break
                if profile == "plane" and peak_alt > 8:
                    break
                if profile == "rover" and peak_speed > 0.8:
                    break
            moved = (
                peak_alt > 10
                if profile == "copter"
                else peak_alt > 8
                if profile == "plane"
                else peak_speed > 0.8
            )
            result = {
                "profile": profile,
                "id": vid,
                "verified_motion": moved,
                "peak_relative_alt_m": peak_alt,
                "peak_groundspeed_m_s": peak_speed,
                "mode": state["mode"],
            }
            results.append(result)
            print(result, flush=True)
            if not moved:
                raise RuntimeError("Expected simulator motion was not observed")
            if profile == "copter":
                api.action(vid, "mode", {"mode": "LAND"})
                for _ in range(75):
                    time.sleep(1)
                    state = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)
                    if not state["armed"]:
                        break
                else:
                    raise RuntimeError("Copter did not land/disarm in time")
                entries = api.action(vid, "log_list")["logs"]
                entry = next((x for x in entries if x["size"] > 0), None)
                if not entry:
                    raise RuntimeError("No onboard DataFlash log after flight")
                log = api.action(vid, "log_download", {"id": entry["id"], "size": entry["size"]})
                result["dataflash_bytes"] = log["bytes"]
                result["landing_disarmed"] = True
                print(
                    "Copter landed/disarmed; DataFlash downloaded",
                    log["bytes"],
                    "bytes",
                    flush=True,
                )
        finally:
            api.call("DELETE", p)
    output = Path(__file__).resolve().parent.parent / "runtime/copilot/flight-smoke.json"
    output.write_text(json.dumps({"results": results, "tested_at": time.time()}, indent=2))
    print("Flight tests passed:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        nargs="+",
        choices=["copter", "plane", "rover"],
        default=["copter", "plane", "rover"],
    )
    main(parser.parse_args().profiles)
