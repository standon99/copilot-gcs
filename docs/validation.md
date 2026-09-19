# Validation record

## Numeric inference settings — 2026-09-19

Fixed clearing a numeric Settings field immediately inserting `0`. Empty edits
now remain empty; entered values still use numeric payloads and the existing
server validation. This applies to the timeout, periodic/watch intervals, hard
automatic spacing, model-call limit and output-token limit.

Chrome reproduced the original timeout bug, then verified clearing and typing
in all six fields after the fix, including an empty timeout followed by `60`.
Reload saved restored the form; saved preferences remained unchanged. All
**20 frontend tests**, formatting and the production TypeScript/Vite build
passed; the existing bundle-size advisory remains. No inference requests or
vehicle actions were made, and backend tests were not rerun for this frontend
change. README, usage, implementation, development and setup documentation were
reviewed and remain accurate; the layout and screenshots are unchanged.

## Spatial tools and 3D terrain — 2026-09-19

Iteration based on 414a82e. **182 Python tests and 20 frontend tests passed**,
with Ruff, formatting and the production build. Vite retains its bundle-size
advisory. Fourteen new spatial tests cover metre geometry, curved/short roads,
infeasible containment, required kind/containment arguments, trace validation,
fresh position versus home, projection/scale, rendered image feedback, clipping,
prior-proposal reads, concurrency guards and turn-local edits. Frontend tests
cover pitch limits, height-aware bounds, stale positions and screen projection.
After the final append guard, the affected 33 spatial/agent tests passed again.

Chrome verification used an isolated runtime on port 8091, with automatic periodic
and event inference off. A real Overpass query returned **35** mapped road/runway
candidates. UI feature selection and repeated Share map sends worked; each sent
message recorded a fresh 1280 × 945 image. Sending from 3D flattened the capture
to north-up 2D and restored the tilted operator view.

Three real Qwen turns attempted **nine model calls** in total. The first stopped
at the 2,500 output-token limit on call two and committed nothing. With only the
test installation increased to 4,096 tokens, a retry completed in **98.70 s**,
three calls/three tools (**33,171 reported tokens**). It built a measured 1,000 m
square west of Monaro Highway, 20.0 m from its mapped line, and inspected an
overlay. It omitted the requested runway's numerical containment IDs; those
IDs are now a required argument, including an explicit empty list when appropriate.

A follow-up using that schema read the pending preview, rebuilt it with the
runway ID and inspected the overlay: **115.37 s**, four calls/four tools,
**47,171 reported tokens**. The mapped runway line was contained with **104.25 m**
boundary clearance; its full outline remained unknown. The model also appended
an unintended duplicate area. The final tool now rejects ambiguous edits when an
area exists: callers must select `replace_index` or explicitly request `append`.
Regression checks verify rejection leaves the proposal unchanged, replacement
keeps one area, and explicit append adds another. The live vision turns predate
that final guard; no further paid retries were made. Neither preview was accepted
or uploaded. [Measured record](spatial-terrain-validation.json).

Two app-owned Copters flew simultaneously to **100 m and 60 m above home**.
Actual 3D dots/labels, ground reference lines, swipe up/down, fit controls and
framing during climb were inspected. Both landed and disarmed. An attempted
150 m takeoff was rejected by the existing 1–120 m command limit before the 100 m
test; no command limits were weakened. Missing DEM tiles no longer cause false
sea-level ground/framing, and overlapping ground markers were reduced in 3D.
This tests the browser display and simulator integration, not physical flight or
terrain clearance. The web DEM is separate from AGL watch inputs.

Actual screenshots and capture conditions are in the [gallery](screenshots/README.md).
The user installation was restarted with its exact saved preferences, both drafts
and **14 chat entries** preserved. Sessions received new IDs and control leases
reset. The isolated test server/simulators were stopped afterward. README, usage,
setup, product, AI interface, implementation, development and spatial docs were
updated. The broader design/feasibility baselines were checked and remain historical.

## Chat bubbles and waiting state — 2026-09-18

Iteration based on 3fc210a. **17 frontend tests passed** and the production
TypeScript/Vite build passed, retaining its bundle-size advisory. Six added tests
exercise immediate pending messages, server acknowledgement without duplication,
vehicle switching, completion/cancellation/failure, reload recovery and explicit
multi-vehicle targets. No backend implementation changed; the Python suite was
not rerun for this iteration. Frontend formatting, local documentation links,
diff checks and credential scans passed.

