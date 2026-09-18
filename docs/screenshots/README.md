# Actual application screenshots

Captured 2026-09-18 from the production React build in Chrome at
http://127.0.0.1:8091 with an isolated runtime and disarmed native Copter SITL.
Iteration based on 2dc7a4b; pinned firmware
`dbe792162d06cab66c3475fd5556bf7a120f119e`.

| File | Recorded state |
| --- | --- |
| start.jpg | Empty installation after stopping the test simulator; compact name/connection/model pill |
| mission-planning.jpg | Three-item draft, 36 m inspection waypoint, accepted inclusion/exclusion bank and visible watch rules |
| flight.jpg | Disarmed Copter, instruments, last-read fence bank, test watch alert and real (now stale) event advice |
| geofence-proposal.jpg | Actual qwen3.5:397b native tool turn; purple inclusion preview from supplied geographic coordinates, before acceptance |
| tool-actions.jpg | Actual gpt-oss:120b read → update waypoint → validate tool sequence |
| settings.jpg | Saved 300 s default interval, 60 s shared cap, 12-call turn limit; periodic/event inference both off after testing |
| diagnostics.jpg | Failure controls and effective-cadence warning; no fault injected |

These are direct 1796 × 1043 JPEG browser captures, inspected for layout and
secrets. Telemetry and model responses are real. Attribution is retained;
coordinates are the Canberra simulator site. The red voltage watch deliberately
used a test threshold to verify event advice. It is not evidence of a fault.

The Qwen turn took 24.89 s across four model calls and eight tools. The subsequent
GPT-OSS waypoint edit took 4.68 s across four calls. The proposal image does not
show a new vision test; the previous map-attachment result remains in the historical
[geofence record](../geofence-validation.json). See the current
[tool-loop record](../tool-loop-validation.json) for failures, fixes and native
fence/event checks. No flight occurred in this iteration.

The user's saved settings were kept separate from this temporary installation.

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

### Inclusion proposal

![Actual model proposal](geofence-proposal.jpg)

### Tool actions

![Actual read-edit-check sequence](tool-actions.jpg)

### Mission planning

![Mission editor](mission-planning.jpg)

### Settings

![Inference settings](settings.jpg)

### Diagnostics

![Simulation diagnostics](diagnostics.jpg)
