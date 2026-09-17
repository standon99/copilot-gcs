# Actual application screenshots

Captured 2026-09-17 from the production React frontend in Chrome at
`http://127.0.0.1:8091`, backed by the real FastAPI server and two native Copter
SITL instances. These show the Copilot GCS product iteration based on `0984521`.
Firmware: `dbe792162d06cab66c3475fd5556bf7a120f119e`.

| File | Recorded state |
| --- | --- |
| `start.jpg` | Task-first onboarding with the editable point-inspection starter, before connecting |
| `mission-planning.jpg` | Real AI-generated takeoff/waypoint/30-second-hold/RTL mission, after verified upload; selected target and 20/30 m altitudes visible |
| `flight.jpg` | That mission returning from the inspection point in AUTO at 30 m, with live navigation cues, attitude instrument and the actual model response |
| `settings.jpg` | Preserved cloud endpoint/model, global pause, 300-second interval and prompt selector during the mission's landing phase |
| `diagnostics.jpg` | Actual scenario/seed/track controls during return/landing; no fault injected; pause and interval notices visible |

The start-page brief survived launching two copters. The initial real model
response asked for missing inspection details. After a protocol fix and backend
restart, a fresh model request produced the mission shown here. Four explicit
inference requests were used across the two sessions; monitoring stayed paused.
No model output, vehicle state or UI was fabricated. See the
[workflow validation](../product-workflow-validation.json) for the flown sequence.

Numerical review, explicit upload and independent readback preceded normal
mode/arm/mission-start controls. The first copter flew to the inspection point,
held for 30 seconds and returned to land and disarm. The second stayed disarmed.
The temporary server and all owned simulators were stopped afterward; saved
settings were unchanged and port 8080 stayed off.

The JPEGs are direct browser captures at 1796 × 1043, not edited telemetry or
generated mockups. They contain no API key. Map attribution is retained. Demo
coordinates are from Canberra SITL and illustrate navigation, not obstacle
clearance or physical-flight readiness. Inspections here mean positioning;
camera and payload control are not implemented.

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

### Start a task

![Describe a task](start.jpg)

### Flight

![Flight view](flight.jpg)

### Mission planning

![Mission editor](mission-planning.jpg)

### Settings

![Inference settings](settings.jpg)

### Diagnostics

![Simulation diagnostics](diagnostics.jpg)
