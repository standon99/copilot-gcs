"""Typed GCS tools acting on a turn's isolated working copies, never the gateway."""

import copy
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import PROFILES
from .geography import ExclusionProposal
from .interaction import ParameterProposal, parameter_context
from .metadata import validate_parameter
from .monitoring import Monitoring, effective_monitoring, monitor_config
from .planning import Waypoint, apply_patch, check
from .watches import METRICS, WatchRule


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: str = Field(min_length=1, max_length=64)


class MissionRead(Args):
    offset: int = Field(default=0, ge=0, le=500)
    limit: int = Field(default=100, ge=1, le=100)


class Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    frame: Literal[0, 3, 10] | None = None
    command: int | None = None
    p1: float | None = None
    p2: float | None = None
    p3: float | None = None
    p4: float | None = None


class Add(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["add"]
    waypoint: Waypoint


class Update(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["update"]
    id: str
    fields: Fields


class Remove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["remove"]
    id: str


class Reorder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: Literal["reorder"]
    ids: list[str] = Field(max_length=500)


class EditWaypoints(Args):
    expected_revision: int = Field(ge=0)
    operations: list[Annotated[Add | Update | Remove | Reorder, Field(discriminator="op")]] = Field(
        min_length=1, max_length=100
    )


class UpdateWaypoint(Args):
    expected_revision: int = Field(ge=0)
    waypoint_id: str
    fields: Fields


class ValidateMission(Args):
    include_proposed_fence: bool = False


class SearchParameters(Args):
    query: str = Field(min_length=1, max_length=200)


class ProposeParameters(Args):
    parameters: list[ParameterProposal] = Field(min_length=1, max_length=20)


class ProposeFence(Args):
    kind: Literal["exclusion", "inclusion"]
    reason: str = Field(min_length=1, max_length=2000)
    coordinate_space: Literal["geographic", "map_pixels"] = "geographic"
    polygons: list[list[tuple[float, float]]] = Field(
        max_length=20,
        description="List of polygon rings of [longitude, latitude] pairs (or [x,y] pixels). Example: [[[149.1,-35.1],[149.2,-35.1],[149.2,-35.2]]]. NOT GeoJSON objects. Complete replacement for chosen kind.",
    )
    inclusion_mode: Literal["intersection", "union"] | None = None


class ManageWatch(Args):
    expected_revision: int = Field(ge=0)
    operation: Literal["add", "update", "enable", "disable", "remove", "notes"]
    id: str | None = None
    rule: WatchRule | None = None
    enabled: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class ConfigureMonitoring(Args):
    expected_revision: int = Field(ge=0)
    periodic_enabled: bool | None = None
    interval_s: int | None = Field(default=None, ge=10, le=86400)
    watch_advice_enabled: bool | None = None
    focus: str | None = Field(default=None, max_length=2000)


TOOLS = {
    "get_vehicle_state": (
        Args,
        "Read current selected-vehicle telemetry and recent evidence. No simulator truth.",
        False,
    ),
    "get_mission": (
        MissionRead,
        "Read the working mission, intent, exact waypoint IDs and working revision. Page using offset/limit.",
        False,
    ),
    "update_waypoint": (
        UpdateWaypoint,
        "Update specified fields of one existing waypoint in the local working draft. Altitude metres; frame 3 above home, 0 AMSL. Read first, validate afterward.",
        True,
    ),
    "edit_waypoints": (
        EditWaypoints,
        "Add, update, remove or reorder working draft waypoints in one validated batch. This never uploads or starts a mission. Validate afterward.",
        True,
    ),
    "validate_mission": (
        ValidateMission,
        "Run numerical checks on the working draft. Optionally include the pending fence preview without accepting it. This does not authorize upload.",
        False,
    ),
    "search_parameters": (
        SearchParameters,
        "Find up to 40 actual parameters and pinned metadata by words or exact parameter name. Search before proposing; no simulator parameters.",
        False,
    ),
    "propose_parameters": (
        ProposeParameters,
        "Stage parameters present in search results for manual Apply. No vehicle write.",
        True,
    ),
    "propose_geofence": (
        ProposeFence,
        "Preview a complete replacement of the chosen inclusion or exclusion polygon set, preserving areas to keep. Inclusion mode: intersection stays inside ALL overlapping areas; union stays inside ANY area. Needs operator Accept and separate Upload. Geographic or attached-map pixel coordinates.",
        True,
    ),
    "get_watch_rules": (
        Args,
        "Read local watch rules, their revision and the supported metric catalog.",
        False,
    ),
    "manage_watch": (
        ManageWatch,
        "Add/update/enable/disable/remove requested local advisory watches, or replace concern notes. enabled=true activates an explicitly requested watch; never sends vehicle actions. Use exact thresholds and phase.",
        True,
    ),
    "get_monitoring": (
        Args,
        "Read per-vehicle monitoring configuration and operator-owned hard limits/master switches.",
        False,
    ),
    "configure_monitoring": (
        ConfigureMonitoring,
        "Configure requested periodic monitoring, interval, focus and independent watch-triggered advice. Settings master switches and shared automatic request cap cannot be changed. Too-fast intervals are clamped.",
        True,
    ),
}


def inline_schema(model):
    """Avoid provider-specific handling of $defs/$ref and tuple prefixItems."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(node):
        if isinstance(node, list):
            return [expand(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            node = {
                **definitions[node["$ref"].rsplit("/", 1)[-1]],
                **{k: v for k, v in node.items() if k != "$ref"},
            }
        node = {k: expand(v) for k, v in node.items() if k not in ("title", "discriminator")}
        if "prefixItems" in node:
            parts = node.pop("prefixItems")
            node["items"] = parts[0]  # All tuple schemas here are coordinate pairs.
        if "oneOf" in node:
            node["anyOf"] = node.pop("oneOf")
        if "anyOf" in node:
            nonnull = [part for part in node["anyOf"] if part.get("type") != "null"]
            if len(nonnull) == 1:
                # Optional properties are omitted. Some tool templates stringify
                # object-or-null unions instead of emitting a nested object.
                node.pop("anyOf")
                node.update(nonnull[0])
                if node.get("default") is None:
                    node.pop("default", None)
        return node

    return expand(schema)


def tool_schemas(read_only=False):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": inline_schema(model),
            },
        }
        for name, (model, desc, mutates) in TOOLS.items()
        if not (read_only and mutates)
    ]


class TurnConflict(RuntimeError):
    pass


class WorkspaceTurn:
    def __init__(self, live, ids, prefs, map_image=None, read_only=False):
        self.live, self.ids, self.prefs = live, ids, prefs
        self.map_image, self.read_only = map_image, read_only
        self.before = {}
        self.working = {}
        self.validated = {}
        for vid in ids:
            v = live[vid]
            self.before[vid] = {
                "vehicle": v,
                "epoch": v.telemetry.epoch,
                "draft": copy.deepcopy(v.draft),
                "watch_revision": v.watches.revision,
                "monitor_revision": monitor_config(v).revision,
            }
            self.working[vid] = {
                "draft": copy.deepcopy(v.draft),
                "watches": copy.deepcopy(v.watches),
                "monitoring": monitor_config(v).model_copy(deep=True),
                "parameters": {},
                "catalog": {},
                "fence": None,
                "operations": [],
            }

    def guard(self):
        for vid, b in self.before.items():
            v = self.live.get(vid)
            if v is not b["vehicle"] or v.closed or v.telemetry.epoch != b["epoch"]:
                raise TurnConflict("Selected vehicle session changed; no turn changes applied")
            if v.trial_task and not v.trial_task.done():
                raise TurnConflict("Diagnostics started; no turn changes applied")
            if (
                v.draft["revision"] != b["draft"]["revision"]
                or v.watches.revision != b["watch_revision"]
                or monitor_config(v).revision != b["monitor_revision"]
            ):
                raise TurnConflict("Workspace changed during this turn; no turn changes applied")
            for p in self.working[vid]["parameters"].values():
                current = v.params.get(p["name"])
                if not current or not math.isclose(
                    current["value"], p["expected"], rel_tol=1e-6, abs_tol=1e-5
                ):
                    raise TurnConflict("A proposed parameter changed; no turn changes applied")

    def missing_validation(self):
        return [
            vid
            for vid, w in self.working.items()
            if w["operations"] and self.validated.get(vid) != w["draft"]["revision"]
        ]

    def execute(self, name, arguments):
        self.guard()
        if name not in TOOLS or (self.read_only and TOOLS[name][2]):
            raise ValueError("Tool is not available in this turn")
        a = TOOLS[name][0].model_validate(arguments)
        if a.vehicle_id not in self.ids:
            raise ValueError("Tool targets an unselected vehicle")
        v, w = self.live[a.vehicle_id], self.working[a.vehicle_id]
        if name == "get_vehicle_state":
            return {
                "state": v.telemetry.snapshot(),
                "observations": v.telemetry.observations(v.active, "operational"),
            }
        if name == "get_mission":
            return {
                "revision": w["draft"]["revision"],
                "intent": w["draft"]["intent"],
                "waypoints": w["draft"]["waypoints"][a.offset : a.offset + a.limit],
                "total": len(w["draft"]["waypoints"]),
                "offset": a.offset,
                "home": v.telemetry.snapshot()["home"],
                "supported_commands": PROFILES[v.profile]["commands"],
            }
        if name in ("edit_waypoints", "update_waypoint"):
            ops = (
                [
                    {
                        "op": "update",
                        "id": a.waypoint_id,
                        "fields": a.fields.model_dump(exclude_none=True),
                    }
                ]
                if name == "update_waypoint"
                else [op.model_dump(exclude_none=True) for op in a.operations]
            )
            draft = apply_patch(w["draft"], ops, a.expected_revision)
            if any(p["command"] not in PROFILES[v.profile]["commands"] for p in draft["waypoints"]):
                raise ValueError("Mission command unsupported for this vehicle")
            w["draft"] = draft
            w["operations"].extend(ops)
            return {
                "working_revision": draft["revision"],
                "waypoint_count": len(draft["waypoints"]),
                "applied_operations": ops,
                "status": "staged until this turn completes; call validate_mission",
            }
        if name == "validate_mission":
            draft = copy.deepcopy(w["draft"])
            if a.include_proposed_fence and w["fence"]:
                for key in ("exclusions", "inclusions", "inclusion_mode"):
                    draft["intent"][key] = w["fence"][key]
            result = check(draft, v.profile, v.telemetry.snapshot()["home"])
            if not a.include_proposed_fence:
                self.validated[v.id] = draft["revision"]
            return {
                **result,
                "findings": result["findings"][:100],
                "total_findings": len(result["findings"]),
                "includes_proposed_fence": a.include_proposed_fence,
            }
        if name == "search_parameters":
            entries = parameter_context(v.profile, v.params, a.query)
            w["catalog"].update({p["name"]: p for p in entries})
            return {"parameters": entries}
        if name == "propose_parameters":
            proposed = {}
            for p in a.parameters:
                old = w["catalog"].get(p.name)
                if not old or p.name.startswith("SIM_") or p.name in proposed:
                    raise ValueError(
                        "Search each parameter first; duplicate/SIM parameters are unavailable"
                    )
                if old["type"] != 9 and p.value != int(p.value):
                    raise ValueError("Integer parameter requires an integer")
                validate_parameter(v.profile, p.name, p.value)
                proposed[p.name] = {**p.model_dump(), "expected": old["value"]}
            if len(w["parameters"] | proposed) > 20:
                raise ValueError("At most 20 parameter proposals per vehicle per turn")
            w["parameters"].update(proposed)
            self.guard()
            return {
                "status": "pending manual Apply after turn completion",
                "parameters": list(proposed.values()),
            }
        if name == "propose_geofence":
            resolved = ExclusionProposal.model_validate(
                a.model_dump(include={"reason", "coordinate_space", "polygons"})
            ).resolve(self.map_image)
            if w["fence"] is None:
                w["fence"] = {
                    key: copy.deepcopy(w["draft"]["intent"][key])
                    for key in ("exclusions", "inclusions", "inclusion_mode")
                }
            w["fence"][a.kind + "s"] = resolved["polygons"]
            w["fence"]["reason"] = resolved["reason"]
            if a.kind == "inclusion" and a.inclusion_mode is not None:
                w["fence"]["inclusion_mode"] = a.inclusion_mode
            proposed = copy.deepcopy(w["draft"])
            for key in ("exclusions", "inclusions", "inclusion_mode"):
                proposed["intent"][key] = w["fence"][key]
            checks = check(proposed, v.profile, v.telemetry.snapshot()["home"])
            return {
                "status": "preview only; pending operator acceptance",
                **w["fence"],
                "checks": {**checks, "findings": checks["findings"][:100]},
            }
        if name == "get_watch_rules":
            return {
                **w["watches"].public(),
                "metrics": METRICS,
                "rule_schema": WatchRule.model_json_schema(),
            }
        if name == "manage_watch":
            w["watches"].edit(
                a.expected_revision, a.operation, a.id, a.rule, a.notes, "AI tool", a.enabled
            )
            return {
                **w["watches"].public(),
                "status": "applies when turn completes",
                "advice": self.monitoring(w),
            }
        if name == "get_monitoring":
            return self.monitoring(w)
        if name == "configure_monitoring":
            if a.expected_revision != w["monitoring"].revision:
                raise ValueError("Monitoring revision changed; read it again")
            patch = a.model_dump(exclude_none=True, exclude={"vehicle_id", "expected_revision"})
            if "interval_s" in patch:
                patch["interval_s"] = max(patch["interval_s"], self.prefs.automatic_min_interval)
            w["monitoring"] = Monitoring.model_validate(
                {**w["monitoring"].model_dump(), **patch, "revision": w["monitoring"].revision + 1}
            )
            return {
                **self.monitoring(w),
                "status": "applies when turn completes; global Settings switches still apply",
            }
        raise ValueError("Unknown tool")

    def monitoring(self, working):
        from types import SimpleNamespace

        return effective_monitoring(SimpleNamespace(monitoring=working["monitoring"]), self.prefs)
