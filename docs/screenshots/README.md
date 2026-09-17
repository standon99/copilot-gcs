# Actual application screenshots

Captured 2026-09-17 from the production React frontend in Chrome at
`http://127.0.0.1:8091`, backed by the real FastAPI server and two native Copter
SITL instances. Refreshed with the project icon in the branding/concise-README
iteration based on `91a1877`. Firmware: `dbe792162d06cab66c3475fd5556bf7a120f119e`.

| File | Recorded state |
| --- | --- |
| `flight.jpg` | First copter holding at 30 m above home in AUTO after takeoff and waypoint transit; second copter disarmed; live target ring and flight instrument |
| `mission-planning.jpg` | Operator-created local takeoff/waypoint/unlimited-loiter draft, editable altitudes/datums, vehicle target selection and numerical draft checks |
| `settings.jpg` | Actual saved cloud endpoint/model, global pause, 300-second assessment interval and system-prompt selector |
| `diagnostics.jpg` | Actual scenario/seed/track controls during GUIDED climb; trial not running; pause/interval warnings visible |

The local draft was created through the application's API, then reviewed and
uploaded with readback verification. Normal mode/arm/takeoff/start controls
flew the first simulator. Automatic monitoring stayed paused; this refresh used
no inference requests and shows no model-generated responses or proposals. No
failure was injected. The test copter was landed and the temporary server and
simulators stopped after capture. The earlier model-generated demonstration
remains documented in the historical validation record and Git history.

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

## Gallery

### Flight

![Flight view](flight.jpg)

### Mission planning

![Mission editor](mission-planning.jpg)

### Settings

![Inference settings](settings.jpg)

### Diagnostics

![Failure laboratory](diagnostics.jpg)
