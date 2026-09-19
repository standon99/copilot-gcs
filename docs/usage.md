# Using Copilot GCS

[Project overview](../README.md)

## Workspace

Choose a profile/count and **Start simulation**, or **Connect telemetry**.
The compact pill shows the project name, gateway connection symbol and selected
model; click the model to open Settings. Wait for the selected vehicle's home and position. An optional start-page brief
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

Requested waypoint changes revise local drafts, with before/after inspection and undo. The model can read, edit, check the results and continue in one turn through the
[documented tools](ai-interface.md). Your messages appear on the right, replies
on the left. The reply bubble streams text as it arrives and shows the current
stage, such as **Thinking…**, **Writing reply…** or **Checking the mission…**,
with the model, elapsed time and **Stop**. Expand **Thinking** to see reasoning
text the provider explicitly returns; this section appears only when available.
It remains available with the completed or stopped reply. Scroll up to read
earlier messages without being pulled back to the bottom.

Expand **Activity details** while waiting or **Reply details** afterward to
inspect tool calls, intermediate/unfinished responses and request counts. A maximum of 12 calls means a usage
limit, not 12 steps the model must complete; these counters stay out of the main
conversation. Settings controls the limit.
The application stages the complete turn before changing drafts. An unselected
target, reboot, concurrent edit, failed request or exhausted/cancelled turn
rejects staged changes. **Stop** requests cancellation, then a stopped message
replaces the waiting bubble. Reloading the page retains an active reply's waiting
indicator, partial text and Thinking; switching vehicles shows that vehicle's
conversation. Streamed text is provisional until the turn finishes its checks.
If a turn fails or stops, unfinished text moves into Reply details and the error
is shown in the conversation. Thinking text is retained in local chat/audit data.

Streaming uses the existing OpenAI-compatible endpoint. Models that do not
return thinking simply stream their answer. An endpoint that returns one JSON
reply instead is displayed on arrival, without making a second request.
Streaming does not raise token/call limits or request extra thinking effort.
Automatic assessments and connection tests still return complete responses.

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

The model can create and enable a rule you request. Inspect its measurement,
units, threshold, phase, dwell, reset margin, cooldown and **AI prompt on trigger**
in Watch rules. Disable or edit it there. Manual **Add a rule** starts disabled;
manual editing requires re-enabling. Turn off **Request AI advice** on a rule for
local alerts alone. **Operator concerns** are assessment context, not a confirmed
diagnosis. Rules cannot contain arbitrary Python, JavaScript or vehicle actions.

Supported metrics include absolute yaw rate and altitude change over a 1–60 s
window. For example: “Enable a watch if altitude above home increases by more
than 5 m in 10 seconds while armed; ask AI to compare climb and attitude data.”
Missing history becomes unavailable. Actual yaw rate is not commanded-response
error; tracking that error needs a separate supported measurement.

Each card shows its live value and state. Breaches turn red locally, before the
model replies, and stay highlighted until acknowledged. Acknowledgement does not
clear an ongoing breach. “Unavailable” means stale/missing data or unknown flight
phase. “Inactive” means outside the configured phase. **While armed** includes
the ground, takeoff and landing; **Airborne** requires fresh reported flight phase
and includes takeoff/landing. These distinctions matter for a 10 m minimum.

A trigger can request AI advice with **periodic monitoring off**. Enable
**Settings → Request AI advice when a watch rule triggers**, the vehicle's watch
advice switch, and the rule's own Request AI advice option. The per-rule prompt
and exact trigger evidence accompany the assessment. The model can configure
these per-vehicle options from your request, but cannot change Settings limits.

Triggers bypass the periodic schedule, while respecting the shared automatic
API spacing and per-vehicle watch spacing. Pending events are combined. Cards
show queued, assessing, unavailable, paused or advice-available states. Disabling
watch advice suppresses those calls and drops queued events; local checks keep
running. A sustained breach triggers once until it clears beyond the reset margin
and recurs after cooldown. AI remains advisory and can be delayed or wrong.

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

