import copy
import math
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from shapely.geometry import LineString, Point, Polygon

from .config import PROFILES


class Waypoint(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10], max_length=64)
    command: int = 16
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    alt: float = Field(default=30, ge=-1000, le=20000, allow_inf_nan=False)
    frame: Literal[0, 3, 10] = 3
    p1: float = Field(default=0, allow_inf_nan=False)
    p2: float = Field(default=0, allow_inf_nan=False)
    p3: float = Field(default=0, allow_inf_nan=False)
    p4: float = Field(default=0, allow_inf_nan=False)


class Intent(BaseModel):
    brief: str = Field(default="", max_length=8000)
    min_alt: float | None = Field(default=None, ge=-1000, le=20000, allow_inf_nan=False)
    max_alt: float | None = Field(default=None, ge=-1000, le=20000, allow_inf_nan=False)
    altitude_frame: Literal["relative_home", "amsl"] = "relative_home"
    max_speed: float | None = Field(default=None, gt=0, le=200, allow_inf_nan=False)
    corridor_m: float | None = Field(default=None, gt=0, le=10000, allow_inf_nan=False)
    required_commands: list[int] = Field(default_factory=list, max_length=30)
    unresolved: list[str] = Field(default_factory=list, max_length=30)
    exclusions: list[list[tuple[float, float]]] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def valid(self):
        if self.min_alt is not None and self.max_alt is not None and self.min_alt > self.max_alt:
            raise ValueError("Minimum altitude exceeds maximum")
        for ring in self.exclusions:
            if (
                len(ring) < 3
                or len(ring) > 1000
                or any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in ring)
                or not Polygon(ring).is_valid
            ):
                raise ValueError("Exclusion polygons must be valid longitude/latitude rings")
        return self


class Draft(BaseModel):
    revision: int = 0
    waypoints: list[Waypoint] = Field(default_factory=list, max_length=500)
    intent: Intent = Field(default_factory=Intent)


def distance(a, b):
    x = math.radians(b["lon"] - a["lon"]) * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    y = math.radians(b["lat"] - a["lat"])
    return math.hypot(x, y) * 6371000


