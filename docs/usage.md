# Using Copilot GCS

[Project overview](../README.md)

## Using the app

### Waypoints, altitude and deployment

1. Select the intended vehicle tab. In **Mission**, click the map to add points or drag an existing point.
2. Edit each row's **Altitude m** and **Reference**. **Relative home** means metres above the vehicle's home; **AMSL** means metres above mean sea level. Press Enter or leave the field to save. Terrain-relative missions are blocked because terrain coverage is not implemented.
3. Use supported commands: waypoint (16), unlimited/timed loiter (17/19), return home (20), ground-speed change (178), and takeoff/land (22/21) for aerial vehicles. Rover has no aerial takeoff/land commands.
4. Optionally import a checked example from [`examples/`](../examples/). Its coordinates are at the Canberra SITL site; adapt them for another location.
5. **Check plan** attaches numerical checks and requests a real model review. Resolve blockers and inspect warnings/unknowns.
6. **Claim control**, then **Upload reviewed revision** in the copilot panel. Upload is disarmed-only and verifies an onboard readback. A later draft edit does not change the active mission.
7. Arm and start separately. Copter supports GUIDED takeoff; Plane requires an appropriate takeoff mission; Rover executes ground navigation. Native autopilot prearm checks remain enabled.

### LLM interaction and parameter changes

Turn on **LLM interaction mode** in the main bar, check allowed targets, and write in the copilot chat. Use a displayed vehicle ID when instructions differ between copters. For example, replacing the sample ID with a current one:

> For copter ab12cd, add a waypoint at -35.3623, 149.16523 at 30 m above home, followed by unlimited loiter. Stage LOG_DISARMED=1 for that copter. Leave the other copter unchanged.

Requested waypoint changes revise local drafts, with before/after inspection and undo. The application validates the complete multi-target response before changing drafts. An unselected target, reboot or conflicting draft revision rejects the response.

Parameter requests create cards containing vehicle, exact parameter, old/new values and reason. **Claim control → Apply to [ID]** writes to a disarmed owned simulator and verifies readback. Proposals expire after five minutes and are invalid after reboot or conflicting changes. A failed batch stops; earlier verified writes remain applied and are recorded in its results.

The interaction switch starts off on each page load. With it off, chat is review-only unless **Allow requested draft edits** is enabled. Editing prompts never grants upload, arm, mode, takeoff, mission-start or failure-injection authority to the model.

### Mission intent and operator-error checks

Open **Mission intent & operating constraints** and describe what the operation should achieve. For example:

> During cruise, stay between 25 and 40 metres above home, stay below 6 m/s ground speed, and return home when finished. Takeoff and landing may be below the cruise floor.

**Interpret statement with copilot** proposes structured constraints. Inspect the altitude datum, phase exceptions and unresolved clauses, then accept the proposal into the draft. Upload pins that reviewed intent to the active revision. Supported numerical checks compare actual behavior with those constraints; free-text intent is not automatically a comprehensive safety monitor.

### Geofence

In **Mission → Onboard geofence**, claim control while disarmed, choose **Enable onboard fence**, enter radius and optional maximum altitude above home, select the breach action, then **Apply onboard fence**. The configured circle appears as an amber dashed boundary; use zoom/fit controls if it is outside the viewport.