Chrome verification used port 8091 with a separate disarmed native Copter,
automatic periodic/event inference off, and at most four calls per chat turn.
Two actual `qwen3.5:397b` requests read vehicle state and returned formatted
replies in **10.55 s** and **7.85 s**, each using two model calls and one
`get_vehicle_state` action. Their reported token totals were **34,516** and
**39,665**. A first cancellation attempt lost the race to the second completed
reply; a third request was stopped after reloading the page, before its first
model response. The waiting bubble survived reload and changed to Stopped.
Five model requests were attempted in total; usage for the cancelled request is
unavailable. No extra calls were made to manufacture screenshots.

The browser showed right/left message bubbles, Markdown emphasis/lists, the
waiting model/time/Stop control, collapsed activity details, expandable read-tool
results and no persistent call counter in the conversation. The draft remained
version zero with no waypoints, fences, watches or parameter proposals. No
vehicle commands or writes were tested. Actual inspected screenshots are in the
[capture notes](screenshots/README.md).

README, usage, AI interface, implementation, development and screenshot docs
were updated. Setup instructions and the broader design baseline were reviewed
and remain accurate. `react-markdown` 10.1.0 is now pinned for reply rendering;
raw HTML and remote model-written images are disabled. The new
[spatial-planning review](spatial-planning.md) records recommendations prompted
by the user's road-geofence example; those spatial additions are not shipped or
validated by this iteration.

The user's 8080 tab was refreshed without restarting its backend. Exact saved
settings, both session IDs, drafts, chat histories and pending proposals were
verified unchanged across the refresh. The isolated 8091 server and its owned
test simulator were stopped afterward.

## Map-image model compatibility — 2026-09-18

Iteration based on feb4984. The two reported map failures used **gpt-oss:120b**
and returned HTTP 400 on the first call, before any tools ran. Ollama `/api/show`
confirmed no vision capability for that model; **qwen3.5:397b** reported both
vision and tools. Capability discovery now controls the attachment UI and backend
preflight. Unknown endpoints remain usable. Tests verify that rejected images
never reach inference, text chat remains available, caches respect endpoint/model,
local requests carry no cloud key, and provider error/timeout text reveals no
response body or credential.

**168 Python tests and 11 frontend tests passed**, with Ruff, formatting,
diff checks and the production build (the existing Vite bundle-size advisory
remains). Browser checks verified disabled attachment for the text model, the
Model settings link, capability display and discovery for an unsaved model choice.
Actual Settings and compatibility screenshots were captured.

An isolated disarmed Copter exercised native image turns with actual satellite
captures. The first Qwen turn exceeded the original **45 s** timeout. A bounded
retry using **120 s**, six calls maximum and 4,096 output tokens per call completed
in **86.68 s**, two calls and one `propose_geofence` action (13,594 reported tokens).
A closer-image correction completed in **53.50 s**, two calls and one action
(13,497 reported tokens). Pixel polygons were converted, validated and displayed
as previews. No proposal was accepted or uploaded; no vehicle command ran.

**Road alignment did not pass visual review.** The first preview was an oversized
rectangle; the correction still deviated from the road and retained an unwanted
extension. The model's claims that it followed the road were inaccurate. This
verifies image delivery and tool integration, not reliable road segmentation or
flight-ready fencing. The [measured record](vision-compatibility-validation.json)
and [actual correction screenshot](screenshots/vision-correction.jpg) retain that
limitation. Five inference requests were issued, including the timeout; its
token usage is unavailable. Automatic inference stayed off in the test runtime.

README, AI interface, implementation, usage, setup troubleshooting and screenshot
notes were updated. Setup commands, dependencies and firmware pin were reviewed
and remain unchanged. Saved user inference preferences were preserved separately
from the test settings. The 8080 app was restarted with disarmed Copter/Plane
sessions; settings, both drafts and all six chat entries were verified unchanged.
Session IDs changed and control leases were reset. The isolated 8091 server and
its test simulator were stopped after verification.

## Native tool loop, inclusion fences and compact header — 2026-09-18

Iteration based on 2dc7a4b. **157 Python tests and 11 frontend tests passed**,
with Ruff, formatting, diff checks and the production build. Vite retains its
bundle-size advisory. New checks cover native tool-result feedback, typed errors,
read-only/target guards, stale sessions and revisions, cancellation/rollback,
mandatory final validation, repeated-error termination, shared persisted usage
limits, oldest-due scheduling across vehicles, independent event advice, windowed
altitude evidence and inclusion geometry.