def check(draft, profile, home=None):
    d = Draft.model_validate(draft)
    findings = []

    def add(severity, code, text, waypoint=None):
        findings.append({"severity": severity, "code": code, "text": text, "waypoint": waypoint})

    if not d.waypoints:
        add("error", "empty", "The mission has no items.")
    for text in d.intent.unresolved:
        add("unknown", "unresolved_intent", text)
    cursor = 0
    for command in d.intent.required_commands:
        found = next(
            (i for i in range(cursor, len(d.waypoints)) if d.waypoints[i].command == command), None
        )
        if found is None:
            add(
                "error",
                "required_step",
                f"Required command {command} is missing or in the wrong order.",
            )
        else:
            cursor = found + 1
    if len({w.id for w in d.waypoints}) != len(d.waypoints):
        add("error", "duplicate_id", "Waypoint IDs must be unique.")
    nav = []
    for w in d.waypoints:
        if w.command not in PROFILES[profile]["commands"]:
            add(
                "error",
                "unsupported_command",
                f"Command {w.command} is unsupported for {profile}.",
                w.id,
            )
        if w.frame == 10:
            add(
                "error",
                "terrain_unavailable",
                "Terrain-relative altitude requires a terrain provider; upload is blocked.",
                w.id,
            )
        if w.command in (16, 17, 19, 21, 22):
            nav.append(w)
            if profile != "rover":
                alt = w.alt
                target = 3 if d.intent.altitude_frame == "relative_home" else 0
                if w.frame != target:
                    if home and w.frame in (0, 3):
                        alt += home["alt"] if w.frame == 3 else -home["alt"]
                    else:
                        add(
                            "error",
                            "altitude_reference",
                            "Home altitude is unavailable for reference conversion.",
                            w.id,
                        )
                        continue
                # Lower-altitude bound applies to cruise, not takeoff or landing.
                if (
                    w.command not in (21, 22)
                    and d.intent.min_alt is not None
                    and alt < d.intent.min_alt
                ):
                    add(
                        "error",
                        "minimum_altitude",
                        f"Altitude {alt:.1f} m is below the approved minimum {d.intent.min_alt:g} m.",
                        w.id,
                    )
                if d.intent.max_alt is not None and alt > d.intent.max_alt:
                    add(
                        "error",
                        "maximum_altitude",
                        f"Altitude {alt:.1f} m exceeds the approved maximum {d.intent.max_alt:g} m.",
                        w.id,
                    )
        if w.command == 178:
            if w.p1 != 1:
                add(
                    "error",
                    "speed_type",
                    "Only ground-speed DO_CHANGE_SPEED (p1=1) is supported.",
                    w.id,
                )
            if w.p2 <= 0:
                add("error", "speed_value", "Requested speed must be positive.", w.id)
            if d.intent.max_speed and w.p2 > d.intent.max_speed:
                add("error", "maximum_speed", "Requested speed exceeds intent.", w.id)
    for ring in d.intent.exclusions:
        poly = Polygon(ring)
        for w in nav:
            if poly.intersects(Point(w.lon, w.lat)):
                add(
                    "error",
                    "excluded_point",
                    "Waypoint intersects an approved exclusion region.",
                    w.id,
                )
        for a, b in zip(nav, nav[1:]):
            if poly.intersects(LineString([(a.lon, a.lat), (b.lon, b.lat)])):
                add(
                    "error",
                    "excluded_leg",
                    "Route leg intersects an approved exclusion region.",
                    b.id,
                )
    if profile != "rover" and d.waypoints and d.waypoints[0].command != 22:
        add(
            "warning",
            "no_takeoff",
            "No initial takeoff item; this plan assumes an already airborne vehicle.",
        )
    if d.waypoints and d.waypoints[-1].command not in (20, 21):
        add("warning", "no_recovery", "No explicit return or landing at the end of this mission.")
    if profile == "plane":
        add(
            "unknown",
            "turn_climb",
            "Fixed-wing turn radius, climb performance and landing approach are not validated.",
        )
    add(
        "unknown",
        "obstacles",
        "Terrain, obstacles, airspace permission and battery endurance are not verified by map imagery.",
    )
    return {
        "revision": d.revision,
        "findings": findings,
        "upload_allowed": not any(f["severity"] == "error" for f in findings),
        "distance_m": sum(distance(a.model_dump(), b.model_dump()) for a, b in zip(nav, nav[1:])),
    }


def revise(current, proposed, expected):
    if current["revision"] != expected:
        raise ValueError("Draft changed while this edit was being prepared. Refresh and retry.")
    result = Draft.model_validate(proposed).model_dump()
    result["revision"] = expected + 1
    return result


def apply_patch(current, operations, expected):
    d = copy.deepcopy(current)
    if len(operations) > 100:
        raise ValueError("Too many draft operations")
    for op in operations:
        kind = op.get("op")
        if kind == "add":
            w = Waypoint.model_validate(op["waypoint"]).model_dump()
            d["waypoints"].append(w)
        elif kind in ("update", "remove"):
            idx = next((i for i, w in enumerate(d["waypoints"]) if w["id"] == op.get("id")), None)
            if idx is None:
                raise ValueError("Unknown waypoint ID")
            if kind == "remove":
                d["waypoints"].pop(idx)
            else:
                fields = op.get("fields", {})
                if set(fields) - {"lat", "lon", "alt", "frame", "command", "p1", "p2", "p3", "p4"}:
                    raise ValueError("Invalid waypoint fields")
                d["waypoints"][idx] = Waypoint.model_validate(
                    {**d["waypoints"][idx], **fields}
                ).model_dump()
        elif kind == "reorder":
            ids = op.get("ids", [])
            if len(ids) != len(set(ids)) or set(ids) != {w["id"] for w in d["waypoints"]}:
                raise ValueError("Reorder must contain each existing ID exactly once")
            by_id = {w["id"]: w for w in d["waypoints"]}
            d["waypoints"] = [by_id[i] for i in ids]
        else:
            raise ValueError("Planner may only add, update, remove or reorder draft waypoints")
    return revise(current, d, expected)