The editor configures a home-centred circle plus optional ceiling, sets the ceiling datum explicitly, and reads settings back. It replaces fence-type selection and disables automatic enable-on-flight behavior. It does not upload polygon fences. Mission-intent exclusion polygons are separate advisory constraints. [ArduPilot geofence reference](https://ardupilot.org/copter/docs/common-geofencing-landing-page.html).

### Map, flight instrument and multiple copters

Choose a profile and a count in the launch bar. Up to six sessions may run together, including mixed profiles. App-owned instances start at separate nearby positions and have separate TCP/RC ports. The selected vehicle is teal, other vehicles amber, and stale markers are dimmed. Click a marker/tab to select it, **Locate vehicle** to centre it, or **Fit all** to see the group.

The artificial horizon follows the selected vehicle and converts its attitude telemetry to display degrees. Stale/missing readings are blanked; unavailable attitude is labelled after three seconds without fresh data.

During supported navigation modes, a gold stick/target ring uses fresh autopilot position-target telemetry, falling back to the verified uploaded mission item in AUTO. The orange diamond is a **projected navigation-bearing cue** placed 5–50 m ahead for readability, not the autopilot's internal look-ahead point. Cues disappear when arming/mode/freshness requirements are not met. These displays consume no LLM calls. [MAVLink target message definition](https://mavlink.io/en/messages/common.html#POSITION_TARGET_GLOBAL_INT).

### Parameters, logs and external connections

**Parameters** supports search, metadata, staged single/bulk changes and import/export. **Logs** exposes recorded telemetry, historical replay and onboard DataFlash transfer. Simulator fault parameters use the separate laboratory rather than ordinary parameter writes.

**Settings → Read-only MAVLink connection** connects to a supported local transport, such as `tcp:127.0.0.1:5760`. External connections remain read-only in this release. The optional older terminal launchers are `start-sitl.sh` and `start-mavproxy.sh`; the latter additionally requires `MAVProxy==1.8.74` in `.venv`. They are not part of the web app's normal startup path.

## Inference settings and usage

Settings are available without a vehicle and persist in ignored `runtime/copilot/settings.json`. They survive backend restarts and application rebuilds. The four prompts are **continuous assessment**, **mission planning/review**, **mission-statement interpretation**, and **multi-vehicle interaction**. Restore buttons put factory text in the editor; **Save settings** applies it. Preserve the response JSON contracts.

| Setting | Behavior |
| --- | --- |
| Automatic assessments | Global enable/pause, plus per-vehicle monitoring control |
| Assessment interval | 10 seconds to 24 hours, measured after each assessment completes; longer intervals reduce request frequency |
| Timeout | 10–120 seconds; 45-second initial default |
| Model | Editable model ID or provider model discovery |
| Endpoint | OpenAI-compatible API base URL; include `/v1` for Ollama, not `/chat/completions` |
| Prompts | Persisted custom system text, with application validators enforced independently |

At a five-minute interval, each monitored vehicle has a nominal ceiling of about 12 scheduled assessments per hour, excluding request duration. Each assessment can make one bounded repair request; chat and manual connection tests add calls. More simultaneous vehicles mean more requests. Global pause stops subsequent automatic calls but numerical checks continue.

The cloud credential is sent only to the original configured HTTPS provider origin, never to a local or alternate endpoint. Local endpoints receive no cloud key. Alternate providers that require a different key need separate credential support; there is currently no arbitrary provider-secret editor. During active blinded trials, inference settings are locked to keep the experimental configuration stable.

## SITL failure experiments

Open **Diagnostics / tests**, select an owned simulator, claim control, choose a scenario, observation duration, seed and evidence track, then run. Enable automatic assessments first and choose an interval shorter than the observation window. The lab warns about an interval that is too long and does not silently increase request frequency.

| Scenarios | Vehicle profiles |
| --- | --- |
| Nominal control, GPS loss/jump, battery sag, RC loss, primary magnetometer failure | Copter, Plane, Rover |
| Strong crosswind, barometer drift | Copter, Plane |
| Reduced motor output | Copter |
| Held airspeed | Plane |

Trials preserve the existing flight/driving phase. A motor or wind fault may be unobservable while disarmed; establish the intended phase with normal controls first. Cancellation attempts to restore injected parameters and reports restoration failures.

Two evidence tracks answer different questions:

- **Telemetry-only:** excludes simulator parameters/messages, diagnostic strings, deterministic rule labels, scenario IDs, seeds, injection events and private truth. It tests inference from permitted measurements.
- **Operational:** includes normal autopilot diagnostic messages and rule context. It measures usefulness with the information an operator would normally see.

Predictions are locked and hashed before results are revealed. The current scorer performs lexical symptom screening with evidence timing; results need human adjudication and nominal controls. Existing smoke trials do not establish a validated safety-detection rate. See [the evaluation protocol](sitl-evaluation.md) and [measured results](validation.md).
