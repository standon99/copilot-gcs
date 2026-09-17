# Using Copilot GCS

[Project overview](../README.md)

## Workspace

Choose a profile/count and **Start simulation**, or **Connect telemetry**.
Wait for the selected vehicle's home and position. An optional start-page brief
carries into Chat; launching a simulator makes no AI request.

**Flight** is one workspace. Instruments and contextual flight controls stay on
the left. Switch the map between **Live map** and **Plan mission**. On the right,
**Chat** is the conversation, **Alerts** contains warnings and AI assessments,
and **Watch rules** contains rule configuration and acknowledgement.

Describe a mission in Chat or edit it manually. **Check draft** runs numerical
checks without inference. **Ask AI to review** requests a model assessment in
the conversation. Resolve blockers, enable controls and **Upload mission**.
Upload remains disarmed-only and independently verified.

Flight controls then offers explicit prepare-mode, arm and start actions.
A configuration/home change invalidates the review: use **Check draft** or
**Recheck**. An edited draft does not alter the already uploaded mission.
**Clear draft** removes its waypoints and intent, including draft areas; Undo
restores a prior revision. Onboard missions/fences require separate changes.

## Using the app

### Waypoints, altitude and deployment

1. Select the intended vehicle tab. In **Plan mission**, click the map to add points or drag an existing point.
2. Edit each row's **Altitude m** and **Reference**. **Relative home** means metres above the vehicle's home; **AMSL** means metres above mean sea level. Press Enter or leave the field to save. Terrain-relative missions are blocked because terrain coverage is not implemented.
3. Use supported commands: waypoint (16), unlimited/timed loiter (17/19), return home (20), ground-speed change (178), and takeoff/land (22/21) for aerial vehicles. Rover has no aerial takeoff/land commands.
4. Optionally import a checked example from [`examples/`](../examples/). Its coordinates are at the Canberra SITL site; adapt them for another location.
5. **Check draft** runs numerical checks; **Ask AI to review** optionally adds a model review. Resolve blockers and inspect warnings/unknowns.
6. **Enable vehicle controls**, then **Upload mission** above the map. Upload is disarmed-only and verifies an onboard readback. A later draft edit does not change the active mission.
7. Use **Flight controls**. For a ground-start mission, **Prepare flight** selects GUIDED (Copter), FBWA (Plane), or HOLD (Rover); then choose **Arm vehicle**, then **Start mission**. Copter/Plane missions need an appropriate Takeoff item first. Start switches the autopilot to mission execution; a separate GUIDED **Take off** is available for Copter. Native prearm checks remain enabled; inspect vehicle status messages when a command is refused.

**Version 1** (formerly `r1`) is the draft's edit counter, not its name. Every edit
creates a new version. **Enable vehicle controls** (formerly “Claim control”)
gives this browser a renewable 30-second exclusive command lease for the selected
simulator; it does not arm or start it. Upload explains whether review, control,
a disarmed vehicle or refreshed checks are missing. Review context excludes
read-only runtime/flight-time/boot counters; real configuration changes, home
changes and reboots still require a new review.

### LLM interaction and parameter changes

Use **AI planning** in the main bar, check the target vehicles, and write in the Copilot chat. Use a displayed vehicle ID when instructions differ between copters. For example, replacing the sample ID with a current one:

> For copter ab12cd, add a waypoint at -35.3623, 149.16523 at 30 m above home, followed by unlimited loiter. Stage LOG_DISARMED=1 for that copter. Leave the other copter unchanged.

Requested waypoint changes revise local drafts, with before/after inspection and undo. The application validates the complete multi-target response before changing drafts. An unselected target, reboot or conflicting draft revision rejects the response.

Parameter requests create cards containing vehicle, exact parameter, old/new values and reason. **Enable vehicle controls → Apply to [ID]** writes to a disarmed owned simulator and verifies readback. Proposals expire after five minutes and are invalid after reboot or conflicting changes. A failed batch stops; earlier verified writes remain applied and are recorded in its results.

AI planning starts on each page load and targets the selected vehicle. Switching vehicle tabs resets that selection to the new vehicle; check additional targets explicitly for a multi-vehicle request. With it off, chat is review-only unless **Allow requested draft edits** is enabled. Editing prompts never grants upload, arm, mode, takeoff, mission-start or failure-injection authority to the model.

### Mission intent and operator-error checks

Open **Mission intent & operating constraints** and describe what the operation should achieve. For example:

> During cruise, stay between 25 and 40 metres above home, stay below 6 m/s ground speed, and return home when finished. Takeoff and landing may be below the cruise floor.

