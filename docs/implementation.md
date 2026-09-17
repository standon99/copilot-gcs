# Implementation and operating boundaries

The repository now contains a local research ground station, native Copter/Plane/Rover SITL integration, and live Ollama inference. The original [design](design.md) remains the broader design baseline. This document describes the actual implementation rather than treating every proposed acceptance target as achieved.

## Run

Start `./start.sh`, then open `http://127.0.0.1:8080`. The production React bundle is served by the same FastAPI origin. Launch simulators from the vehicle bar. Each simulator has its own directory, MAVLink connection, TCP port, RC-input UDP port, gateway process, observation history, mission draft, and command queue. The system deliberately supports overlapping MAVLink system IDs on **separate** connections.

The API binds to loopback. Native SITL's TCP/RC listeners use ArduPilot's normal network binding behavior; this is a local development machine setup, not a hardened network appliance. External loopback MAVLink connections are inspectable but vehicle writes are restricted to simulators launched by this app.

## Implemented workflows

| Area | Actual behavior |
|---|---|
| Live operations | Selected-vehicle artificial horizon and flight instrument, fresh autopilot-target stick and labelled projected navigation-bearing carrot; concurrent vehicle selection, mode/armed state, relative altitude, ground/air speed, battery, GPS, attitude data, freshness coverage, status messages, satellite/street map, selected vehicle position and mission overlays |
| Parameters | Full discovery with missing-index repair on refresh; search; pinned-firmware descriptions/ranges/enums/bitmasks; staged JSON import/export; disarmed writes with fresh old-value conflict detection, type checks, echo and separate readback; sequential bulk journal |
| Missions | Map clicks and dragging; waypoint table; relative-home/AMSL frames; supported commands per profile; JSON import/export; onboard download; immutable draft revisions, optimistic concurrency, undo; deterministic route/constraint checks; explicit reviewed upload and readback; separate arming/start |
| Conversational planning | Real cloud model inference; canonical draft and operational observations in context; typed add/update/remove/reorder patches only; review-only mode rejects patches; before/after cards; stale-revision rejection; no vehicle-write tools |
| Multi-vehicle interaction | Main-page opt-in switch and explicit target allowlist; all responses validated before any draft mutation; profile/revision/session guards; model parameter proposals expire after five minutes and require manual disarmed Apply; old-value conflicts, independent readback and partial-write journal |
| Intent | Optional brief; model-proposed interpretation that requires explicit acceptance into the draft; altitude bounds with a datum, maximum ground speed, route corridor, exclusion polygons, required mission-command order, and unresolved clauses; active intent pinned to the uploaded version |
| Monitoring | Independent rules plus evidence-citing model assessments, availability/error states, operational and telemetry-only tracks, one in-flight assessment per vehicle, separately reserved monitor/planner concurrency, finite provider deadlines |
| Settings | Persistent installation preferences for model, OpenAI-compatible endpoint, assessment interval/global pause, timeout and all four prompts; model discovery and explicit connection test; available without a vehicle; optimistic settings revisions |
| Onboard fence | Disarmed circle/ceiling parameter editor with explicit above-home ceiling datum, profile-specific breach actions, conflict checks, sequential readback and enable-last behavior; configured boundary displayed on map |
| Logs | Raw MAVLink tlog, normalized JSONL, SQLite audit, exact successful model-visible observation/prediction records, onboard LOG_* listing/download with gap retries, historical map/altitude replay with a causal cursor and no write route |
| SITL lab | Nominal, GPS loss/jump, battery sag, RC loss, wind, barometer drift, magnetometer failure; Copter reduced motor output; Plane held airspeed; baseline/jitter/observation/restoration lifecycle; seed/repeat CLI; locked prediction hash followed by result disclosure |