A real **qwen3.5:397b** turn completed eight tool actions in four model calls
(**24.89 s**, 24,222 reported total tokens across calls). It read the mission and
configuration, changed a waypoint to 35 m above home, validated, enabled the
requested yaw-rate watch, turned periodic monitoring off, kept per-vehicle watch
advice on, and proposed an inclusion while preserving the exclusion. The global
Settings switches remained off and were accurately reported as blocking automatic
inference. Geometry stayed a preview until browser acceptance.

A later **gpt-oss:120b** turn read, changed that waypoint from 35 to 36 m and
validated it in four model calls (**4.68 s**, 12,273 reported total tokens).
Neither turn uploaded a mission, applied parameters or commanded flight. The
model's wording about being ready to upload did not grant a review or write lease;
those remain separate operator checks/actions.

Development failures are retained in the [measured record](tool-loop-validation.json):
an eight-round malformed fence attempt, two GPT-OSS HTTP-500 turns, and a Qwen
turn repeatedly string-encoding an optional watch object. All discarded staged
edits. Schemas were simplified for provider compatibility; identical repeated
errors now terminate early. The longer GPT-OSS request was not rerun after the
last schema fix; the successful final complex check used Qwen. This is integration
evidence, not a general model-reliability result. The checks issued **43 provider
requests**, including failed turns, two compatibility probes and one event
assessment; failed-call token usage is unavailable.

Native **disarmed Copter, Plane and Rover** verified mixed 5001 inclusion / 5002
exclusion banks by upload and independent readback. Plane and Rover verified both
union and intersection modes, preserving unrelated FENCE_OPTIONS bits. Copter
uploaded the actual accepted model proposal. Clearing that mixed bank verified an
empty readback while retaining enabled circle/ceiling settings. Unit cases cover
concavity, boundary contact, home/departure/return, empty intersections, union gaps,
unsupported bank types and the combined 70-vertex limit.

One real **gpt-oss:120b** watch assessment completed in **4.37 s** with global and
per-vehicle periodic monitoring off. It cited supplied evidence about the disarmed,
stationary vehicle. A deliberately low test voltage threshold caused the event;
this was a pipeline check, not a blinded fault trial. A second trigger turned red
and queued without another request inside the 60-second shared cap. Event advice
was then disabled in the test installation. The response's “fully charged” claim
is model interpretation of reported values, not an independent battery diagnosis.

Chrome checks verified inclusion preview/accept, manual drawing, numerical
blockers for an invalid region, Undo without added waypoints, rule details/prompts,
red event cards, tool traces, settings and the compact status pill. All affected
[screenshots](screenshots/README.md) were refreshed from the actual page. No new
vision attachment, fence-breach recovery, airborne fault or physical-flight test
was run. Previous vision and flight records below remain historical.

The local-stub regression check also verified endpoint selection, frozen Settings
during a trial, GPS injection/cancel restoration and periodic pause with zero
cloud calls. An initial run against 8080 timed out behind its existing sessions;
preferences were restored automatically. The harness now accepts `--url` for
an isolated server and explicitly sets its test-only automatic cap. The shared
scheduler selects the oldest due periodic assessment across all vehicles, with
oldest queued watch events first, instead of using vehicle insertion order.
A final isolated three-profile local-stub check assessed Copter, Plane and Rover
in three requests spaced 10.015 and 10.052 seconds apart under a 10-second cap.
All remained disarmed; no cloud calls were made. The final 8080 restart cleared
the temporary stub assessments from the initial harness run.

The temporary 8091 server and its simulators were stopped. The updated 8080 app
was restarted with disarmed Copter/Plane sessions; existing drafts and saved model,
prompts and monitoring preferences were preserved. Setup commands and examples
were checked and remain applicable; no dependency or firmware-pin change was needed.

## Flight workspace, exclusion areas and vision — 2026-09-17 (historical)

Iteration based on 338cd63. **132 Python tests and 11 frontend tests passed**,
with Ruff checks and the production TypeScript/Vite build. Coverage includes
invalid/quantized polygon geometry, departure/RTL intersections, pixel conversion,
image age/bounds, proposal acceptance/staleness, mission-type isolation,
first-vertex readback, conflict and partial-failure journals, Land normalization,
and profile-specific flight-control sequencing.

