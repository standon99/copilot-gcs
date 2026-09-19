"""Bounded map features, metric geometry and image feedback for planning only."""

import base64
import copy
import hashlib
import io
import json
import math
import time
from typing import Literal

import httpx
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pyproj import Geod, Transformer
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import substring, transform

from .geography import validate_polygons

GEOD = Geod(ellps="WGS84")
OVERPASS = "https://overpass-api.de/api/interpreter"
_feature_cache = {}


class FeatureInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["road", "airstrip", "area"]
    label: str = Field(min_length=1, max_length=100)
    geometry_type: Literal["LineString", "Polygon"]
    points: list[tuple[float, float]] = Field(min_length=2, max_length=200)
    coordinate_space: Literal["geographic", "map_pixels"] = "geographic"
    uncertainty: str = Field(min_length=1, max_length=500)


class MetricFence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["inclusion", "exclusion"]
    reason: str = Field(min_length=1, max_length=2000)
    shape: Literal["rectangle", "road_following"] = "rectangle"
    width_m: float = Field(ge=10, le=5000, allow_inf_nan=False)
    length_m: float = Field(ge=10, le=5000, allow_inf_nan=False)
    center: tuple[float, float] | None = None
    center_feature_id: str | None = Field(default=None, max_length=100)
    road_id: str | None = Field(default=None, max_length=100)
    side: Literal["west", "east", "north", "south"] | None = None
    clearance_m: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    bearing_deg: float | None = Field(default=None, ge=0, lt=360, allow_inf_nan=False)
    contain_feature_ids: list[str] = Field(
        max_length=10,
        description="IDs of EVERY mapped feature the operator requires inside. Use [] only when none is required. Centering on a feature does not check its containment.",
    )
    replace_index: int | None = Field(default=None, ge=0, le=19)
    append: bool = Field(
        default=False,
        description="Explicitly add another area when areas already exist. Otherwise supply replace_index to revise an existing area.",
    )

    @model_validator(mode="after")
    def combinations(self):
        if self.road_id and (self.side is None or self.clearance_m is None):
            raise ValueError(
                "A road boundary needs an explicit side and clearance_m (0 is allowed)"
            )
        if self.shape == "road_following" and not self.road_id:
            raise ValueError("Road-following geometry needs a road_id")
        if self.center and self.center_feature_id:
            raise ValueError("Choose a center or a center_feature_id, not both")
        if self.append and self.replace_index is not None:
            raise ValueError("Choose append or replace_index, not both")
        return self


def empty_spatial():
    return {
        "revision": 0,
        "features": [],
        "selected_ids": [],
        "brief": {},
        "feature_status": "Not loaded",
    }


def state_for(vehicle):
    return copy.deepcopy(getattr(vehicle, "spatial", None) or empty_spatial())


def merge_features(state, loaded):
    """Keep traces, bound the cache, and drop selections no longer present."""
    retained = [f for f in state["features"] if f["source"] != "OpenStreetMap"]
    state["features"] = (retained + loaded["features"])[:50]
    ids = {f["id"] for f in state["features"]}
    state["selected_ids"] = [ident for ident in state["selected_ids"] if ident in ids]
    state["feature_status"] = loaded["status"]


def valid_coordinate(p):
    return (
        len(p) == 2
        and all(math.isfinite(v) for v in p)
        and -180 <= p[0] <= 180
        and -85 <= p[1] <= 85
    )


def local_frame(origin):
    if not valid_coordinate(origin):
        raise ValueError("A valid longitude/latitude origin is required")
    crs = f"+proj=aeqd +lat_0={origin[1]} +lon_0={origin[0]} +datum=WGS84 +units=m +no_defs"
    return (
        Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform,
        Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform,
    )


def map_metrics(image):
    west, south, east, north = image.bounds
    lon, lat = (west + east) / 2, (south + north) / 2
    width = GEOD.inv(west, lat, east, lat)[2]
    height = GEOD.inv(lon, south, lon, north)[2]
    return {
        "width_m": round(width, 2),
        "height_m": round(height, 2),
        "meters_per_pixel_at_center": round(width / image.width, 4),
        "north_up": True,
        "screen_right": "east",
        "scale_varies_with_latitude": True,
    }