Supported mission commands are waypoint (16), unlimited/timed loiter (17/19), return home (20), ground-speed change (178), plus takeoff/land (22/21) for aerial profiles. Command-specific parameters remain visible in the editor. Relative-terrain missions are blocked because terrain coverage is not implemented. Frame/coordinate comparisons apply to navigational fields; ArduPilot normalization of unused return-home/speed fields is handled explicitly. Legacy MISSION_REQUEST receives MISSION_ITEM_INT, as specified by the [MAVLink mission protocol](https://mavlink.io/en/services/mission.html).

## Interaction and display contracts

`POST /api/interaction` accepts an enabled flag, explicit session IDs and an operator message. Each selected vehicle gets its own canonical draft, live state, recent conversation and a bounded metadata catalog of up to 40 relevant parameters (simulator parameters excluded). Responses cannot address another vehicle, introduce unsupported commands, change mission intent, or write to the gateway. The entire batch validates before local drafts or proposals change. Target sessions, epochs and draft revisions are checked again after inference, including targets for which the response makes no edits.

Parameter proposals are session-bound, finite-lived records. A separate operator Apply endpoint checks control ownership, disarmed state, epoch, expiry, metadata and expected current values; each queued write also checks fresh telemetry and independently reads the value back. Repeated Apply on a verified proposal is idempotent; failed or expired proposals require a new proposal. Configuration writes and arming are interlocked during a proposal batch. This is sequential verified application, not an atomic autopilot transaction. Audit events retain proposals and results; pending proposals are intentionally not restored across application restarts.

Map cues use `POSITION_TARGET_GLOBAL_INT`, `NAV_CONTROLLER_OUTPUT`, and the verified mission snapshot/`MISSION_CURRENT` offset (home occupies sequence zero). Unsupported frames, masked horizontal coordinates, old observations and non-navigation modes suppress targets. The orange point is a bounded projection of the reported navigation bearing, separate from the autopilot-reported position target. The artificial horizon uses native ATTITUDE radians converted to display degrees; stale instruments are explicitly unavailable. No inference is involved in rendering these instruments.

## Operational semantics

The browser holds a renewable 30-second write lease. Closing it stops lease renewal; the gateway continues GCS heartbeats and monitoring. The configured GCS source system is 255. A queued request expires after 30 seconds and is tied to a boot epoch. The gateway rechecks freshness, disarmed-only conditions and relevant control preconditions before execution. No reconnect automatically replays a command.

A command's `accepted` result means the autopilot acknowledged it. `verified` means the specific protocol/state check passed: mode/armed heartbeat, parameter readback, or mission download comparison. Takeoff acknowledgement does not by itself prove the requested altitude was reached. Timeout errors state that completion may be unknown; inspect telemetry and audit before issuing another action.

Draft edits do not alter the onboard mission. Mission upload remains disarmed-only. The executing mission and intent remain pinned while the operator creates later drafts. Relative altitude intent is anchored to the reviewed home; a moved home is reported. Cruise minimum-altitude checks exclude landing/return contexts and report missing flight-phase evidence.

The initial monitor cadence is **20 seconds after each completed assessment**, configurable from 10 seconds to 24 hours in Settings. This installation has been saved with a five-minute interval and global automatic inference paused. Requests time out after 45 seconds by default (also configurable). The UI exposes observation age and assessment availability; it does not promise continuous model attention. Numerical rules continue during inference outages. No latency or detection-accuracy target is certified by this implementation.

## Inference and secret boundaries

The key is loaded only on the backend from ignored `.env`, which has mode `0600`. It is not sent to the browser, placed in prompts, recorded in audit payloads, or committed. The application repository is published at `https://github.com/standon99/copilot-gcs`; publishing does not include `.env`, runtime data or the separate ArduPilot checkout. No push is needed to run the app.

Inference uses one-shot Python subprocesses and anonymous pipes. On this Mac, `sandbox-exec` denies reads of `.env`, `.git`, the entire runtime tree and the ArduPilot checkout, denies filesystem writes, and denies outbound loopback network connections. The worker receives only the selected prompt/payload plus the credentials needed to contact the configured provider. It has no dynamic tools, shell evaluator, vehicle client, injector, or application session cookie. Cloud responses are parsed as JSON and validated in the parent; monitor citations must refer to supplied evidence IDs. On other platforms the UI explicitly reports that this filesystem sandbox is unavailable.

When a local inference URL is explicitly selected, the sandbox permits only that loopback TCP port; other loopback services remain denied. The ground station's own port cannot be selected. The stored cloud credential is scoped to its original HTTPS provider origin and is never forwarded to local or alternate endpoints. Prompts are editable and persisted, while the application's response validators and vehicle-write restrictions remain independent of prompt text. Each assessment records the effective prompt hash and settings revision.

The blind telemetry track excludes simulator messages, **all** parameters, STATUSTEXT, estimator/health diagnostic flags, deterministic rule labels, scenario names, seeds, injection events and ground truth. It also strips the mission brief, unresolved free-text clauses and custom waypoint identifiers to avoid accidentally passing operator-written scenario hints. Structured approved mission constraints remain. The operational track adds normal autopilot status messages, mission text and rule findings and is scored separately. Model prompts are generic across nominal and fault runs. Static knowledge of ArduPilot failure behavior is allowed; telling the model which scenario is running is not.

Model-facing observations use explicit SI field names, with native records retained as evidence. GPS DOP values and EKF innovation ratios are dimensionless. The pinned Plane firmware's airspeed-error scaling quirk is corrected from its source implementation. A schema/evidence error gets at most one repair attempt within the original total deadline; rejected outputs and successful repairs are retained in the inference audit. Repair prompts contain only the same observations and the schema error, never injector information.

Trial prediction files are created once, made read-only and hashed before scenario results are disclosed. This is local reproducibility protection, not tamper-proof remote attestation. The operator owns the machine and can inspect the private artifacts.

The symptom scorer requires a matching incident with a citation timestamp at or after injection and at or before that assessment's observation cutoff. Runs with no valid assessment are unassessed. The CLI now waits 65 seconds between trials to drain the 60-second observation window; this does not reset all vehicle state or establish independent experimental repetitions.

DataFlash downloads refresh the onboard log's advertised size, stream bounded windows, retry missing byte ranges, and publish a file only after every advertised byte arrives. A SHA-256 digest accompanies the result. This verifies the advertised-size snapshot; an active onboard log can append bytes afterward.

## Limits that remain explicit

- This is an implemented SITL research tool, not full Mission Planner parity or validation for physical flight. Firmware flashing, calibration wizards, joystick/continuous setpoints, arbitrary mission commands, MAVFTP, onboard polygon-fence uploads, terrain/obstacle/airspace validation, and additional airframes are outside this release.
- Fixed-wing turn/climb/landing performance and energy/endurance are reported as unverified. Groundspeed bounds are supported; airspeed bounds, terrain clearance, payload completion and arbitrary natural-language requirements are retained as unresolved where the numerical schema cannot express them.
- Satellite tiles require network access and follow provider attribution/usage terms. The mission overlay is independent of tile availability. Exclusion polygons are editable as coordinate JSON; a dedicated polygon-drawing gesture is not implemented.
- Normalized recordings and raw tlogs each stop at 256 MiB per session with visible recording state. Audit/inference/benchmark artifacts have no automatic deletion policy. The operator manages disk retention under `runtime/copilot/`.
- The current UI displays the latest assessment and preserves previous results in logs. It does not yet provide a complete incident acknowledgement/escalation workflow or automatic cross-vehicle conflict analysis.
- Stored draft revisions remain in SQLite/audit, while live session identities are intentionally recreated on restart. Export mission JSON before terminating a session to conveniently reuse it in a new one.
- Trial scoring is **lexical symptom screening**, separately labeled. A keyword match is not adjudicated diagnosis or a calibrated confidence. Disarmed GPS/battery trials test observation plumbing; motor/wind/motion scenarios need appropriate airborne/driving phases. No held-out accuracy percentage is claimed.
- This release has automated protocol, planning, isolation and API tests plus real SITL/provider tests. A full packet-loss/HIL campaign, all fault adapters in all flight phases, sustained endurance tests and manual browser acceptance remain separate validation work.
- Optional WebMCP tools expose telemetry reads and reversible local draft staging only; their registration remains unverified. A subsequent Chrome pass verified the main map, waypoint altitude edits, settings persistence and diagnostics UI, and fixed the missing MapLibre v6 worker bundle that prevented vector overlays from rendering.

See [validation.md](validation.md) for the concrete evidence from this installation.
