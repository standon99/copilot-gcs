# Implementation and operating boundaries

Copilot GCS is an AI-enabled web ground control station for simple waypoint flights and inspections, with Copter/Plane/Rover support and live Ollama inference. The original [design](design.md) remains the broader design baseline. This document describes the actual implementation rather than treating every proposed acceptance target as achieved.

The project icon is shared by the app header, browser favicon and README. Vector
and PNG assets plus a GitHub social-preview image are described in [brand assets](brand/README.md).

## Run

Start `./start.sh`, then open `http://127.0.0.1:8080`. The production React bundle is served by the same FastAPI origin. Launch simulators from the vehicle bar. Each simulator has its own directory, MAVLink connection, TCP port, RC-input UDP port, gateway process, observation history, mission draft, and command queue. The system deliberately supports overlapping MAVLink system IDs on **separate** connections.

The API binds to loopback. Native SITL's TCP/RC listeners use ArduPilot's normal network binding behavior; this is a local development machine setup, not a hardened network appliance. External loopback MAVLink connections are inspectable but vehicle writes are restricted to simulators launched by this app.

## Flight workspace

The start page connects telemetry or launches simulators, with an optional brief
and profile-specific task starters. Launching does not invoke the model.
**Flight** keeps instruments and contextual controls beside a map with
**Live map / Plan mission** views. Chat, Alerts and Watch rules occupy distinct
right-panel tabs. Numerical findings live with the plan rather than persisting
inside the conversation. Plain functional labels replace the earlier step strip. Project name, connection
symbol and model share a compact pill in the vehicle bar, without a separate
full-width header.

Chat uses right-aligned user bubbles and left-aligned replies. A local pending
message appears immediately, reconciles with the server without duplication,
and belongs only to the vehicles selected when sent. Running server state keeps
the waiting bubble and Stop available after reload; completion, failure or
cancellation removes it. Model-request counts and tool traces are collapsed
behind Activity/Reply details. The UI follows new messages unless the reader has
scrolled up. Replies arrive whole; there is no token streaming.

Assistant text uses pinned `react-markdown` 10.1.0 for paragraphs, emphasis,
lists and code. Raw HTML is skipped, no raw-HTML plugin is enabled, links use the
renderer’s URL filtering and open with `noopener noreferrer`, and model-written
images render as text rather than fetching external resources. This is separate
from operator-attached map images. Error and user messages remain plain text.

**Check draft / Recheck** runs numerical review without inference.
**Ask AI to review** also appends a model assessment to chat. Upload remains an
explicit reviewed action. Flight controls then offers separate control access,
profile-specific launch mode, arming and mission start. Manual controls remain
available in an expandable section.

## Implemented workflows

| Area | Actual behavior |
|---|---|
| Live operations | Selected-vehicle artificial horizon and flight instrument, fresh autopilot-target stick and labelled projected navigation-bearing carrot; concurrent vehicle selection, mode/armed state, relative altitude, ground/air speed, battery, GPS, attitude data, freshness coverage, status messages, satellite/street map, selected vehicle position and mission overlays |
| Parameters | Full discovery with missing-index repair on refresh; search; pinned-firmware descriptions/ranges/enums/bitmasks; staged JSON import/export; disarmed writes with fresh old-value conflict detection, type checks, echo and separate readback; sequential bulk journal |
| Missions | Map clicks and dragging; waypoint table; relative-home/AMSL frames; supported commands per profile; JSON import/export; onboard download; immutable draft revisions, optimistic concurrency, undo; deterministic route/constraint checks; explicit reviewed upload and readback; separate arming/start |
| Conversational planning | Native multi-step function calls; typed working-copy edits, numerical validation, tool action/results trace and cancellation; guarded final local commit, Undo; read-only mode removes edit tools; no vehicle-write tools |
| Multi-vehicle interaction | AI planning enabled by default, with a main-page toggle and explicit vehicle targets; all responses validated before any draft mutation; profile/revision/session guards; model parameter proposals expire after five minutes and require manual disarmed Apply; old-value conflicts, independent readback and partial-write journal |
| Intent | Optional brief; model-proposed interpretation that requires explicit acceptance into the draft; altitude bounds with a datum, maximum ground speed, route corridor, inclusion/exclusion polygons with overlap/union semantics, required mission-command order, and unresolved clauses; active intent pinned to the uploaded version |
| Monitoring | Independent rules plus evidence-citing model assessments, availability/error states, operational and telemetry-only tracks, visible operator/AI-proposed watch rules with event-triggered advice, independent periodic/event switches, shared persisted automatic request spacing, model-configurable per-vehicle focus/cadence, finite tool-loop/provider deadlines |
| Settings | Persistent installation preferences for model, OpenAI-compatible endpoint, periodic/watch switches, default cadence and hard automatic spacing, bounded chat rounds/output, timeout and saved prompts including the native agent prompt; model discovery and explicit connection test; available without a vehicle; optimistic settings revisions |
| Onboard fence | Map-drawn inclusion/exclusion areas, separate verified MAVLink2 polygon-bank upload/clear, plus circle/ceiling settings; profile breach actions, conflict checks, disarmed guards and enable-last behavior |
| Logs | Raw MAVLink tlog, normalized JSONL, SQLite audit, exact successful model-visible observation/prediction records, onboard LOG_* listing/download with gap retries, historical map/altitude replay with a causal cursor and no write route |
| Simulation diagnostics | Nominal, GPS loss/jump, battery sag, RC loss, wind, barometer drift, magnetometer failure; Copter reduced motor output; Plane held airspeed; baseline/jitter/observation/restoration lifecycle; seed/repeat CLI; locked prediction hash followed by result disclosure |

