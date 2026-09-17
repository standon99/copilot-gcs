# Actual application screenshots

Captured 2026-09-17 from the production React frontend in Chrome at
http://127.0.0.1:8091, using an isolated runtime and native Copter, Plane and
Rover SITL. Code iteration based on 338cd63; firmware
dbe792162d06cab66c3475fd5556bf7a120f119e.

| File | Recorded state |
| --- | --- |
| start.jpg | Empty installation view after test simulators were stopped |
| mission-planning.jpg | Manually prepared 30 m draft with four mission items, three draft exclusion areas, two onboard areas and one disabled operator watch |
| flight.jpg | A separate disarmed Copter with the verified takeoff/hold/RTL/Land mission; instruments, contextual controls and Alerts panel |
| geofence-proposal.jpg | Actual qwen3.5:397b response to an attached map, showing a purple proposal before acceptance |
| settings.jpg | Isolated test settings: vision model, 300 s periodic cadence, 60 s watch spacing, automatic inference paused |
| diagnostics.jpg | Failure controls and trial conditions; no injected fault in this capture |

These are direct 1796 × 1043 JPEG browser captures. Model output and telemetry
are real; none were fabricated. Imagery attribution is retained. Coordinates
are the Canberra simulator site. Captures contain no API key.

The vision proposal took 57.9 s and preserved two existing areas while adding
an approximate runway boundary. Acceptance changed the local draft but left the
onboard bank unchanged. The boundary is not certified or a clearance guarantee.
The four-item mission verified Land's default direction normalization while
disarmed. No new flight or fence-breach test is implied by these images.
See [validation](../geofence-validation.json).

The user's saved model, prompts and monitoring preferences were preserved;
qwen3.5 was selected only in the isolated test installation.

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

### Vision proposal

![Actual model proposal](geofence-proposal.jpg)

### Mission planning

![Mission editor](mission-planning.jpg)

### Settings

![Inference settings](settings.jpg)

### Diagnostics

![Simulation diagnostics](diagnostics.jpg)