**Interpret statement with copilot** proposes structured constraints. Inspect the altitude datum, phase exceptions and unresolved clauses, then accept the proposal into the draft. Upload pins that reviewed intent to the active revision. Supported numerical checks compare actual behavior with those constraints; free-text intent is not automatically a comprehensive safety monitor.

### Custom watch rules and immediate AI advice

In **AI planning**, describe watches in the same message as a mission, or open
**Watch rules → Ask Copilot for watches**. For example:

> Keep this concern in view: possible prop damage, not confirmed. Ask me which
> vibration and attitude thresholds to watch. Also propose an alert whenever
> height above ground is below 10 m while armed, including takeoff and landing.
> Alert and advise only; I choose vehicle actions.

The AI proposes **disabled** rules in the visible Watch rules pane. Inspect the
measurement, units, threshold, phase, dwell time, reset margin and cooldown; edit
if needed, then click **Enable rule**. You can also **Add a rule** without any
inference. **Operator concerns** are editable context for operational assessments,
not a confirmed diagnosis or an executable check. Unsupported conditions need a
supported numerical rule; arbitrary Python, JavaScript and vehicle actions cannot
be included. The current rules compare one measurement against one threshold.

Each card shows its live value and state. Breaches turn red locally, before the
model replies, and stay highlighted until acknowledged. Acknowledgement does not
clear an ongoing breach. “Unavailable” means stale/missing data or unknown flight
phase. “Inactive” means outside the configured phase. **While armed** includes
the ground, takeoff and landing; **Airborne** requires fresh reported flight phase
and includes takeoff/landing. These distinctions matter for a 10 m minimum.

A first trigger bypasses the scheduled AI interval. In **Settings**, enable
automatic assessments and **Request AI advice when a watch rule triggers**, then
choose the minimum time between event assessments (default 60 seconds). Further
triggers are combined while a request is running or the limit applies. The pane
shows queued, assessing, unavailable, paused or advice-available status. Global
and per-vehicle pause suppress automatic calls; numerical checks keep running.
A sustained breach produces one event until it clears beyond the reset margin
and recurs after its cooldown. AI remains advisory and can be delayed or wrong.