def vehicle_context(vehicle, image=None):
    s = vehicle.telemetry.snapshot()
    age = s.get("coverage", {}).get("GLOBAL_POSITION_INT")
    fresh = bool(s.get("position_valid") and age is not None and age <= 3)
    position = s.get("position") if fresh else None
    home = s.get("home")
    result = {
        "vehicle_id": vehicle.id,
        "observed_at": time.time(),
        "current_position": position,
        "position_age_s": age,
        "position_fresh": fresh,
        "home": home,
        "heading_deg": s.get("heading") if fresh else None,
        "coordinate_order": "longitude, latitude",
        "image_available_this_turn": image is not None and image.vehicle_id == vehicle.id,
    }
    if image and image.vehicle_id == vehicle.id:
        result["capture"] = image.context()
        result["current_marker_pixels"] = {
            key: {
                "pixel": list(image.pixel((p["lon"], p["lat"]))),
                "in_view": image.bounds[0] <= p["lon"] <= image.bounds[2]
                and image.bounds[1] <= p["lat"] <= image.bounds[3],
            }
            for key, p in (("aircraft", position), ("home", home))
            if p
        }
        result["image_age_s"] = round(time.time() - image.captured_at, 1)
    return result


def feature_by_id(features, ident):
    f = next((f for f in features if f["id"] == ident), None)
    if not f:
        raise ValueError(f"Unknown feature {ident}; read map features first")
    return f


def record_feature(data, source, image=None):
    points = data.points
    if data.coordinate_space == "map_pixels":
        if image is None:
            raise ValueError("Tracing image pixels requires a map shared in this turn")
        points = [image.geographic(p) for p in points]
    if not all(valid_coordinate(p) for p in points):
        raise ValueError("Invalid feature coordinates")
    if data.geometry_type == "Polygon":
        points = validate_polygons([points])[0]
        geometry = mapping(Polygon(points))
    else:
        if len(set(points)) < 2 or not LineString(points).is_simple:
            raise ValueError("A feature line needs distinct points and no crossing")
        geometry = mapping(LineString(points))
    center = shape(geometry).centroid
    if any(GEOD.inv(center.x, center.y, *p)[2] > 10000 for p in points):
        raise ValueError("Feature trace exceeds the 10 km local geometry limit")
    digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "id": f"{source}:{digest}",
        "kind": data.kind,
        "label": data.label,
        "geometry": geometry,
        "source": source,
        "confidence": "unverified trace",
        "uncertainty": data.uncertainty,
        "outline_known": data.geometry_type == "Polygon",
        "captured_at": time.time(),
        "map_sha256": image.context()["sha256"] if image else None,
    }


def parse_features(data, center):
    if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
        raise ValueError("Map feature response has no element list")
    project, unproject = local_frame(center)
    result = []
    for item in data.get("elements", []):
        if not isinstance(item, dict):
            continue
        tags = item.get("tags", {})
        if not isinstance(tags, dict) or not isinstance(item.get("geometry"), list):
            continue
        if not all(isinstance(p, dict) for p in item["geometry"]):
            continue
        points = [(p.get("lon"), p.get("lat")) for p in item.get("geometry", [])]
        if (
            not 2 <= len(points) <= 1000
            or any(not isinstance(x, (int, float)) for p in points for x in p)
            or not all(valid_coordinate(p) for p in points)
        ):
            continue
        kind = "road" if "highway" in tags else "airstrip"
        closed = len(points) >= 4 and points[0] == points[-1]
        geometry = Polygon(points) if closed and kind == "airstrip" else LineString(points)
        if geometry.is_empty or not geometry.is_valid:
            continue
        # Keep full geometry near this search; reject huge returned ways.
        metric = transform(project, geometry)
        if metric.length > 50000:
            continue
        simplified = metric.simplify(0.5, preserve_topology=True)
        if (
            len(
                list(
                    simplified.exterior.coords
                    if simplified.geom_type == "Polygon"
                    else simplified.coords
                )
            )
            > 200
        ):
            continue
        result.append(
            {
                "id": f"osm:way:{item['id']}",
                "kind": kind,
                "label": str(
                    tags.get("name")
                    or tags.get("ref")
                    or tags.get("aeroway")
                    or tags.get("highway")
                )[:100],
                "geometry": mapping(transform(unproject, simplified)),
                "source": "OpenStreetMap",
                "confidence": "mapped feature; not field verified",
                "uncertainty": "Road line is a centreline, not the road edge"
                if kind == "road"
                else (
                    "Mapped outline; full airstrip extent needs visual review"
                    if closed
                    else "Runway centreline only; width and full airstrip outline unknown"
                ),
                "outline_known": closed and kind == "airstrip",
                "distance_m": round(metric.distance(Point(0, 0)), 1),
                "source_timestamp": item.get("timestamp"),
                "fetched_at": time.time(),
            }
        )
    # Retain airstrip candidates even where many roads surround the selected vehicle.
    result.sort(key=lambda f: (f["kind"] != "airstrip", f["distance_m"]))
    return result[:35]


