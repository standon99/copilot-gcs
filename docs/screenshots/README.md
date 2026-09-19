# Actual application screenshots

The chat update based on **3fc210a** added **chat-waiting.jpg** and **chat.jpg**
on 2026-09-18, using the production page on port 8091 and an isolated disarmed
Copter runtime. The waiting image shows a real `qwen3.5:397b` request in progress;
the conversation image shows a real completed reply and a later cancelled
request. User messages align right, replies left; activity details are collapsed.
The waiting dots are an activity indicator, not streamed model output.

These are unmodified 1796 × 1043 browser captures, inspected for layout,
attribution and secrets. No mission, fence, watch or parameter was changed and
automatic inference was off. [Validation](../validation.md).

![Waiting for the model](chat-waiting.jpg)

![Conversation and stopped reply](chat.jpg)

## Earlier captures

The images below retain historical validation evidence. Their chat layout and
Tool actions/Cancel turn labels predate the message bubbles shown above; use the
new captures for the current conversation UI.

The map-compatibility fix based on feb4984 refreshed **settings.jpg** and added
**model-compatibility.jpg** and **vision-correction.jpg** on 2026-09-18, from the
actual production page at port 8091 with a separate disarmed Copter runtime.
Settings and Chat show the verified `gpt-oss:120b` text-only restriction.
The vision image shows a real Qwen follow-up with an **inaccurate** road boundary
and unwanted top extension; its claim of correct tracing is model output, not a
validated result. Neither preview was accepted. These are inspected, unmodified
1796 × 1043 browser captures with attribution and no credentials.
[Measured results](../vision-compatibility-validation.json).

![Text-model attachment restriction](model-compatibility.jpg)

The remaining captures below are from the preceding iteration:

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
| settings.jpg | Refreshed for the compatibility fix: model capability status, saved 300 s default interval, 60 s shared cap; periodic/event inference both off |
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
3. Launch the app-owned vehicles needed for the changed workflow. Use the actual
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