Height above ground uses a fresh valid downward range reading with attitude
correction, or fresh local terrain elevation subtracted from reported AMSL.
Relative-home altitude is **never** substituted. Range coverage, tilt and terrain
resolution limit the estimate; terrain height does not establish obstacle
clearance. Default SITL may have neither source, so an AGL watch will show
unavailable. [MAVLink distance and terrain definitions](https://mavlink.io/en/messages/common.html#DISTANCE_SENSOR).
Vibration and attitude can reveal symptoms; they do not identify a damaged prop
by themselves. [ArduPilot vibration guidance](https://ardupilot.org/copter/docs/common-measuring-vibration.html).

Custom notes/rules are excluded from model input during all Diagnostics trials,
and custom triggers cannot change their inference cadence. Local cards still
update. This prevents operator-written fault hints from contaminating those
runs. Outside trials, custom context is included only on the operational track.
Watches belong to the vehicle session, are audited, and must be re-enabled after
autopilot reboot. Live session rules are not automatically restored after an app
restart; saved model/prompt/frequency preferences do persist.

### Geofence

In **Plan mission**, choose **Draw exclusion area**, click at least three corners,
then **Finish area**. Drag a numbered vertex while drawing/editing, undo the last
vertex, or cancel with Escape. **Manage areas → Edit area** reopens a boundary; the trash button
removes it from the draft. Self-crossing/degenerate areas are rejected. Undo,
export and import include the areas. Draft changes are separate from onboard fences.

Red boundaries are draft areas, purple is an AI proposal, amber is the last
downloaded/uploaded onboard snapshot. Numerical checks block waypoints and
straight route legs crossing exclusions, including home departure and RTL.
They do not model curved turns, loiter footprints or obstacle-avoidance paths.

To enforce areas onboard, enable vehicle controls while disarmed, open
**Onboard geofence**, **Read onboard areas**, select a breach action, then
**Upload & enable areas**. This replaces the exclusion bank after a fresh conflict
check, transfers MAVLink2 fence items and independently downloads them for
comparison. It enables the polygon type last and preserves circle/ceiling types.
At most 70 total vertices are supported. Home/current position cannot lie inside
a newly uploaded area. Unsupported existing inclusion/circle/return-point bank
items block replacement rather than being silently erased.
Empty the draft areas and choose **Clear onboard areas** to remove that bank.

The separate circle/ceiling editor preserves polygon/minimum-altitude selections.
Both upload paths disable automatic enable-on-flight behavior. Report Only does
not command recovery. A fence's breach action does not guarantee automatic
detouring. See [ArduPilot fencing](https://ardupilot.org/copter/docs/common-polygon_fence.html).

For AI-drawn boundaries, select a vision model, **Attach map for vision model**
and describe the area. Inspect the purple boundary before **Accept areas**;
acceptance edits the local draft only. A text model can also propose boundaries
from supplied coordinates. The [documented AI interface](ai-interface.md) is
sent to the model on every planning request.

### Map, flight instrument and multiple copters

Choose a profile and a count in the launch bar. Up to six sessions may run together, including mixed profiles. App-owned instances start at separate nearby positions and have separate TCP/RC ports. Startup markers wait for an initial fresh 3D GPS fix and a subsequent position sample; zero and near-zero pre-fix estimator drift no longer places a new Plane over the ocean. After initialization, GPS loss may leave a visibly stale/degraded estimated position. The selected vehicle is teal, other vehicles amber, and stale markers are dimmed. Click a marker/tab to select it, **Locate vehicle** to centre it, or **Fit all** to see the group.

The artificial horizon follows the selected vehicle and converts its attitude telemetry to display degrees. Stale/missing readings are blanked; unavailable attitude is labelled after three seconds without fresh data.

During supported navigation modes, a gold stick/target ring uses fresh autopilot position-target telemetry, falling back to the verified uploaded mission item in AUTO. The orange diamond is a **projected navigation-bearing cue** placed 5–50 m ahead for readability, not the autopilot's internal look-ahead point. Cues disappear when arming/mode/freshness requirements are not met. These displays consume no LLM calls. [MAVLink target message definition](https://mavlink.io/en/messages/common.html#POSITION_TARGET_GLOBAL_INT).

### Parameters, logs and external connections

**Parameters** supports search, metadata, staged single/bulk changes and import/export. **Logs** exposes recorded telemetry, historical replay and onboard DataFlash transfer. Simulator fault parameters use Diagnostics rather than ordinary parameter writes.

**Settings → Read-only MAVLink connection** connects to a supported local transport, such as `tcp:127.0.0.1:5760`. External connections remain read-only in this release. The optional older terminal launchers are `start-sitl.sh` and `start-mavproxy.sh`; the latter additionally requires `MAVProxy==1.8.74` in `.venv`. They are not part of the web app's normal startup path.

## Inference settings and usage

Settings are available without a vehicle and persist in ignored `runtime/copilot/settings.json`. They survive backend restarts and application rebuilds. The four prompts are **continuous assessment**, **mission planning/review**, **mission-statement interpretation**, and **multi-vehicle interaction**. The interaction editor also shows the fixed watch-proposal contract appended by the application. Restore buttons put factory text in the editor; **Save settings** applies it. Preserve the response JSON contracts.

| Setting | Behavior |
| --- | --- |
| Automatic assessments | Global enable/pause, plus per-vehicle monitoring control |
| Watch-triggered assessments | Enable/disable extra calls and set a 10–3,600 second minimum spacing; default 60 seconds; both automatic pause controls apply |
| Assessment interval | 10 seconds to 24 hours, measured after each assessment completes; longer intervals reduce request frequency |
| Timeout | 10–120 seconds; 45-second initial default |
| Model | Editable model ID or provider model discovery |
| Endpoint | OpenAI-compatible API base URL; include `/v1` for Ollama, not `/chat/completions` |
| Prompts | Persisted custom system text, with application validators enforced independently |

At a five-minute interval, each monitored vehicle has a nominal ceiling of about 12 scheduled assessments per hour, excluding request duration. Each assessment can make one bounded repair request; watch-triggered assessments, chat and manual connection tests add calls. More simultaneous vehicles mean more requests. Global pause stops subsequent automatic calls but numerical checks continue.

The cloud credential is sent only to the original configured HTTPS provider origin, never to a local or alternate endpoint. Local endpoints receive no cloud key. Alternate providers that require a different key need separate credential support; there is currently no arbitrary provider-secret editor. During active blinded trials, inference settings are locked to keep the experimental configuration stable.

## SITL failure experiments

Open **Diagnostics**, select an owned simulator, enable vehicle controls, choose a scenario, observation duration, seed and evidence track, then run. Enable automatic assessments first and choose an interval shorter than the observation window. The lab warns about an interval that is too long and does not silently increase request frequency.

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