Native disarmed Copter, Plane and Rover accepted exclusion polygons through
MAVLink2 type 1, followed by independent downloads and verified parameter writes.
Copter also accepted two polygons. Rover clearing removed the bank and polygon
bit while retaining the circular fence. Unsupported bank types and altered
readback are tested with protocol fixtures; no physical vehicle or deliberate
in-flight fence breach was tested.

The reported Land upload error was reproduced from the user's four-item plan.
Pinned AP_Mission returns LAND p4=+1 for the default zero direction. A separate
native Copter accepted takeoff, timed loiter, RTL and Land after the narrow
normalization fix: all five downloaded items (including synthetic home) verified.
Negative/nondefault directions and unrelated fields remain checked.
[Measured record](geofence-validation.json).

A single real qwen3.5:397b vision interaction consumed an actual 1280 × 855
north-up map image and completed in **57.9 s**. It returned three valid geographic
polygons, preserving the two existing areas and proposing an approximate runway
boundary. The preview did not change the draft; acceptance changed it from two
to three areas while the onboard bank remained two. This tests image transport,
schema validation, preview and acceptance, not boundary accuracy or clearance.
Pixel-coordinate conversion was tested with unit fixtures; this model response
chose geographic coordinates. Automatic inference stayed paused.

Chrome verification used the real production frontend and isolated native SITL:
map drawing and saving without adding waypoints, area editing/cancellation,
proposal acceptance, separate Chat/Alerts/Watch rules, functional labels and
instrument/control layout. Screenshots were refreshed from the running UI; their
capture conditions are in [screenshots](screenshots/README.md). The user's saved
model, prompts and cadence were kept separate from the vision-test settings.
The current tests were disarmed; earlier flight evidence below remains historical.
The normal installation was restarted with fresh, empty Copter and Plane
sessions as requested; old workspaces were privately backed up first. All 81 local
documentation links resolved. Setup instructions were checked and remain accurate;
no dependencies or installation steps changed.

Requested slogans were removed from the interface and social-preview source.
The deterministic PNG export was inspected. GitHub browser automation lost its
connection while opening the image uploader, so the updated export is included
in the repository but was not applied to the separate Social preview setting.


## Visible watches and operating guidance — 2026-09-17

Iteration based on `8421fe8`. **109 Python tests and 8 frontend tests passed**,
with Python lint/format checks and the production TypeScript/Vite build. New
checks cover drifting startup coordinates, AGL validity/units/range/terrain
coverage, phase evidence, dwell/hysteresis/cooldown, retained alerts, pause and
trial isolation, exact event evidence, watch revision/target guards, voltage
sentinels and configuration-review hashes. This adds an operational watch
workflow; it does not establish failure-detection accuracy.

The user's native Plane recording began at 0°,0°, then drifted slightly around
that location without a GPS fix before initializing at Canberra. It was disarmed.
The map now waits for initialization. Fresh native Plane, Copter and Rover
sessions all produced their first accepted map positions near the intended spawn.

A real `gpt-oss:120b` interaction proposed two typed, disabled watches alongside a
Copter mission: AGL below 10 m and a deliberately conflicting 15 m relative-home
test ceiling. The model emitted zero-coordinate navigation placeholders and did
not populate the separate concern-notes field. The operator replaced those
coordinates with reported home and entered the concern before review/upload;
no placeholder route was flown. The application contract was then clarified,
without overwriting saved custom prompts. That revised wording was not separately
retested against the cloud model. Model proposals still require inspection.

After numerical review and verified mission readback, native GUIDED/Arm/Start
controls flew takeoff to 20 m, a 10-second timed hold and RTL. The relative-height
watch fired at **15.166 m**. Its event assessment began **0.0026 s** after the
local trigger and completed **4.215 s** after it, despite a **3,600-second periodic
interval**. The response cited the ceiling breach. One interaction and one event
assessment were used, with no repair requests; a sustained breach did not produce
additional calls. Model comments that current was “normal” are not validated
against a propulsion baseline and do not establish propeller health.

Peak relative altitude was **20.004 m**; the Copter landed and disarmed. Plane
and Rover remained disarmed. The AGL watch was correctly unavailable in flight
because default SITL supplied no valid range/terrain source. Valid AGL breach
handling was exercised with unit fixtures, not a native sensor-equipped flight.
The latched red alert remained visible after landing. See the compact
[measured record](watch-validation.json).