Supported mission commands are waypoint (16), unlimited/timed loiter (17/19), return home (20), ground-speed change (178), plus takeoff/land (22/21) for aerial profiles. Command-specific parameters remain visible in the editor. Relative-terrain missions are blocked because terrain coverage is not implemented. Frame/coordinate comparisons apply to navigational fields; ArduPilot normalization of unused return-home/speed fields is handled explicitly. Legacy MISSION_REQUEST receives MISSION_ITEM_INT, as specified by the [MAVLink mission protocol](https://mavlink.io/en/services/mission.html).

Timed loiter's default direction is verified against the pinned firmware's
canonical readback (`p3=0` becomes `+1`). Duration, position, altitude, explicit
radius/direction and all other fields remain checked; this is not a general
normalization bypass. See the pinned [ArduPilot mission conversion](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_Mission/AP_Mission.cpp#L1664).

## Interaction and display contracts

`POST /api/interaction` starts a bounded native function-call loop over selected
session IDs. Typed tools read state, edit a working copy, validate the final
mission, propose parameters/fences and configure requested advisory watches or
monitoring. Results and validation errors return to the model for subsequent
rounds. The model ends with conversational text. The complete
[contract and tools](ai-interface.md) are exposed at `/api/ai/capabilities`.

All selected session identities, boot epochs, draft/watch/monitor revisions and
settings revision are checked throughout the turn and before commit. A conflict,
provider failure, cancellation, deadline or round limit discards staged changes.
Successful draft edits become one visible version. No await occurs between final
guards and the local batch commit; disk failure there is reported as an
interrupted commit requiring workspace inspection, not an atomic rollback.
The public trace contains tool arguments/results, never private reasoning.
Initial public context, effective system text, schemas and full bounded tool
results are audited; image bytes are excluded. Review-only turns expose only
reads. There is no tool for upload, flight, connections or fault injection.

Parameter proposals are session-bound, finite-lived records. A separate operator Apply endpoint checks control ownership, disarmed state, epoch, expiry, metadata and expected current values; each queued write also checks fresh telemetry and independently reads the value back. Repeated Apply on a verified proposal is idempotent; failed or expired proposals require a new proposal. Configuration writes and arming are interlocked during a proposal batch. This is sequential verified application, not an atomic autopilot transaction. Audit events retain proposals and results; pending proposals are intentionally not restored across application restarts.

Map cues use `POSITION_TARGET_GLOBAL_INT`, `NAV_CONTROLLER_OUTPUT`, and the verified mission snapshot/`MISSION_CURRENT` offset (home occupies sequence zero). Unsupported frames, masked horizontal coordinates, old observations and non-navigation modes suppress targets. The orange point is a bounded projection of the reported navigation bearing, separate from the autopilot-reported position target. The artificial horizon uses native ATTITUDE radians converted to display degrees; stale instruments are explicitly unavailable. No inference is involved in rendering these instruments.

## Inclusion/exclusion areas and vision interface

See [AI interface](ai-interface.md) for the machine-readable catalog, native
function-call contract, proposal example and optional WebMCP distinction.
The catalog lives at /api/ai/capabilities and derives its argument schemas from
the live validators. Geographic or map-pixel proposals create no draft change
until acceptance checks the proposal ID, draft revision and boot epoch.

Map images are operator-attached PNGs only, bounded in dimensions/size, stamped
with draft/vehicle/time and Web Mercator bounds. The browser resets bearing/tilt,
adds pixel coordinates and attribution, and exposes a thumbnail before sending.
The server converts pixel polygons and rejects invalid geometry. Settings and
Chat check optional Ollama model metadata on the configured origin; known
text-only models cannot send map attachments, and vision models without tools
cannot run image editing turns. Unknown compatible-provider capabilities remain
usable and are labelled unknown. The worker classifies HTTP failures with fixed
messages, without reflecting provider bodies. Metadata caches are scoped to
endpoint/model, with bounded timeouts and no inference. Models without vision
can use geographic coordinates; no model is selected automatically.
Only planning receives the attachment; monitoring/trials are unchanged.

Fence-bank download and upload use MAV_MISSION_TYPE_FENCE=1; regular missions
remain type 0. Request, item and ACK matching is type-specific; fence item zero
is a real vertex, not synthetic home. Inclusion command 5001 and exclusion command 5002 carry each ring's
vertex count. FENCE_OPTIONS bit 1 (value 2) chooses inclusion union; clearing it
requires intersection. Other option bits are preserved and read back. Upload is capped at 70 total vertices and checks quantized geometry.
Existing unsupported bank types block replacement. Fresh onboard items and
parameters must match the operator's loaded snapshot before mutation.

The gateway disables fencing while disarmed, writes and downloads the bank,
then verifies type/action/auto-enable settings and enables last. A partial failure
reports a journal and invalidates the cached bank; the operator must reload.
Circle/altitude selections are preserved. Clearing removes the polygon type
and disables fencing if no other type remains. Displayed bank geometry is a
last-read snapshot, not a continuously synchronized external-edit feed.

The numerical review rejects explicit straight segments outside the inclusion
region or intersecting exclusions, including home-to-first and RTL-to-home. It
requires home, blocks boundary contact, empty overlap and gaps between disjoint
union areas. It does not validate loiter radius, curved turns or vehicle avoidance.
Breach response is the configured autopilot behavior, not an app route planner.

LAND command 21 with default p4=0 accepts the pinned firmware's +1 readback
(the deepstall direction sign representation). All other land fields and
nondefault direction still require agreement. This is separate from the existing
timed-loiter p3 default normalization.

## Operator watch engine

`backend/watches.py` validates a finite rule language (up to 20 per session): one
allowlisted metric, less/greater comparator, finite SI threshold, always/armed/
airborne scope, dwell, hysteresis/reset margin, repeat cooldown and severity. The
AI cannot submit code or commands. It can enable explicitly requested advisory
rules; manual additions start disabled. Operator CRUD,
Enable/Disable and Acknowledge use `/api/vehicles/{id}/watches` with optimistic
watch revisions. AI batches validate all target session/epoch/draft/watch
revisions before applying local proposals. Manual editing disables a rule for review. Rules include a local-only/event-advice
choice and an optional per-rule AI prompt. Absolute yaw rate and windowed relative
altitude change are supported; missing/gapped history stays unknown.
Notes and configuration are stored in SQLite/audit; new sessions start empty.

The gateway requests distance, terrain and extended flight-state messages; their
absence is unknown. The 20 Hz backend pump evaluates fresh samples (at most 3 s
old). This is application scheduling, not a real-time safety guarantee. A latched
red card survives condition clearance until acknowledged; an active violation
stays red after acknowledgement. Data gaps reset dwell without retriggering an
already active breach. Reboots disable rules, clear queued events and require
operator re-enable. No watch has a vehicle-write route.

The first event bypasses the normal monitoring interval. Events are bounded to
one pending entry per rule, combined during an in-flight request, and subject to
a configurable per-vehicle minimum spacing (10–3,600 s; default 60). Independent global/per-vehicle event switches suppress calls; periodic pause
does not. The installation-wide automatic spacing also applies across all vehicles
and attempted repairs, with persisted reservations including failures/cancellation.
Selection happens after evaluating every vehicle: oldest eligible watch events
first, then the oldest due periodic assessment, avoiding insertion-order starvation. New
suppressed events are not replayed when monitoring resumes. Local alerts remain.
Event assessments include the exact triggering samples, even if normal
five-second downsampling would discard them. Evidence IDs, effective prompts,
trigger details and results are audited. Model latency/quota availability still
apply; “immediate” means eligible without waiting for the periodic interval.

AGL accepts a fresh downward DISTANCE_SENSOR reading strictly inside its reported
range and not marked invalid, with fresh ATTITUDE and roll/pitch within 20°; the
beam is projected vertically. Otherwise it uses AMSL minus fresh terrain height
only when TERRAIN_REPORT has nonzero spacing and its coordinates are within
min(30 m, half the grid spacing) of the vehicle estimate. Missing/nonfinite/stale
inputs return unknown. No relative-home fallback or terrain download service is
provided. Ground-surface estimates do not establish obstacle clearance.

All custom context and event-driven cadence are disabled during Diagnostics
trials; the default Settings cadence and hard cap apply, then the previous
per-vehicle configuration is restored. This applies to all trials, including operational trials; ordinary operational autopilot diagnostics
remain as before. The telemetry-only track always excludes custom notes, rule
labels and triggers. Trial edits are locked, including an AI response that
returns after a trial starts. The deterministic pane remains visible to the
operator independently of blinded inference.

Initial map positions wait for a fresh 3D GPS fix followed by a global-position
sample. This fixes Plane's pre-fix drift around 0°,0° without rejecting legitimate
coordinates at that location. Position initialization resets with boot epoch;
initialized dead-reckoning positions can remain during later GPS loss and are
visually degraded. Replay routes omit pre-initialization position samples.

## Operational semantics

**Enable vehicle controls** gives the browser a renewable 30-second write lease. It does not arm or start the vehicle. Mission versions use plain “Version” labels and upload explains missing prerequisites. The numerical-review hash excludes only STAT_RUNTIME, STAT_FLTTIME and STAT_BOOTCNT; configuration values and mission-count changes still invalidate review. Home/epoch checks remain independent. Closing it stops lease renewal; the gateway continues GCS heartbeats and monitoring. The configured GCS source system is 255. A queued request expires after 30 seconds and is tied to a boot epoch. The gateway rechecks freshness, disarmed-only conditions and relevant control preconditions before execution. No reconnect automatically replays a command.

A command's `accepted` result means the autopilot acknowledged it. `verified` means the specific protocol/state check passed: mode/armed heartbeat, parameter readback, or mission download comparison. Takeoff acknowledgement does not by itself prove the requested altitude was reached. Timeout errors state that completion may be unknown; inspect telemetry and audit before issuing another action.

Draft edits do not alter the onboard mission. Mission upload remains disarmed-only. The executing mission and intent remain pinned while the operator creates later drafts. Relative altitude intent is anchored to the reviewed home; a moved home is reported. Cruise minimum-altitude checks exclude landing/return contexts and report missing flight-phase evidence.

The initial monitor cadence is **20 seconds after each completed assessment**, configurable from 10 seconds to 24 hours in Settings. Effective cadence is clamped to the operator-owned shared automatic spacing (default 60 s). Periodic and watch-event advice have independent switches. Requests time out after 45 seconds by default (also configurable). The UI exposes observation age and assessment availability; it does not promise continuous model attention. Numerical rules continue during inference outages. No latency or detection-accuracy target is certified by this implementation.

## Inference and secret boundaries

The key is loaded only on the backend from ignored `.env`, which has mode `0600`. It is not sent to the browser, placed in prompts, recorded in audit payloads, or committed. The application repository is published at `https://github.com/standon99/copilot-gcs`; publishing does not include `.env`, runtime data or the separate ArduPilot checkout. No push is needed to run the app.

Inference uses one-shot Python subprocesses and anonymous pipes. On this Mac, `sandbox-exec` denies reads of `.env`, `.git`, the entire runtime tree and the ArduPilot checkout, denies filesystem writes, and denies outbound loopback network connections. The worker receives only the selected prompt/payload plus the credentials needed to contact the configured provider. It has no tool executor, shell evaluator, vehicle client, injector, or application session cookie. Native function arguments are validated/executed only by the parent against working copies. Assessment responses are parsed as JSON; monitor citations must refer to supplied evidence IDs. On other platforms the UI explicitly reports that this filesystem sandbox is unavailable.

When a local inference URL is explicitly selected, the sandbox permits only that loopback TCP port; other loopback services remain denied. The ground station's own port cannot be selected. The stored cloud credential is scoped to its original HTTPS provider origin and is never forwarded to local or alternate endpoints. Prompts are editable and persisted, while the application's response validators and vehicle-write restrictions remain independent of prompt text. Each assessment records the effective prompt hash and settings revision.

The blind telemetry track excludes simulator messages, **all** parameters, STATUSTEXT, estimator/health diagnostic flags, deterministic rule labels, scenario names, seeds, injection events and ground truth. It also strips the mission brief, unresolved free-text clauses and custom waypoint identifiers to avoid accidentally passing operator-written scenario hints. Structured approved mission constraints remain. The operational track adds normal autopilot status messages, mission text and rule findings and is scored separately. Model prompts are generic across nominal and fault runs. Static knowledge of ArduPilot failure behavior is allowed; telling the model which scenario is running is not.

Model-facing observations use explicit SI field names, with native records retained as evidence. GPS DOP values and EKF innovation ratios are dimensionless. The pinned Plane firmware's airspeed-error scaling quirk is corrected from its source implementation. A schema/evidence error gets at most one repair attempt within the original total deadline and shared automatic cap; rejected outputs and successful repairs are retained in the inference audit. Repair prompts contain only the same observations and the schema error, never injector information.

Trial prediction files are created once, made read-only and hashed before scenario results are disclosed. This is local reproducibility protection, not tamper-proof remote attestation. The operator owns the machine and can inspect the private artifacts.

The symptom scorer requires a matching incident with a citation timestamp at or after injection and at or before that assessment's observation cutoff. Runs with no valid assessment are unassessed. The CLI now waits 65 seconds between trials to drain the 60-second observation window; this does not reset all vehicle state or establish independent experimental repetitions.

DataFlash downloads refresh the onboard log's advertised size, stream bounded windows, retry missing byte ranges, and publish a file only after every advertised byte arrives. A SHA-256 digest accompanies the result. This verifies the advertised-size snapshot; an active onboard log can append bytes afterward.

## Limits that remain explicit

- The current release supports simulator control and external telemetry monitoring. Physical flight has not been validated, and full Mission Planner parity is not implemented. Firmware flashing, calibration wizards, joystick/continuous setpoints, arbitrary mission commands, MAVFTP, circular fence-bank editing, terrain/obstacle/airspace validation, and additional airframes are outside this release.
- Fixed-wing turn/climb/landing performance and energy/endurance are reported as unverified. Groundspeed bounds are supported; mission-level airspeed bounds, planned terrain clearance, payload completion and arbitrary natural-language requirements are retained as unresolved where the numerical schema cannot express them.
- Satellite tiles require network access and follow provider attribution/usage terms. The mission overlay is independent of tile availability. Inclusion/exclusion polygons support map drawing, vertex dragging, removal, undo and coordinate JSON. Curved flight paths and automatic detouring are not checked.
- Normalized recordings and raw tlogs each stop at 256 MiB per session with visible recording state. Audit/inference/benchmark artifacts have no automatic deletion policy. The operator manages disk retention under `runtime/copilot/`.
- The current UI displays the latest assessment and preserves previous results in logs. It provides acknowledgement for custom watch alerts but not a complete incident escalation workflow or automatic cross-vehicle conflict analysis.
- Stored draft revisions remain in SQLite/audit, while live session identities are intentionally recreated on restart. Export mission JSON before terminating a session to conveniently reuse it in a new one.
- Trial scoring is **lexical symptom screening**, separately labeled. A keyword match is not adjudicated diagnosis or a calibrated confidence. Disarmed GPS/battery trials test observation plumbing; motor/wind/motion scenarios need appropriate airborne/driving phases. No held-out accuracy percentage is claimed.
- This release has automated protocol, planning, isolation and API tests plus real SITL/provider tests. A full packet-loss/HIL campaign, all fault adapters in all flight phases, sustained endurance tests and manual browser acceptance remain separate validation work.
- Optional WebMCP tools expose telemetry reads and reversible local draft staging only; their registration remains unverified. A subsequent Chrome pass verified the main map, waypoint altitude edits, settings persistence and diagnostics UI, and fixed the missing MapLibre v6 worker bundle that prevented vector overlays from rendering.

See [validation.md](validation.md) for the concrete evidence from this installation.
