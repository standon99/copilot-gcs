"""Matched nominal/fault smoke trials on owned SITL. Scores require adjudication.

Usage: .venv/bin/python scripts/benchmark.py --scenarios nominal gps_loss --duration 45
Existing vehicle phase is preserved. This never launches or arms physical devices.
"""

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


async def main(args):
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8080", headers={"X-Copilot-Request": "1"}, timeout=60
    ) as client:

        async def call(method, path, body=None):
            r = await client.request(method, "/api" + path, json=body)
            if r.is_error:
                raise RuntimeError(f"{path}: {r.status_code} {r.text[:200]}")
            return r.json()

        await call("GET", "/bootstrap")
        vs = await call("GET", "/vehicles")
        selected = [v for v in vs if v["owned"] and v["profile"] in args.profiles]
        if not selected:
            raise RuntimeError("Launch owned simulator sessions first")
        reports = []

        async def run_vehicle(v):
            vid = v["id"]
            sequence = [(s, seed) for seed in args.seeds for s in args.scenarios]
            random.Random(41).shuffle(sequence)
            for scenario, seed in sequence:
                # A preceding integration process may still own its 30 s lease.
                for attempt in range(20):
                    r = await client.post(f"/api/vehicles/{vid}/lease", json={})
                    if r.is_success:
                        break
                    if r.status_code != 409 or attempt == 19:
                        r.raise_for_status()
                    await asyncio.sleep(2)
                trial = await call(
                    "POST",
                    f"/vehicles/{vid}/trials",
                    {
                        "scenario": scenario,
                        "seed": seed,
                        "duration": args.duration,
                        "track": "telemetry",
                    },
                )
                print(v["profile"], "trial started", trial["id"], flush=True)
                while True:
                    await asyncio.sleep(2)
                    state = next(x for x in await call("GET", "/vehicles") if x["id"] == vid)[
                        "trial"
                    ]
                    if state["state"] in ("complete", "failed", "cancelled"):
                        reports.append({"profile": v["profile"], "vehicle": vid, **state})
                        print(
                            v["profile"],
                            scenario,
                            state["state"],
                            state.get("results", state.get("error")),
                            flush=True,
                        )
                        break
                # Drain the entire 60 s model observation window after restoration.
                await asyncio.sleep(65)

        await asyncio.gather(*(run_vehicle(v) for v in selected))
        output = ROOT / "runtime/copilot" / f"benchmark-{int(time.time())}.json"
        output.write_text(
            json.dumps(
                {
                    "generated_at": time.time(),
                    "track": "telemetry",
                    "scope": "smoke validation; not a release accuracy benchmark",
                    "trials": reports,
                },
                indent=2,
            )
        )
        print("Benchmark report:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="+", default=["copter", "plane", "rover"])
    parser.add_argument("--scenarios", nargs="+", default=["nominal", "gps_loss"])
    parser.add_argument("--seeds", nargs="+", type=int, default=[11])
    parser.add_argument("--duration", type=int, default=45)
    asyncio.run(main(parser.parse_args()))