async def nearby_features(center, radius_m=1500):
    if not valid_coordinate(center) or not 100 <= radius_m <= 3000:
        raise ValueError("Feature lookup needs valid coordinates and radius 100–3000 m")
    key = (*[round(x, 5) for x in center], round(radius_m))
    cached = _feature_cache.get(key)
    if cached and time.monotonic() - cached[0] < 600:
        return copy.deepcopy(cached[1])
    lon, lat = center
    # Coordinates and bounded radius only: no model-written query or URL is sent.
    around = f"(around:{radius_m:.0f},{lat:.7f},{lon:.7f})"
    query = f'[out:json][timeout:12][maxsize:4000000];(way["highway"]{around};way["aeroway"~"^(runway|aerodrome)$"]{around};);out meta geom;'
    try:
        async with httpx.AsyncClient(timeout=16, trust_env=False, follow_redirects=False) as client:
            async with client.stream(
                "POST",
                OVERPASS,
                data={"data": query},
                headers={"User-Agent": "Copilot-GCS/0.1 (local operator-requested map features)"},
            ) as response:
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > 4_000_000:
                        raise ValueError("Map feature response exceeds 4 MB")
                    chunks.append(chunk)
                data = json.loads(b"".join(chunks))
        result = {
            "features": parse_features(data, center),
            "status": "Loaded mapped candidates; imagery/edge accuracy still needs review",
            "source": "© OpenStreetMap contributors",
            "source_url": "https://www.openstreetmap.org/copyright",
            "fetched_at": time.time(),
            "database_timestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
            "query_center": center,
            "radius_m": radius_m,
        }
        if len(_feature_cache) >= 32:
            _feature_cache.pop(next(iter(_feature_cache)))
        _feature_cache[key] = (time.monotonic(), result)
        return copy.deepcopy(result)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError(
            "Map feature service unavailable or invalid; use a visible map trace or operator-selected feature"
        ) from exc