In **Plan mission**, choose **Draw inclusion area** or **Draw exclusion area**, click at least three corners,
then **Finish area**. Drag a numbered vertex while drawing/editing, undo the last
vertex, or cancel with Escape. **Manage areas → Edit area** reopens a boundary; the trash button
removes it from the draft. Self-crossing/degenerate areas are rejected. Undo,
export and import include the areas. Draft changes are separate from onboard fences.

Blue boundaries are draft inclusions, red boundaries are exclusions, purple is
an AI proposal, and amber is the last-read onboard snapshot. In **Mission intent
& operating constraints**, choose whether multiple inclusions require their
common overlap (**intersection**, default) or their combined area (**union**).
Numerical checks require home, waypoints and straight route legs to stay inside
the chosen inclusion region and outside exclusions, including departure and RTL.
Boundary contact and routes crossing a gap between union areas are blocked.
They do not model curved turns, loiter footprints or obstacle-avoidance paths.

To enforce areas onboard, enable vehicle controls while disarmed, open
**Onboard geofence**, **Read onboard areas**, select a breach action, then
**Upload & enable areas**. This replaces the mixed inclusion/exclusion bank after a fresh conflict
check, transfers MAVLink2 fence items and independently downloads them for
comparison. It enables the polygon type last and preserves circle/ceiling types.
At most 70 total vertices are supported. Home/current position must be inside the inclusion region and outside exclusions.
Upload verifies the inclusion-combination setting while preserving unrelated
FENCE_OPTIONS bits. Unsupported circular/return-point bank items block replacement
rather than being silently erased.
Empty the draft areas and choose **Clear onboard areas** to remove that bank.

