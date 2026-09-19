# Spatial planning: review and proposed additions

Status: recommendations, not implemented. Based on the request to draw an
approximately 1 km square west of the road beside the aircraft, containing the
airstrip, and the model's five clarification questions on 2026-09-18.

## What went wrong

The model confused home with current position, asked again about the explicitly
required airstrip containment, and deferred the whole proposal instead of using
available tools. Inclusion is the natural interpretation of an operating area
that must contain the airstrip; state that assumption in a reviewable preview.
This interpretation does not authorize accepting or uploading the proposal.
The saved response metadata confirms one model call and zero tool calls for the
quoted request.

The existing map attachment already includes image dimensions, geographic bounds,
a pixel grid and north-up Web Mercator projection. The backend can convert pixel
vertices to geographic coordinates. Scale is therefore encoded, although there
is no explicit metric scale bar or metric geometry tool. The missing pieces are
reliable feature identification and using the supplied state and geometry.

Current limitations found in the code:

- The first prompt supplies home, not live position or heading. Those are
  available through `get_vehicle_state`; home is not evidence of current position.
- Vehicle/home DOM markers visible to the operator are absent from the attached
  canvas image. The model sees a different image from the full GCS screen.
- Roads and airstrips are imagery, without identified feature geometry, IDs or
  confidence. Polygon validation does not test whether a line follows a road.
- A previous pending fence preview is not exposed as readable geometry by the
  current mission tool. New turns cannot reliably inspect and refine that preview.
- The tool loop returns geometry/checks, but cannot request a fresh image of its
  own overlaid proposal for visual correction.

The [earlier vision validation](vision-compatibility-validation.json) already
showed valid polygons with inaccurate road alignment. Confident text is not a
substitute for inspecting the geometry.

## What the GCS should provide

| Addition | Required behavior |
| --- | --- |
| Compact spatial context | Distinct current position and home, heading, coordinate units, validity and timestamps; current vehicle ID and draft/proposal revision. Fetch longer telemetry history only when needed. |
| Matching visual annotations | Put labelled vehicle/home markers into the attached image and provide their exact pixel coordinates. Include north arrow, metric scale and map extent in metres. Treat off-screen positions explicitly. |
| Named map features | Readable road polylines/edges and airstrip polygons with IDs, source, date/availability and confidence. Use vector data when present; otherwise request a trace or one operator click to resolve candidate features. A road centreline is not its edge. |
| Metric geometry tools | Build/rotate a 1,000 m by 1,000 m rectangle; offset or follow a chosen road by a distance in metres; clip and measure polygons. Let deterministic code perform projection and arithmetic. |
| Readable proposals and feedback | Read the current proposed geometry, overlay it on the same georeferenced map, return the image plus dimensions, area, clearance and containment checks, and allow bounded corrections. |
| Explicit task constraints | Preserve inclusion type, requested size, road side and complete airstrip containment across turns. Separate stated requirements, inferred defaults and genuinely unresolved choices. |

Keep attachment/feature data time-stamped and tied to the selected vehicle,
capture and revision. Unknown road width, airstrip outline or imagery age must
remain unknown rather than receiving invented precision. Preview acceptance and
onboard upload remain separate operator actions. Extra image/model requests stay
within the existing turn limits and require a provider with image/tool support.

## Better interaction

1. Read current telemetry and map context before asking the operator for facts
   the GCS already has. In a north-up map, screen-right is east; aircraft-right
   depends on heading. State which interpretation is used.
2. Resolve the road and airstrip to labelled candidate features. If there are
   several plausible roads, highlight them and ask for a click instead of asking
   the operator to invent coordinates.
3. Build a proposed inclusion region west of that road, containing the whole
   identified airstrip, using the requested metric dimensions.
4. Return numerical constraint results and an overlaid preview to the model.
   Correct within the same bounded turn when possible, then present the preview
   and any unresolved issues for review.

An exact square cannot generally follow a curved road along its entire edge.
That is a useful clarification: **exact 1 km square, or roughly 1 km across with
the boundary following the road?** If the intended approximate interpretation is
clear enough, state it and produce a preview instead of asking five questions.
Ask about road clearance if no applicable saved preference exists; do not invent
a safety margin. Do not silently relax an explicit dimension to fit the airstrip.

## Validation needed before calling this reliable

Use geographically measured fixtures for straight and curved roads, offset
airstrips, multiple nearby roads, stale/off-screen aircraft, heading changes,
missing features and infeasible constraints. Measure side lengths and deviation
from known road geometry, verify full airstrip containment, and inspect actual
overlays. Test that ambiguities trigger a focused question, tool-readable facts
do not trigger redundant questions, and no proposal is accepted or uploaded by
the model. These spatial acceptance tests have not been run or implemented in
this chat-interface iteration.