def construct_metric_fence(args, features, fallback):
    if args.center_feature_id:
        c = shape(feature_by_id(features, args.center_feature_id)["geometry"]).centroid
        origin = (c.x, c.y)
    else:
        origin = args.center or fallback
    if origin is None:
        raise ValueError("No fresh vehicle position; supply a center or mapped feature")
    project, unproject = local_frame(origin)
    road = None
    if args.road_id:
        feature = feature_by_id(features, args.road_id)
        if feature["kind"] != "road" or feature["geometry"]["type"] != "LineString":
            raise ValueError("road_id must identify a road line")
        road = transform(project, shape(feature["geometry"]))
        if road.distance(Point(0, 0)) > 10000:
            raise ValueError("Road is outside the 10 km local planning extent")
        station = road.project(Point(0, 0))
        start, end = station - args.length_m / 2, station + args.length_m / 2
        if start < 0 or end > road.length:
            raise ValueError(
                "Mapped road segment is shorter than the requested boundary; load/trace a longer segment or choose another center"
            )
        segment = substring(road, start, end)
        x0, y0 = segment.coords[0]
        x1, y1 = segment.coords[-1]
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1:
            raise ValueError("Road doubles back; select a simpler segment")
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        nx, ny = -uy, ux
        direction = {"west": (-1, 0), "east": (1, 0), "north": (0, 1), "south": (0, -1)}[args.side]
        dot = nx * direction[0] + ny * direction[1]
        if abs(dot) < 0.25:
            raise ValueError(
                "Chosen side is along this road, not across it; choose its perpendicular side"
            )
        sign = 1 if dot > 0 else -1
        nx, ny = nx * sign, ny * sign
        if args.shape == "road_following":
            outer = segment.buffer(
                sign * (args.clearance_m + args.width_m), single_sided=True, join_style="mitre"
            )
            inner = (
                segment.buffer(sign * args.clearance_m, single_sided=True, join_style="mitre")
                if args.clearance_m
                else None
            )
            polygon = outer.difference(inner) if inner else outer
        else:
            if args.bearing_deg is not None:
                ux, uy = (
                    math.sin(math.radians(args.bearing_deg)),
                    math.cos(math.radians(args.bearing_deg)),
                )
                nx, ny = -uy, ux
                if nx * direction[0] + ny * direction[1] < 0:
                    nx, ny = -nx, -ny
            anchor = road.interpolate(station)
            # A straight edge cannot follow a bend. Place its supporting line on
            # the requested side of the entire chosen segment, without resizing.
            support = max((x - anchor.x) * nx + (y - anchor.y) * ny for x, y in segment.coords)
            cx, cy = (
                anchor.x + nx * (support + args.clearance_m + args.width_m / 2),
                anchor.y + ny * (support + args.clearance_m + args.width_m / 2),
            )
            polygon = Polygon(
                [
                    (cx + along * ux + across * nx, cy + along * uy + across * ny)
                    for along, across in [
                        (-args.length_m / 2, -args.width_m / 2),
                        (args.length_m / 2, -args.width_m / 2),
                        (args.length_m / 2, args.width_m / 2),
                        (-args.length_m / 2, args.width_m / 2),
                    ]
                ]
            )
    else:
        angle = math.radians(args.bearing_deg or 0)
        ux, uy, nx, ny = math.sin(angle), math.cos(angle), math.cos(angle), -math.sin(angle)
        polygon = Polygon(
            [
                (along * ux + across * nx, along * uy + across * ny)
                for along, across in [
                    (-args.length_m / 2, -args.width_m / 2),
                    (args.length_m / 2, -args.width_m / 2),
                    (args.length_m / 2, args.width_m / 2),
                    (-args.length_m / 2, args.width_m / 2),
                ]
            ]
        )
    if polygon.geom_type != "Polygon" or polygon.interiors or not polygon.is_valid:
        raise ValueError(
            "Requested road offset creates a split, crossing or holed region; reduce width or select a simpler road"
        )
    geographic = transform(unproject, polygon)
    ring = validate_polygons([list(geographic.exterior.coords)])[0]
    if len(ring) > 70:
        raise ValueError(
            "Boundary exceeds 70 vertices; simplify the selected road before construction"
        )
    checks = measure_polygon(ring, features, args.contain_feature_ids, args.road_id)
    checks["requested"] = args.model_dump(exclude_none=True)
    checks["road_alignment"] = (
        "follows mapped line offset"
        if args.shape == "road_following"
        else "rectangle; a curved road can deviate from its straight edge"
    )
    return ring, checks


