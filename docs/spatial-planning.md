# Spatial planning

Implemented in `gcs.tools.v3`. The original 2026-09-18 review followed a request
for a 1 km square west of a road, containing an airstrip. The model confused home
with current position, asked again about stated requirements, and made no tool
calls. A later request had no image: the old one-shot attachment had been cleared.
The earlier recommendation to infer inclusion was rejected by the operator;
**fence type must be explicit or established in the current spatial brief**.

## What the GCS supplies

| Data/tool | Behavior |
| --- | --- |
| Current spatial context | Fresh position separate from home, heading, age, vehicle/revision and explicit image availability |
| Shared map | Fresh capture per message while Share map is on; aircraft/home/waypoint labels, exact pixels, north-up projection, scale and extent in metres |
| Feature geometry | Bounded nearby OpenStreetMap roads/runways with IDs, provenance and uncertainty; operator selection and manual/model traces |
| Metric construction | Rectangles, rotation and one-sided road offsets in metres; no model degree arithmetic |
| Measured checks | Side lengths, area, mapped-line distance, road intersection and containment of requested feature geometry |
| Visual feedback | Read a previous pending proposal; render its overlay back to the model for inspection/correction in the same bounded turn |
| Spatial brief | Session-local dimensions, kind, side, selected feature IDs, requirements and unresolved choices |

The app appends its contract even when a custom system prompt is saved. It tells
the model to retrieve available facts, retain stated requirements, use metric
tools, and ask focused questions about unresolved choices. Text alone cannot
guarantee that a model follows these instructions. Tool schemas, revision guards,
operator acceptance and upload restrictions remain independently enforced.

## Operator sequence

1. Select the vehicle. Enable **Share map** for imagery-based planning.
2. Open **Map features → Load nearby**. Select a road/runway on the map or list.
   Trace missing road lines or airstrip outlines with the corresponding buttons.
3. State the fence kind, dimensions, road side and clearance. The model can fetch
   candidates itself; a selection resolves ambiguity without invented coordinates.
4. The model builds and measures a proposed boundary, receives an overlay image,
   and can correct it. Known containment failures or road crossings block acceptance.
5. Inspect the purple preview and measured checks. **Accept areas** changes the
   draft. Onboard upload remains a separate operator action.

For example: “Draw an inclusion square 1 km on each side west of the selected
road, 20 m from its mapped line, containing the selected runway.” An exact square
cannot follow a curved road along its entire edge. Choose the exact rectangle or
a road-following strip; the tool never enlarges explicit dimensions to fit.

## Limits and implementation

- Metric geometry uses local WGS84 azimuthal-equidistant projection through
  pyproj/PROJ and Shapely, with geodesic area and edge measurements. Rectangle
  dimensions are 10–5,000 m. Road offset construction rejects missing/short
  segments, holes, split regions and boundaries over 70 vertices.
- A mapped road is generally a centreline, not an edge. Runway centreline
  containment does not prove the full airstrip is contained. Traces are labelled
  unverified. Unknown imagery age, road width and feature extent stay unknown.
- The fixed Overpass endpoint receives coordinates and a bounded 100–3,000 m
  radius, no credential. Responses are capped at 4 MB, 35 fetched candidates and
  50 total features including traces. The cache is bounded and lasts ten minutes.
  Network failures return a trace/selection alternative.
- North-up map captures expire after three minutes. Rendering uses the same
  image/georeference and reports clipped proposal geometry. It cannot see beyond
  that capture. At most three feedback images are allowed per turn, within the
  existing model-call/output/deadline limits. PNG bytes are not stored in audit.
- Feature selections and briefs belong to the live session. Pending proposals
  remain revision/epoch bound, reversible and separate from accepted constraints.
- This is geometry-assisted planning, not reliable automatic road segmentation
  or validated real-world clearance. See the current [validation](validation.md)
  and historical [vision results](vision-compatibility-validation.json).

Sources: [PROJ projection](https://proj4.org/en/stable/operations/projections/aeqd.html),
[pyproj transforms](https://pyproj4.github.io/pyproj/stable/api/transformer.html),
[Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL).
