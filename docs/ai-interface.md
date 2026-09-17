# AI interface

Copilot receives a versioned capability catalog and response schema on every
AI-planning request. The same catalog is available at
[GET /api/ai/capabilities](http://127.0.0.1:8080/api/ai/capabilities) and through
**AI tool contract** beside the chat composer. Settings shows the application
contract appended to the saved interaction prompt.

The current transport is **one JSON response to /api/interaction**, validated by
the backend. It is not an OpenAI function-calling loop, MCP server or arbitrary
tool executor. A text model can propose coordinates; image-based tracing requires
a vision-capable model selected in Settings.

| Capability | Response field | Effect |
| --- | --- | --- |
| Add/update/remove/reorder waypoints | vehicles[].operations | Revises the local mission draft |
| Propose parameters | vehicles[].parameters | Review card; operator Apply, disarmed, verified readback |
| Propose exclusion areas | vehicles[].exclusion_proposal | Purple preview; Accept areas replaces draft exclusions |
| Propose watch rules | vehicles[].watch_rules | Disabled rules; operator enables them |
| Record watch concerns | vehicles[].watch_notes | Operational AI context outside Diagnostics |

Each selected vehicle supplies its ID, boot epoch, profile, supported commands,
canonical draft, numerical checks, live state, recent conversation, watch state
and up to 40 relevant parameter entries with pinned metadata. The catalog includes
Pydantic-generated response/waypoint schemas and the watch metric catalog.
All selected sessions and draft/watch revisions are checked after inference;
one invalid edit rejects the whole response. Diagnostics locks this planning path.

## Exclusion proposal example

The response names an exact selected vehicle ID. Coordinates are longitude,
latitude in degrees. Rings close implicitly; do not repeat the first point.

```json
{
  "reply": "Proposed the requested area. Check the purple boundary.",
  "vehicles": [{
    "vehicle_id": "use-the-selected-session-id",
    "exclusion_proposal": {
      "reason": "Requested exclusion around the specified location",
      "coordinate_space": "geographic",
      "polygons": [
        [[149.166,-35.362],[149.167,-35.362],[149.167,-35.361],[149.166,-35.361]]
      ]
    }
  }]
}
```

The list is the **complete proposed replacement**, including areas to retain.
An empty list proposes removal. Neither changes anything until accepted.
Acceptance checks proposal identity, draft version and boot epoch, creates a
reversible draft revision, and invalidates its review. Onboard upload is separate.

## Vision map input

1. Select a vision model in **Settings** (cloud or your own compatible endpoint).
   The native cloud test used qwen3.5:397b with a 90-second inference timeout;
   the unchanged default text model does not gain vision from attaching an image.
2. Open the map and choose **Attach map for vision model**.
3. Review the thumbnail and send a message describing the boundary.
4. Inspect the purple proposal; accept or dismiss it. Adjust vertices manually
   in **Plan mission** if needed.

The browser captures the actual map canvas at up to 1280 pixels per dimension,
north-up and without tilt, with a pixel grid and basemap attribution. It includes
rendered route/area layers; DOM vehicle/waypoint markers and the rest of the UI
are not in the image. Vehicle state is supplied separately as structured data.
Only this explicitly attached planning turn sends an image. Automatic assessments
and Diagnostics do not receive map images.

The request carries PNG dimensions, capture time, selected vehicle/draft and
bounds [west,south,east,north]. Captures expire after three minutes or a draft
change; wrapping/polar views and extents over five degrees are rejected.
The provider receives OpenAI-compatible text plus image_url content. Providers
without image support report an error; the app does not silently switch models.

A proposal may instead use coordinate_space="map_pixels" and [x,y] vertices
measured in that exact PNG, top-left origin. The server converts them using
Web Mercator, checks image bounds and validates the resulting polygons.
Coordinates, duplicate vertices, self-crossings and degenerate areas are checked.
No image or model establishes obstacle clearance, property boundaries or airspace
permission. The audit retains proposal geometry, model metadata and image
georeference/hash, not the full PNG.

## Boundaries and other interfaces

Upload, arm, mode changes, takeoff, start, connections, watch enable and parameter
application are operator actions. There is no shell, filesystem, general URL
fetch, raw MAVLink or executable-script capability. Continuous monitoring is a
separate evidence-based assessment contract with no workspace writes.

An optional browser WebMCP integration in web/src/webmcp.ts exposes
read_ground_station_state, read_selected_mission_workspace and
stage_selected_mission_draft to a compatible browser agent. This is separate
from the Ollama planning contract. It has no vehicle-control or diagnostics tools.

Implementation: backend/ai_contract.py, interaction.py, geography.py and provider.py.
[Ollama image-compatible API](https://docs.ollama.com/api/openai-compatibility).