Production-browser checks covered plain version labels, upload prerequisites,
vehicle-specific start guidance, watch cards and inference controls. A manual Rover rule triggered locally with AI paused; acknowledgement kept the active breach red, editing disabled it, and removal cleared it. The fence-pane control button obtained a real lease without arming. Settings
were saved through the UI in an isolated runtime. Updated screenshots show the
actual app after the flight, with its earlier assessment clearly marked stale;
no telemetry or model output was fabricated. User settings remained separate.
Older records below describe their original revisions and screenshots.

## Copilot GCS task workflow — 2026-09-17

The product now leads with everyday waypoint flights and point inspections:
Describe → Review → Upload → Operate. The start page preserves an editable
brief through simulator launch, AI planning targets the selected vehicle by
default, and profile-specific starters ask for missing operating details.
Simulation diagnostics remain available as supporting tools. Product direction,
operating guides, branding and actual screenshots were refreshed together.

**85 Python tests and 7 frontend workflow tests passed**, along with Python lint,
format checks and the production TypeScript/Vite build. The existing large-map
bundle advisory remains. New tests cover mission progress across revisions,
vehicle selection and reboot invalidation, plus timed-loiter readback and rejection
of changed mission fields. All 70 local documentation file/image/heading links
resolved, and the five screenshots decoded at 1796 × 1043 and were visually
inspected. Setup commands were reviewed; dependencies and native toolchain
installation were not rerun. The credential/history scan passed.

Chrome and two native Copter simulators exercised the flow on temporary port
8091. A real inspection starter response asked for coordinates, altitude and
hold duration without editing. Explicit details then produced takeoff at 20 m,
a waypoint at 30 m, a 30-second timed hold and return home. Selecting another
vehicle reset the AI target selection; the unselected copter's draft stayed empty.
Four explicit cloud requests were used across the initial and final sessions.
Automatic monitoring remained paused, with saved cadence/model/prompts unchanged.

The first upload attempt rejected a changed parameter hash. **Refresh checks**
now lets the operator rerun numerical checks without paying for another AI
review; it preserves upload-time home/configuration checks. The real timed-hold
upload then exposed the pinned firmware's default direction encoding: zero is
returned as +1. The fix accepts that specific encoding while retaining checks on
duration, coordinates, altitude, explicit radius/direction and all other fields.

After restarting with that fix, a fresh real model draft passed numerical review,
operator upload and independent readback. Normal GUIDED/arm/mission-start actions
flew takeoff, waypoint transit, the timed hold, return and landing. Peak relative
altitude was **29.998 m**; the vehicle disarmed at the end, and the other vehicle
remained disarmed. A post-flight edit showed draft r2 needing review while r1
remained onboard. See [the recorded summary](product-workflow-validation.json).

An initial model review described RTL altitude and route distance imprecisely.
This run demonstrates the workflow and protocol behavior, not general model
accuracy, terrain clearance, camera capture or physical-flight readiness. Plane
and Rover starters were inspected, but their vehicle operations and fault trials
were not rerun. Both test sessions were stopped; port 8080 stayed stopped.

The GitHub About description was updated. The new social-preview PNG was uploaded
and GitHub published an image URL, but its image CDN returned HTTP 403 and the
preview remained blank during verification. The reviewed export is committed;
public image rendering remains unverified. See [brand notes](brand/README.md).

## GitHub social preview publication (historical, `0984521`)

On 2026-09-17, after the user made the repository public, the committed
1280 × 640 `docs/brand/social-preview.png` was uploaded through GitHub's Social
preview setting. The complete artwork was visually verified after reloading
the settings page. The brand guide now records the applied image. The main
README and implementation guide were reviewed and remain accurate. This update
changes repository presentation and documentation only; application tests and
simulator sessions were not rerun.

## Project icon and concise README (historical, `1000c8d`)

The README now focuses on features and running the application, with detailed
setup, usage and development instructions in linked guides. The original shield
and navigation icon appears in the README, app header and browser icons. Editable
SVG sources, PNG exports and a 1280 × 640 GitHub social-preview image are recorded
in [brand/README.md](brand/README.md).

All 74 automated tests, the production TypeScript/Vite build and Python lint
passed. All 61 local documentation file/image links resolved. The running backend
served the SVG favicon, PNG favicon and Apple touch icon with HTTP 200 and the
expected image content types. The icon and social preview were visually inspected;
the preview is under GitHub's 1 MB limit. Direct Chrome screenshots were refreshed
using two native Copter SITL sessions on temporary port 8091, with no inference
requests or changes to saved model, cadence or prompts. Capture conditions are in
[screenshots/README.md](screenshots/README.md). Detailed design and feasibility
documents were reviewed and remain applicable.

