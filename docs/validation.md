# Validation record

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

The key remains in ignored, mode-0600 `.env`; no remote is configured. Git hooks scan for private environment files and the configured credential without printing it. No credential or runtime corpus is included in the committed reports.
