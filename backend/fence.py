"""Home-centred circle configuration, with explicit ceiling datum and readback."""

from pydantic import BaseModel, ConfigDict, Field

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


def fence_changes(profile, params, edit):
    if profile == "rover" and edit.max_alt is not None:
        raise ValueError("Rover supports the circular fence without an altitude ceiling")
    if edit.radius <= edit.margin:
        raise ValueError("Fence radius must exceed the margin")
    # This editor explicitly replaces the configured types with circle (+ ceiling).
    changes = {
        "FENCE_RADIUS": edit.radius,
        "FENCE_MARGIN": edit.margin,
        "FENCE_ACTION": edit.action,
        "FENCE_TYPE": 2 | (1 if edit.max_alt is not None else 0),
    }
    if edit.max_alt is not None:
        changes.update(FENCE_ALT_MAX=edit.max_alt, FENCE_ALT_MAX_TP=1)
    if "FENCE_AUTOENABLE" in params:
        changes["FENCE_AUTOENABLE"] = 0
    changes["FENCE_ENABLE"] = int(edit.enabled)
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
        "radius": values.get("FENCE_RADIUS"),
        "max_alt": values.get("FENCE_ALT_MAX") if int(values.get("FENCE_TYPE", 0)) & 1 else None,
        "altitude_frame": values.get("FENCE_ALT_MAX_TP"),
        "available": all(n in values for n in NAMES[:5]),
    }
