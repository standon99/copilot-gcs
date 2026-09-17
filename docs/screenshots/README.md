# Actual application screenshots

Updated 2026-09-17 from the production React frontend in Chrome at
`http://127.0.0.1:8091`, using an isolated FastAPI runtime and native Plane, Copter
and Rover SITL. These show the watch-rule iteration based on `8421fe8`.
Firmware: `dbe792162d06cab66c3475fd5556bf7a120f119e`.

| File | Recorded state |
| --- | --- |
| `start.jpg` | Unchanged task-first onboarding capture from the preceding iteration; still matches the start page |
| `mission-planning.jpg` | Reviewed/uploaded version 2: 20 m takeoff, timed hold and RTL; visible red latched watch alert after landing |
| `flight.jpg` | Operate after the flight: disarmed Copter, attitude instrument, explicit mode/arm/start guidance and earlier AI assessment marked stale |
| `settings.jpg` | Separate scheduled interval (300 s) and event minimum spacing (60 s), saved in the isolated test runtime; global pause on |
| `diagnostics.jpg` | Native simulation scenario/seed/track controls and custom-watch isolation guidance; no failure injection in this capture |

The Copter flew a reviewed home-position mission to 20 m, deliberately crossing
a 15 m test ceiling. A real cloud assessment followed the trigger in 4.215 s,
while the regular interval was one hour. The model initially produced zero
coordinate placeholders; these were corrected to reported home before review
and upload. The operator also entered the requested concern notes. The AGL watch
had no valid source in the default simulator and showed unavailable in flight.
Plane and Rover stayed disarmed. See [validation](../watch-validation.json).

These are direct 1796 × 1043 JPEG browser captures. No model output or telemetry
was fabricated. Map attribution is retained; coordinates are the Canberra SITL
site. Screenshots contain no API key. They demonstrate workflow and monitoring,
not propeller diagnosis, obstacle clearance or physical-flight validation.
The separate user installation's saved inference preferences were preserved.

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