The separate circle/ceiling editor preserves polygon/minimum-altitude selections.
Both upload paths disable automatic enable-on-flight behavior. Report Only does
not command recovery. A fence's breach action does not guarantee automatic
detouring. See [ArduPilot fencing](https://ardupilot.org/copter/docs/common-polygon_fence.html).

For AI-drawn boundaries, choose a model with image **and tool** support in
**Settings → Model & endpoint**, save, then enable **Share map** and describe the area.
Settings reports those capabilities; known incompatible models disable attachment
with a link back to Settings. Ollama `gpt-oss:120b` is text-only;
`qwen3.5:397b` supports images and tools. Unknown endpoint capabilities remain
usable. Large vision requests can need a longer **Inference timeout** (up to 120 s).
Inspect the purple boundary before **Accept areas**;
acceptance edits the local draft only. A text model can also propose boundaries
from supplied coordinates. The [documented AI interface](ai-interface.md) is
sent to the model on every planning request.

**Share map** sends a fresh north-up 2D capture with each message while enabled,
even if you are viewing 3D. The sent bubble shows its dimensions and capture time;
expand **Last shared image** to inspect it. Captures include aircraft/home labels
and a metric scale. State **inclusion** or **exclusion** explicitly.

Open **Map features → Load nearby** to fetch road/runway candidates. Select a line
on the map or a feature in the list to reference it in chat. **Trace road** and
**Trace airstrip** let you click missing geometry and **Save trace**. For example:
“Make an inclusion square 1,000 m on each side, west of this selected road with
20 m clearance from its mapped line; include the selected runway.” The model can
construct in metres and inspect an overlaid preview before replying. Measured
checks appear in the proposal; an outside requested feature or a road crossing
blocks acceptance. A centreline alone leaves width/full extent unknown. An exact
square and a boundary following a curved road are different shapes.

### Map, flight instrument and multiple copters

Choose a profile and a count in the launch bar. Up to six sessions may run together, including mixed profiles. App-owned instances start at separate nearby positions and have separate TCP/RC ports. Startup markers wait for an initial fresh 3D GPS fix and a subsequent position sample; zero and near-zero pre-fix estimator drift no longer places a new Plane over the ocean. After initialization, GPS loss may leave a visibly stale/degraded estimated position. The selected vehicle is teal, other vehicles amber, and stale markers are dimmed. Click a marker/tab to select it, **Locate vehicle** to centre it, or **Fit all** to see the group.

The artificial horizon follows the selected vehicle and converts its attitude telemetry to display degrees. Stale/missing readings are blanked; unavailable attitude is labelled after three seconds without fresh data.

The map starts in **2D**. Scroll/swipe up over it to tilt toward **3D**; swipe down
to flatten. The **3D / 2D** button does the same. Pinch or use +/− to zoom; mouse
wheel scrolling also tilts. Elevated dots use reported AMSL altitude, with vertical
lines to mapped terrain and altitude labels. Terrain loads on demand. **Fit aircraft**
frames positions and height; automatic framing zooms out when dots approach the
edge. Panning pauses framing until **Fit aircraft**. Web terrain is a display layer,
separate from autopilot terrain data and AGL watch inputs. It does not enable
terrain-relative missions. Elevation tiles need internet.

During supported navigation modes, a gold stick/target ring uses fresh autopilot position-target telemetry, falling back to the verified uploaded mission item in AUTO. The orange diamond is a **projected navigation-bearing cue** placed 5–50 m ahead for readability, not the autopilot's internal look-ahead point. Cues disappear when arming/mode/freshness requirements are not met. These displays consume no LLM calls. [MAVLink target message definition](https://mavlink.io/en/messages/common.html#POSITION_TARGET_GLOBAL_INT).

### Parameters, logs and external connections

**Parameters** supports search, metadata, staged single/bulk changes and import/export. **Logs** exposes recorded telemetry, historical replay and onboard DataFlash transfer. Simulator fault parameters use Diagnostics rather than ordinary parameter writes.

**Settings → Read-only MAVLink connection** connects to a supported local transport, such as `tcp:127.0.0.1:5760`. External connections remain read-only in this release. The optional older terminal launchers are `start-sitl.sh` and `start-mavproxy.sh`; the latter additionally requires `MAVProxy==1.8.74` in `.venv`. They are not part of the web app's normal startup path.

## Inference settings and usage

Settings persist in ignored `runtime/copilot/settings.json` across restarts and
rebuilds. Use **Chat tools and planning** for the new native tool loop,
**Continuous assessment** for automatic advice, and **Mission-statement
interpretation** for intent parsing. Earlier JSON planner/interaction prompts
remain saved under legacy labels; they no longer drive native Chat. Restore puts
factory text in the editor; **Save settings** applies it. The fixed tool contract
and backend validators remain enforced independently of prompt edits.

| Setting | Behavior |
| --- | --- |
| Allow periodic AI assessments | Global permission plus per-vehicle enable, focus and cadence |
| Request AI advice when a watch rule triggers | Independent global permission and per-vehicle switch; does not require periodic monitoring |
| Minimum seconds between automatic API requests | Hard installation-wide cap, 10 seconds to 24 hours; default 60 s, at most about 60 automatic requests/hour across all vehicles |
| Default assessment interval | 10 seconds to 24 hours after completion; clamped to the hard spacing |
| Watch spacing | Additional 10–3,600 second per-vehicle event spacing; default 60 s |
| Maximum model calls per chat turn | 2–16; default 12; exhausted turns discard staged changes |
| Output tokens per chat call | 512–4,096; default 2,500 |
| Timeout | 10–120 seconds per request; default 45 s |
| Model / endpoint | Editable model ID or discovery; tool-capable OpenAI-compatible API; Ollama base URLs end in `/v1` |
| Prompts | Saved custom text with application constraints shown below the editor |

The hard automatic cap counts periodic calls, event calls and attempted format
repairs, including failed/cancelled calls. Its last reservation persists across
restart. Event evidence waits in a queue while the cap applies; local alerts do
not wait. A blocked repair reports an unavailable assessment rather than bypassing
the cap. Operator chat and connection tests are separate from automatic usage;
chat can make several requests within its configured turn/output bounds. These
are request limits, not a currency or total input-token budget. Disable both
automatic switches to stop future automatic inference completely.

The cloud credential is sent only to the original configured HTTPS provider origin, never to a local or alternate endpoint. Local endpoints receive no cloud key. Alternate providers that require a different key need separate credential support; there is currently no arbitrary provider-secret editor. During active blinded trials, inference settings are locked to keep the experimental configuration stable.

## SITL failure experiments

Open **Diagnostics**, select an owned simulator, enable vehicle controls, choose a scenario, observation duration, seed and evidence track, then run. Enable automatic assessments first and choose an effective interval (including the hard automatic spacing) shorter than the observation window. The lab warns about an interval that is too long and does not silently increase request frequency.

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
