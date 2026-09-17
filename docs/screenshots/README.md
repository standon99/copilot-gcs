# Actual application screenshots

Captured 2026-09-17 from the production React frontend in Chrome at
`http://127.0.0.1:8091`, backed by the real FastAPI server and two native Copter
SITL instances. Application code: commit `e0ce579`; the documentation/setup-only
iteration adds these images. Firmware: `dbe792162d06cab66c3475fd5556bf7a120f119e`.

| File | Recorded state |
| --- | --- |
| `flight.jpg` | First copter holding at 30 m above home in AUTO after takeoff and waypoint transit; second copter disarmed; live target ring and flight instrument |
| `mission-planning.jpg` | Real model-created local takeoff/waypoint/unlimited-loiter draft, editable altitudes/datums, target selection and pending parameter proposal |
| `settings.jpg` | Actual saved cloud endpoint/model, global pause, 300-second assessment interval and system-prompt selector |
| `diagnostics.jpg` | Actual scenario/seed/track controls; trial not running; pause/interval warnings visible |

One real Ollama `gpt-oss:120b` request created the displayed mission and
LOG_DISARMED proposal. The operator subsequently applied the proposal, reviewed
and uploaded the mission, and used normal mode/arm/takeoff/start controls. The
model did not operate a vehicle. Automatic monitoring stayed paused, and no
failure was injected to produce these screenshots. The test copter was landed
and the temporary server/simulators stopped after capture.

The JPEG files are direct browser screenshots, not generated mockups or edited
telemetry. They include no API key or private environment file. Satellite-map
attribution is retained. Session IDs and coordinates are from the local Canberra
SITL demonstration. Images illustrate UI behavior, not physical-flight readiness
or detection accuracy.

## Refresh procedure

1. Rebuild the frontend and start a temporary local server on a free port.
   Respect any user instruction to keep another port stopped.
2. Preserve the installation's model/prompt/cadence preferences. Use only
   app-owned simulators, bounded inference and non-private demo content.
3. Launch two copters, create a representative local mission through the actual
   UI/API and obtain a real model response if showing model-generated content.
4. Capture the visible application viewport in a browser. Keep vehicle identity,
   units, telemetry freshness, controls and map attribution visible. Do not
   fabricate model output or manipulate telemetry/DOM to simulate success.
5. Inspect each saved image for legibility, framing and secrets. Keep filenames
   stable where the README links to them; record date, code revision and scenario
   changes here.
6. Land/stop test simulators and stop the temporary server. Restore any preferences
   deliberately changed for capture.
7. Commit the refreshed images and affected README/docs together. Do not stage
   raw runtime recordings, private trial truth or `.env`.