All four refreshed JPEGs decoded at 1796 × 987 and were visually inspected. The
first copter completed reviewed upload, GUIDED takeoff, AUTO waypoint transit
and 30 m hold, then LAND and disarming; the second remained disarmed. Both owned
simulators and the temporary server were stopped afterward. Port 8080 remained
stopped throughout.

At that iteration, authenticated GitHub repository settings were inspected, but
social-preview upload was unavailable while the repository was private. The PNG
was committed alongside its source for a later upload, and the icon appeared in
the repository README. The follow-up publication record above supersedes that
upload limitation.

## Public documentation, license and setup verification (historical, `91a1877`)

The documentation iteration added a full fresh-clone README, the MIT license for original repository code, `CLAUDE.md` iteration/commit/documentation rules, and four direct browser screenshots. The images at that commit show two real native Copter SITL sessions, a real Ollama-generated mission/parameter proposal, the mission editor, settings and diagnostics. The first copter completed reviewed upload, takeoff, AUTO transit/loiter at 30 m, then LAND and disarming. Automatic monitoring remained paused; one real planning request was used. Current screenshot provenance and refresh instructions are recorded in [screenshots/README.md](screenshots/README.md).

A new temporary application checkout and Python virtual environment exercised the documented setup script with the pinned requirements, including the added `requirements-sitl.txt`. Application dependencies installed, an empty-key `.env` was created with mode 0600, Copter/Plane/Rover metadata was generated, the production frontend built, and `pip check` passed. This check reused the existing pinned upstream source checkout and host Node 22; it was not a fresh operating-system or full native compiler/toolchain installation.

All README/local documentation links and heading targets were checked. All four JPEGs were inspected visually and decoded successfully at 1796 × 1043. The temporary application server used port 8091 and was stopped after capture; port 8080 remained stopped. Historical claims about an unconfigured remote were removed from current operating documentation.

## Interaction mode, flight cues and instruments

The update passes **74 automated tests**, Python lint and the production TypeScript/Vite build. Tests cover all-target validation before mutations, unselected/repeated targets, session/revision races including untouched targets, profile-specific commands, supplied-parameter restrictions, integer/enum checks, expiry, armed/configuration conflicts, idempotent Apply and truthful partial-write failures. Navigation tests cover reported target precedence, coordinate masks, mission sequence offsets, stale/disarmed/manual suppression and geographic projection. Existing saved prompts retain custom content when the fourth interaction prompt is introduced.

Two real Copter SITL sessions were exercised on temporary port 8091 while 8080 remained stopped. A real Ollama multi-target request created distinct drafts (20/30 m on the first, 35 m on the second) and staged LOG_DISARMED only for the first. Both onboard parameter values remained zero until the browser operator clicked Apply. Fresh readback then verified 1 on the first and 0 on the second. The initial model response mislabeled timed loiter as unlimited loiter; the prompt now spells out MAV_CMD names/numbers. A second real inference corrected the item to command 17 without altering the other vehicle. This demonstrates why structured edits remain inspectable; it is not evidence of general planning accuracy.

The corrected mission passed reviewed upload/readback, GUIDED takeoff and AUTO execution. Fresh target telemetry matched the intended waypoint while the copter moved at 3.65 m/s with 20.36 m relative altitude. Chrome inspection during the same flight showed the map stick/cue and an approximately -27° pitch attitude at 9.9 m/s. See [interaction-flight-validation.json](interaction-flight-validation.json). The other copter remained disarmed. The final browser check verified the polished flight instrument, persisted fourth prompt setting, off-by-default interaction switch and suppression of navigation cues during LAND. The temporary test server and its owned simulators were stopped afterward; automatic monitoring remains paused with the saved five-minute interval.

## Settings, geofence and map follow-up

The follow-up implementation passed **44 automated tests** and the production frontend build. New tests cover atomic settings persistence/revision conflicts, endpoint validation, cloud-key origin scoping, effective custom prompts/model selection, local inference and model discovery through the sandbox, denial of other loopback ports, and geofence datum/conflict handling.

