"""Hover an owned Copter SITL instance, run a blind motor-output trial, stop it."""

import json
import time
from pathlib import Path

import integration as api


def main():
    api.call("GET", "/bootstrap")
    v = api.call("POST", "/sitl", {"profile": "copter"})
    vid = v["id"]
    prefix = f"/vehicles/{vid}"
    try:
        time.sleep(30)
        api.action(vid, "mode", {"mode": "GUIDED"})
        api.arm_when_ready(vid)
        api.action(vid, "takeoff", {"alt": 20})
        for _ in range(60):
            time.sleep(1)
            state = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)
            if state["position"]["relative"] >= 18:
                break
        else:
            raise RuntimeError("Did not reach a stable airborne test altitude")
        print(
            "Airborne at", state["position"]["relative"], "m; starting isolated trial", flush=True
        )
        api.call("POST", prefix + "/lease", {})
        api.call(
            "POST",
            prefix + "/trials",
            {"scenario": "motor_loss", "duration": 60, "seed": 71, "track": "telemetry"},
        )
        for _ in range(100):
            time.sleep(2)
            trial = next(x for x in api.call("GET", "/vehicles") if x["id"] == vid)["trial"]
            if trial["state"] in ("complete", "failed", "cancelled"):
                break
        else:
            raise RuntimeError("Airborne trial did not complete")
        path = Path(__file__).resolve().parent.parent / "runtime/copilot/airborne-trial.json"
        path.write_text(json.dumps({"vehicle": vid, "trial": trial}, indent=2))
        print("Airborne trial:", trial, flush=True)
    finally:
        api.call("DELETE", prefix)


if __name__ == "__main__":
    main()
