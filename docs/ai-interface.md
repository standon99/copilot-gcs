# AI interface

Chat uses native OpenAI-compatible function calls through `/v1/chat/completions`.
The model reads GCS state, requests typed edits, receives each tool result and can
continue checking or correcting its work in the same turn. It finishes with a
normal conversational reply. Chat shows a waiting message with the model, elapsed
time and **Stop**. Expand **Activity details** while waiting or **Reply details**
afterward to inspect arguments, results, errors and model-request counts.
Replies are delivered on completion, not streamed; animated dots only indicate
pending work. Private model reasoning is not displayed or recorded.

The versioned catalog is available at
[GET /api/ai/capabilities](http://127.0.0.1:8080/api/ai/capabilities), linked as
**AI tool contract** beside Chat. Its schemas come from the backend validators.
The same tools and application contract are supplied to the model on every round.
**Settings → Chat tools and planning** edits the saved system prompt; the fixed
application contract is shown separately and still applies.

## Tools

Every tool requires an exact selected `vehicle_id`. Tools never address an
unselected session or invoke the MAVLink gateway.

| Tool | Effect |
| --- | --- |
| `get_vehicle_state` | Current telemetry and bounded recent operational evidence |
| `get_mission` | Working mission, intent, home, supported commands and revision; paginated |
| `update_waypoint` | Change specified fields of one waypoint by ID and expected revision |
| `edit_waypoints` | Typed add/update/remove/reorder batch |
| `validate_mission` | Numerical checks; optionally include the pending fence proposal |
| `search_parameters` | Up to 40 matching discovered parameters and pinned metadata; excludes simulator fault parameters |
| `propose_parameters` | Stage searched parameters for the operator's separate Apply action |
| `propose_geofence` | Preview inclusion or exclusion polygons with numerical checks, for separate acceptance |
| `get_watch_rules` | Rules, revision and supported metric catalog |
| `manage_watch` | Add/edit/enable/disable/remove requested advisory rules or concern notes |
| `get_monitoring` | Per-vehicle configuration, effective cadence and operator limits |
| `configure_monitoring` | Periodic enable/interval/focus and independent watch-triggered advice |

Example sequence: `get_mission` → `update_waypoint` → `validate_mission` → final
reply. Invalid arguments become tool errors the model can correct; three identical
errors terminate the turn early. Requested
edits stay in an isolated working copy until the turn finishes; the final edited
mission must have been numerically checked. A failed, cancelled or exhausted turn
discards staged changes. Success creates one visible mission revision with Undo.
Checks can return warnings or blockers; completion does not certify or upload a plan.

Session identity, boot epoch, every selected draft/watch/monitor revision and
settings revision are rechecked throughout the turn and before local commit.
Concurrent changes abort it, including changes to selected but untouched vehicles.
Disk failure during the final local commit is reported as an interrupted commit;
the operator must inspect the workspace. This is not an autopilot transaction.
Diagnostics locks planning. Review-only chat exposes only read tools.

## Monitoring and usage

A request such as “watch absolute yaw rate above 30 degrees/second while armed;
ask for AI advice when it fires; leave periodic monitoring off” can create and
enable that visible rule. Rules may have their own `ai_prompt`, or
`request_ai=false` for local alerts alone. They cannot contain executable scripts
or vehicle actions. Actual yaw rate is not commanded-response error. An altitude
change watch uses a 1–60 second window and becomes unavailable when history has gaps.

Periodic and watch-triggered inference have **independent** global Settings
switches and per-vehicle switches. The model can change only the per-vehicle
configuration. It cannot override either Settings switch or the installation-wide
minimum spacing between automatic API requests. Too-fast requested intervals are
clamped. That hard spacing covers all vehicles, periodic calls, event calls and
repair attempts; failed/cancelled calls count, and the reservation survives restart.
Queued events retain evidence while waiting. Local checks turn red immediately.

Operator-initiated chat is separately bounded: default 12 model calls per turn
(configurable 2–16), 2,500 output tokens per call (512–4,096), at most 40 tool calls,
8 in one model response, and a maximum 600-second turn deadline. Each call also
has the configured provider timeout. These are request/output limits, not a
currency or total input-token budget. A complex request can use several calls.

Automatic assessments remain read-only evidence-based advice. They do not launch
this editing loop or act on a vehicle. Custom notes, focus and watch-triggered
cadence are excluded from Diagnostics; trials use the operator's default cadence
and hard cap, then restore the previous per-vehicle configuration.

## Geofence tool example

Arguments for `propose_geofence` (geographic coordinates are longitude, latitude):

```json
{
  "vehicle_id": "selected-session-id",
  "kind": "inclusion",
  "reason": "Requested operating boundary around the mission",
  "coordinate_space": "geographic",
  "polygons": [
    [[149.164,-35.364],[149.167,-35.364],[149.167,-35.361],[149.164,-35.361]]
  ],
  "inclusion_mode": "intersection"
}
```

Use coordinate arrays, not GeoJSON. Rings close implicitly. This replaces the
complete polygon set of the chosen kind; include areas to retain. The other kind
is preserved, including successive proposals in the same turn. An empty list
proposes removing that kind. `intersection` requires staying inside **all**
inclusion areas; `union` permits the area covered by **any** of them. Crossing a
gap between separate union areas remains invalid.

The purple preview does not change the draft until **Accept areas** verifies the
proposal ID, revision and epoch. Acceptance is reversible and invalidates review.
Onboard upload remains separate and supports mixed inclusion/exclusion banks.

## Vision map input

Select a model with image **and tool** support, choose **Attach map**, inspect the
thumbnail and describe a boundary. A text model can use supplied coordinates;
attaching an image does not give a text-only model vision. No model is switched
automatically. For Ollama cloud, `gpt-oss:120b` is text-only; `qwen3.5:397b`
reports image and tool support. Choose the model in **Settings → Model & endpoint**
and save before attaching. A connection test alone does not test vision.

`GET /api/settings/capabilities` checks the saved selection;
`POST /api/settings/capabilities` checks an unsaved Preferences body. Both return
`model`, `base_url`, and nullable `vision`/`tools` booleans. These are application
metadata endpoints, separate from the model's GCS function-tool catalog.

The app reads the configured endpoint's optional Ollama `/api/show` metadata,
without an inference request. Settings displays image/tool support before saving;
Chat checks the saved model. Known incompatible models disable map attachment,
and the backend rejects image turns before inference. Metadata is cached by exact
endpoint/model for five minutes (30 seconds for unknown support). The probe stays
on the configured origin, uses the same credential scope, and has a five-second
HTTP timeout. It does not send a prompt, image or vehicle data.

Other OpenAI-compatible endpoints may not expose this metadata; support is shown
as **unknown**, and image requests remain available. Provider failures show a
fixed, actionable message for image rejection, authentication, rate limits or
service errors; raw provider bodies and credentials are never displayed. The
app neither retries these failures automatically nor raises the saved usage caps.

The native vision check returned previews with Qwen using a 120-second timeout,
but road alignment failed visual review even after a closer-image correction.
See the [validation record](vision-compatibility-validation.json). A valid polygon
and a confident model reply do not establish that the boundary follows the road.

The actual map canvas is captured north-up, without tilt, at up to 1280 pixels per
dimension, with a pixel grid and attribution. Rendered routes/areas are included;
DOM vehicle/waypoint markers and the rest of the UI are not. The initial context
includes home, vehicle identity and draft metadata; current position, heading and
freshness are available through `get_vehicle_state`, which the model must call.
Only an explicitly attached chat turn sends the
image; automatic assessments and Diagnostics never do.

The [spatial-planning review](spatial-planning.md) describes proposed additions
for road/airstrip identification, metric construction and visual rechecking.
Those additions are not implemented by the current tool catalog.

The PNG carries dimensions, time, vehicle/draft and bounds [west,south,east,north].
Captures expire after three minutes or a draft change. Wrapping/polar views and
extents over five degrees are rejected. `coordinate_space="map_pixels"` accepts
[x,y] coordinates in that image, top-left origin; the server converts them with
Web Mercator and validates image bounds and geometry. The audit stores geometry
and image georeference/hash, not the full PNG. Imagery establishes neither obstacle
clearance nor property or airspace permission.

## Boundaries

Upload, parameter Apply, mode, arm, takeoff, start, connections and fault injection
remain operator-only. There are no shell, filesystem, arbitrary URL-fetch,
raw-MAVLink or executable-script tools. Saved prompts cannot expand this authority.
Custom prompts from earlier versions are retained; native Chat uses the new
`agent` prompt, while legacy JSON planner/interaction editors are labelled as such.

Optional browser WebMCP in `web/src/webmcp.ts` exposes a separate browser-agent
interface for reading state/workspaces and staging a draft; it is not the model's
native tool transport and contains no vehicle-control or diagnostics tools.

Implementation: `backend/agent.py`, `agent_tools.py`, `ai_contract.py`,
`monitoring.py`, `provider.py` and `main.py`.
[Ollama compatibility](https://docs.ollama.com/api/openai-compatibility) ·
[Ollama tool loops](https://docs.ollama.com/capabilities/tool-calling) ·
[ArduPilot polygon fences](https://ardupilot.org/copter/docs/common-polygon_fence.html).