Two real Copter SITL sessions reported distinct positions. A 120 m circle and 80 m above-home ceiling were written and independently read back, with `FENCE_TYPE=3`, `FENCE_ALT_MAX_TP=1`, `FENCE_ENABLE=1` and the chosen recovery action. This validates configuration transfer; a new fence-breach flight campaign was not run.

Chrome UI checks verified launching two copters with the count selector, labelled vehicle markers, the amber fence boundary, saving a 42 m waypoint altitude, the editable Settings screen, a five-minute interval save, a prompt edit/save, and the Diagnostics pane. Real Ollama model discovery returned 20 models; the explicit cloud connection test returned valid JSON in 0.87 s. Both the edited prompt and cadence survived an actual backend restart. The test prompt suffix was restored to factory text afterward. Automatic inference remains paused to avoid ongoing usage.

Browser inspection found that MapLibre v6 needed its worker emitted as a separate Vite bundle. Without it, raster imagery and HTML markers rendered but vector overlays did not. The fix follows [MapLibre's Vite setup](https://maplibre.org/maplibre-gl-js/docs/); the fence boundary was then visually confirmed.

`scripts/settings-smoke.py` also passed against the live API with a local response stub: the scheduler used the selected local model/endpoint, settings changes were blocked during an active trial, GPS injection was observed on Rover, cancellation restored the original simulator parameter, and global pause stopped subsequent requests. Four stub requests and zero cloud calls were made; this was a transport/lifecycle test, not an LLM accuracy trial. The previous cloud preferences were restored afterward.

The original release evidence below remains historical; its unavailable-browser statement no longer describes the follow-up checks above.

Local implementation tested on 2026-09-17, macOS Apple Silicon. Firmware is pinned to `dbe792162d06cab66c3475fd5556bf7a120f119e`; Copter, Plane and Rover report 4.7.1. Real inference used Ollama's cloud endpoint and `gpt-oss:120b`. No physical vehicle was operated.

## Application and protocol evidence

- **34 automated tests passed**: mission revisions and typed edits, route/exclusion geometry, altitude frames and intent constraints, profile-specific commands, causal observation filtering, SI normalization, credential guards, macOS worker isolation, model citation validation/repair, command preconditions, ACK/state semantics, parameter conflict/readback, and missing/out-of-order DataFlash chunk repair. Run `.venv/bin/python -m pytest -q`.
- Production TypeScript/Vite build passed. Python lint and dependency consistency passed; the frontend dependency audit reported zero vulnerabilities. The map library accounts for a large bundle; Vite reports a chunk-size advisory.
- Each native simulator completed parameter write with independent readback, reviewed mission upload with download comparison, mode change with state verification, onboard mission download, and log-list requests. API session/origin/mutation-header rejection and authenticated WebSocket updates were exercised.
- The final server was restarted and exercised through launch, trial baseline, and stop. Stopping cancelled the active trial, removed the session and left no running app-owned vehicles; the application still returned HTTP 200.
- Real cloud conversation generated typed draft edits and intent proposals. Concurrent draft revision changes caused stale model edits to be rejected. Review-only model requests cannot apply edits. Deterministic review remains available independently of the provider.
- Real Copter GUIDED takeoff, LAND and automatic disarming passed. Recorded peak relative altitude was 14.928 m. A **4,009,984-byte DataFlash download** matched the exact prefix of the simulator's native onboard file; the native file subsequently appended bytes. This is an advertised-size snapshot, not a claim that the final growing file has the same whole-file hash.
- A separate disarmed log test passed after the final download changes: **405,066 bytes**, native-prefix equality, SHA-256 verification and identical HTTP download. It deliberately supplied an incorrect client size; the gateway correctly used freshly requested onboard metadata. See [log-validation.json](log-validation.json).
- Plane's takeoff mission entered AUTO and reached 14.174 m relative altitude; Rover's mission entered AUTO and reached 1.421 m/s. Native startup checks remained enabled; scripts retried explicit prearm/mode rejections while the estimator initialized. See [flight-validation.json](flight-validation.json).
- App HTML and a satellite tile returned HTTP 200. **No browser automation surface was available**, so visual rendering, map gestures and optional WebMCP browser registration have not received browser acceptance testing. Compile/API checks do not substitute for that work.

## Blind telemetry smoke trials

The final three-profile batch used explicit SI observations, a generic prompt and bounded citation repair. Scenario names, fault parameters, diagnostic strings, deterministic alerts, seeds and injector outputs were excluded from this track. The inference subprocess was denied runtime/secret/Git reads and loopback network access. Tests exercised those denials; cloud inference remained functional.

Each row below had a 60-second observation period after baseline and seeded onset jitter. The three-profile batch used seed 53; the separate airborne Copter trial used seed 71. Prediction files were locked and their hashes verified before report extraction. Scoring was rechecked against timestamped evidence: a symptom mention must cite an observation after onset. Latency is time from completed injection to completed model response, not merely the observation timestamp.

| Vehicle / condition | Phase | Valid assessments | Result | First qualifying response |
|---|---|---:|---|---:|
| Copter nominal | Disarmed | 2 | No concern alerts | — |
| Plane nominal | Disarmed | 2 | No concern alerts | — |
| Rover nominal | Disarmed | 3 | No concern alerts | — |
| Copter battery voltage sag | Disarmed | 2 | Battery symptom reported | 25.30 s |
| Plane battery voltage sag | Disarmed | 2 | Battery symptom reported | 29.24 s |
| Rover battery voltage sag | Disarmed | 2 | Battery symptom reported | 24.37 s |
| Copter GPS loss | Disarmed | 3 | Navigation/GPS symptom reported | 6.60 s |
| Plane GPS loss | Disarmed | 3 | Navigation/GPS symptom reported | 5.12 s |
| Rover GPS loss | Disarmed | 2 | Navigation/GPS symptom reported | 25.33 s |
| Copter motor 1 reduced output | Airborne | 2 | Transient attitude/control disturbance reported | 17.71 s |

The airborne trial began after verified takeoff to approximately 18 m, then reduced one motor's output multiplier to 0.65. The model cited attitude, throttle, descent and vibration changes. It later called the compensated hover nominal while the injected reduction remained active. **This demonstrates detection of a transient disturbance, not reliable persistent motor-failure diagnosis.** Some descriptions were also imprecise, including the timing of arming and GPS terminology.

The seven nominal assessments produced no concern alerts in this final small batch. This is not a false-positive-rate estimate or a held-out accuracy result. The six disarmed fault trials establish telemetry/inference plumbing and observable symptoms, not airborne recovery or crash prevention. Scores are lexical screening and require human incident adjudication. No comparison proving incremental benefit over rules or native warnings has been completed.

The batch reused vehicle sessions, and its inter-trial delay was too short to fully drain the 60-second history window. One early GPS assessment also discussed the preceding voltage event. Post-onset citation checks still qualified the reported symptom detections, but the trials are not independent. The runner now waits 65 seconds between trials; future rigorous evaluation should also reset state, use held-out seeds and test appropriate flight phases.

## Findings retained from earlier iterations

The first raw-unit trial batch generated false concerns on stationary Plane and Rover: the model misinterpreted native units and disarmed navigation targets. Explicit SI field names, normalized values and phase context replaced that contract. A later normalized Rover nominal trial produced no valid assessment because its citations failed validation; it is recorded as **unassessed**, not a successful negative control. One bounded repair attempt now receives the same observations plus the validation error. Invalid original outputs and repair attempts remain in the audit.

These failures motivated changes, so the final smoke batch is development evidence, not an untouched test set. Other configured adapters—wind, RC loss, GPS jump, barometer drift, magnetometer failure and Plane airspeed hold—still require systematic phase-appropriate trials. Long-duration operation, packet-loss campaigns, HIL and physical flight remain unvalidated.

## Reproducibility and artifacts

- [validation-results.json](validation-results.json): ten final trial records, seeds, timestamps, hashes, evidence-qualified screening results and coverage.
- [flight-validation.json](flight-validation.json): observed native simulator motion.
- Local ignored `runtime/copilot/benchmark-1789624667.json` and `airborne-trial.json`: original final run reports. Earlier iterations are retained as `benchmark-1789623663.json` and `benchmark-1789624088.json`.
- Each local session directory retains raw/normalized telemetry, inference input/output audit, native simulator logs and private trial artifacts. These can be downloaded/replayed through the application and are intentionally absent from Git.
- `scripts/integration.py`, `benchmark.py`, `flight-smoke.py`, `airborne-trial.py` and `log-smoke.py` reproduce the relevant workflows against owned SITL sessions. Flight scripts intentionally arm simulators and stop only their own instances.

At the original validation, the key remained in ignored, mode-0600 `.env` and no remote was configured. The application repository has since been published; the key remains local. Git hooks scan for private environment files and the configured credential without printing it. No credential or runtime corpus is included in the committed reports.