def measure_polygon(ring, features=(), contain_ids=(), road_id=None):
    polygon = Polygon(validate_polygons([ring])[0])
    c = polygon.centroid
    project, _ = local_frame((c.x, c.y))
    metric = transform(project, polygon)
    area, perimeter = GEOD.geometry_area_perimeter(polygon)
    coords = list(polygon.exterior.coords)
    lengths = [round(GEOD.inv(*a, *b)[2], 2) for a, b in zip(coords, coords[1:])]
    containment = []
    for ident in contain_ids:
        f = feature_by_id(features, ident)
        g = transform(project, shape(f["geometry"]))
        containment.append(
            {
                "feature_id": ident,
                "contains_mapped_geometry": metric.covers(g),
                "boundary_clearance_m": round(metric.boundary.distance(g), 2)
                if metric.covers(g)
                else None,
                "full_outline_known": f.get("outline_known", False),
                "source": f["source"],
                "uncertainty": f["uncertainty"],
            }
        )
    result = {
        "area_m2": round(abs(area), 2),
        "perimeter_m": round(perimeter, 2),
        "edge_lengths_m": lengths,
        "vertices": len(ring),
        "feature_containment": containment,
        "all_requested_features_contained": all(x["contains_mapped_geometry"] for x in containment)
        if containment
        else None,
        "fully_identified_outlines": bool(containment)
        and all(x["full_outline_known"] for x in containment),
    }
    if road_id:
        f = feature_by_id(features, road_id)
        road = transform(project, shape(f["geometry"]))
        result["road"] = {
            "feature_id": road_id,
            "minimum_distance_to_mapped_line_m": round(metric.distance(road), 2),
            "crosses_interior": road.relate_pattern(metric, "T********"),
            "edge_clearance_unknown": True,
            "source": f["source"],
        }
    return result


def proposal_issues(proposal):
    checks = (proposal or {}).get("spatial_checks", {})
    issues = []
    if checks.get("all_requested_features_contained") is False:
        issues.append("Requested mapped feature is outside the proposed area")
    if checks.get("road", {}).get("crosses_interior"):
        issues.append("The selected road crosses the proposed area")
    return issues


def render_preview(image, features, fence):
    """Overlay deterministic geometry on the operator-shared image. No tile fetching."""
    if time.time() - image.captured_at > 180:
        raise ValueError("Map capture expired; share a fresh map")
    try:
        with Image.open(io.BytesIO(base64.b64decode(image.image.split(",", 1)[1]))) as source:
            if source.size != (image.width, image.height) or source.format != "PNG":
                raise ValueError("Invalid map raster")
            canvas = source.convert("RGB")
    except (OSError, ValueError) as exc:
        raise ValueError("Map PNG could not be decoded") from exc
    draw = ImageDraw.Draw(canvas, "RGBA")
    font = ImageFont.load_default(size=13)
    offscreen = 0
    proposal_offscreen = 0

    def path(points, color, label, closed=False):
        nonlocal offscreen
        pixels = [image.pixel(p) for p in points]
        if not all(0 <= x <= image.width and 0 <= y <= image.height for x, y in pixels):
            offscreen += 1
        # Avoid unbounded renderer integer coordinates for far-away geometry.
        pixels = [(max(-100000, min(100000, x)), max(-100000, min(100000, y))) for x, y in pixels]
        if closed:
            draw.polygon(pixels, fill=(*color, 28))
            pixels.append(pixels[0])
        draw.line(pixels, fill=(*color, 255), width=3)
        visible = next(
            ((x, y) for x, y in pixels if 0 <= x < image.width and 24 <= y < image.height - 30),
            None,
        )
        if visible:
            draw.text(
                visible,
                label,
                font=font,
                fill=(*color, 255),
                stroke_width=2,
                stroke_fill=(10, 20, 25, 255),
            )

    for f in features[:50]:
        geom = f["geometry"]
        path(
            geom["coordinates"][0] if geom["type"] == "Polygon" else geom["coordinates"],
            (255, 202, 95) if f["kind"] == "road" else (99, 212, 244),
            f["id"],
            geom["type"] == "Polygon",
        )
    for kind in ("inclusions", "exclusions"):
        for i, ring in enumerate((fence or {}).get(kind, [])):
            before = offscreen
            path(ring, (209, 146, 255), f"{kind[:-1]} {i}", True)
            proposal_offscreen += offscreen - before
    draw.rectangle((0, 0, image.width, 23), fill=(13, 25, 31, 245))
    draw.text(
        (8, 3),
        "PROPOSAL PREVIEW | purple boundary | gold roads | cyan airstrips | north up",
        fill="white",
        font=font,
    )
    stream = io.BytesIO()
    canvas.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(), {
        "offscreen_geometries": offscreen,
        "offscreen_proposal_geometries": proposal_offscreen,
        "complete_view": proposal_offscreen == 0,
        "map_context": image.context(),
        "image_role": "Geometry overlay for visual inspection; not independent ground truth",
    }
