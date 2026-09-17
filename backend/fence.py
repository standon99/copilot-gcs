"""Fence configuration and exclusion bank conversion, with explicit readback."""

from pydantic import BaseModel, ConfigDict, Field

from .geography import validate_polygons
from .metadata import validate_parameter

NAMES = (
    "FENCE_ENABLE",
    "FENCE_TYPE",
    "FENCE_ACTION",
    "FENCE_RADIUS",
    "FENCE_MARGIN",
    "FENCE_ALT_MAX",
    "FENCE_ALT_MAX_TP",
    "FENCE_AUTOENABLE",
)


class FenceEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    radius: float = Field(ge=30, le=10000, allow_inf_nan=False)
    max_alt: float | None = Field(default=None, ge=10, le=1000, allow_inf_nan=False)
    margin: float = Field(default=2, ge=1, le=10, allow_inf_nan=False)
    action: int
    expected: dict[str, float]
    circle: bool = True


class FenceUpload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int
    expected_items: list[dict] = Field(max_length=70)
    expected: dict[str, float]
    action: int


def polygon_items(polygons):
    polygons = validate_polygons(polygons)
    if sum(map(len, polygons)) > 70:
        raise ValueError("Onboard exclusion upload supports at most 70 vertices in total")
    items = []
    for ring in polygons:
        for lon, lat in ring:
            items.append(
                {
                    "command": 5002,
                    "frame": 0,
                    "lat": lat,
                    "lon": lon,
                    "alt": 0,
                    "p1": len(ring),
                    "p2": 0,
                    "p3": 0,
                    "p4": 0,
                }
            )
    # MAVLink coordinates quantize to 1e-7 degrees; validate the actual transmitted shape.
    decode_polygons(
        [
            {**w, "lat": round(w["lat"] * 1e7) / 1e7, "lon": round(w["lon"] * 1e7) / 1e7}
            for w in items
        ]
    )
    return items


def decode_polygons(items):
    rings = []
    cursor = 0
    while cursor < len(items):
        w = items[cursor]
        count = int(w["p1"])
        if w["command"] != 5002 or count != w["p1"] or count < 3:
            raise ValueError(
                "This fence bank contains unsupported types; it will not be overwritten"
            )
        group = items[cursor : cursor + count]
        if len(group) != count or any(p["command"] != 5002 or p["p1"] != count for p in group):
            raise ValueError("Incomplete exclusion polygon in onboard readback")
        rings.append([(p["lon"], p["lat"]) for p in group])
        cursor += count
    return validate_polygons(rings)


def fence_changes(profile, params, edit):
    if profile == "rover" and edit.max_alt is not None:
        raise ValueError("Rover supports the circular fence without an altitude ceiling")
    if edit.radius <= edit.margin:
        raise ValueError("Fence radius must exceed the margin")
    # Preserve polygon and minimum-altitude choices; this form only edits circle/ceiling.
    other_types = int(params.get("FENCE_TYPE", {}).get("value", 0)) & ~3
    changes = {
        "FENCE_RADIUS": edit.radius,
        "FENCE_MARGIN": edit.margin,
        "FENCE_ACTION": edit.action,
        "FENCE_TYPE": other_types
        | (2 if edit.circle else 0)
        | (1 if edit.max_alt is not None else 0),
    }
    if edit.max_alt is not None:
        changes.update(FENCE_ALT_MAX=edit.max_alt, FENCE_ALT_MAX_TP=1)
    if "FENCE_AUTOENABLE" in params:
        changes["FENCE_AUTOENABLE"] = 0
    changes["FENCE_ENABLE"] = int(edit.enabled)
    if edit.enabled and not changes["FENCE_TYPE"]:
        raise ValueError("Select at least one fence type before enabling")
    for name, value in changes.items():
        if name not in params:
            raise ValueError(f"Required parameter {name} has not been discovered")
        if edit.expected.get(name) != params[name]["value"]:
            raise ValueError(f"{name} changed; reload the fence before applying")
        validate_parameter(profile, name, value)
    return changes


def fence_snapshot(params):
    values = {name: params[name]["value"] for name in NAMES if name in params}
    return {
        "values": values,
        "enabled": bool(values.get("FENCE_ENABLE", 0)),
        "circle": bool(int(values.get("FENCE_TYPE", 0)) & 2),
        "polygon": bool(int(values.get("FENCE_TYPE", 0)) & 4),
        "radius": values.get("FENCE_RADIUS"),
        "max_alt": values.get("FENCE_ALT_MAX") if int(values.get("FENCE_TYPE", 0)) & 1 else None,
        "altitude_frame": values.get("FENCE_ALT_MAX_TP"),
        "available": all(n in values for n in NAMES[:5]),
    }
