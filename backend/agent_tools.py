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
from .spatial import (
    FeatureInput,
    MetricFence,
    construct_metric_fence,
    measure_polygon,
    merge_features,
    nearby_features,
    record_feature,
    render_preview,
    state_for,
    vehicle_context,
)
from .watches import METRICS, WatchRule


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: str = Field(min_length=1, max_length=64)


class MissionRead(Args):
    offset: int = Field(default=0, ge=0, le=500)
    limit: int = Field(default=100, ge=1, le=100)


class VehicleRead(Args):
    include_evidence: bool = False


class FeatureRead(Args):
    radius_m: int = Field(default=1500, ge=100, le=3000)
    load_nearby: bool = True


class TraceFeature(Args, FeatureInput):
    pass


class BuildMetricFence(Args, MetricFence):
    pass


class SpatialBrief(Args):
    kind: Literal["inclusion", "exclusion"] | None = None
    width_m: float | None = Field(default=None, ge=10, le=5000, allow_inf_nan=False)
    length_m: float | None = Field(default=None, ge=10, le=5000, allow_inf_nan=False)
    shape: Literal["rectangle", "road_following"] | None = None
    road_id: str | None = Field(default=None, max_length=100)
    side: Literal["west", "east", "north", "south"] | None = None
    contain_feature_ids: list[str] | None = Field(default=None, max_length=10)
    requirements: list[str] | None = Field(default=None, max_length=10)
    unresolved: list[str] | None = Field(default=None, max_length=10)


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
        VehicleRead,
        "Read current selected-vehicle telemetry. Compact by default; set include_evidence=true only when historical samples are needed. No simulator truth.",
        False,
    ),
    "get_spatial_context": (
        Args,
        "Read fresh position (distinct from home), heading, map/image availability, metric scale, saved spatial brief and operator-selected features. Read facts before asking the operator.",
        False,
    ),
    "get_map_features": (
        FeatureRead,
        "Read mapped roads/airstrips with feature IDs and geometry. load_nearby=true queries a fixed map service near the fresh vehicle position; false reads existing mapped/operator/model traces. Road lines are centrelines, not edges. Missing features remain unknown.",
        False,
    ),
    "trace_map_feature": (
        TraceFeature,
        "Record an UNVERIFIED road/airstrip/area trace from the shared image using map_pixels or geographic coordinates. For missing vector outlines. Does not create a fence. Label uncertainty accurately.",
        True,
    ),
    "update_spatial_brief": (
        SpatialBrief,
        "Remember operator-stated dimensions, road side, containment requirements and unresolved choices across turns. Omitted fields are preserved. Do NOT infer inclusion/exclusion from 'airstrip inside'; ask if unspecified.",
        True,
    ),
    "build_metric_geofence": (
        BuildMetricFence,
        "Construct a geofence preview in metres: rectangle or curved road-following strip. Requires explicit fence kind and contain_feature_ids. Center on a feature, coordinate or fresh vehicle. For roads, side and clearance_m are required (0 allowed, measured to mapped line). If areas exist, supply replace_index to revise one; append=true only when the operator wants an additional area. Returns containment/dimensions; does not silently enlarge to fit. Render the preview when an image is shared.",
        True,
    ),
    "get_geofence_proposal": (
        Args,
        "Read the current pending geofence geometry and numerical measurements, including a preview from an earlier turn. No acceptance or upload.",
        False,
    ),
    "render_spatial_preview": (
        Args,
        "Return a fresh overlay IMAGE of mapped features and the pending fence on the operator-shared map, for visual inspection and correction. No new tile fetch. At most 3 renders/turn. If no image is shared, ask the operator to turn on Share map.",
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
        self.pending_images = []
        self.render_count = 0
        self.visual_reviewed = {}
        for vid in ids:
            v = live[vid]
            self.before[vid] = {
                "vehicle": v,
                "epoch": v.telemetry.epoch,
                "draft": copy.deepcopy(v.draft),
                "watch_revision": v.watches.revision,
                "monitor_revision": monitor_config(v).revision,
                "spatial_revision": state_for(v)["revision"],
                "fence": copy.deepcopy(getattr(v, "geofence_proposal", None)),
            }
            self.working[vid] = {
                "draft": copy.deepcopy(v.draft),
                "watches": copy.deepcopy(v.watches),
                "monitoring": monitor_config(v).model_copy(deep=True),
                "parameters": {},
                "catalog": {},
                "fence": None,
                "operations": [],
                "spatial": state_for(v),
                "spatial_dirty": False,
                "fence_dirty": False,
            }
            prior = getattr(v, "geofence_proposal", None)
            if (
                prior
                and prior.get("base_revision") == v.draft["revision"]
                and prior.get("epoch") == v.telemetry.epoch
            ):
                self.working[vid]["fence"] = {
                    k: copy.deepcopy(prior[k])
                    for k in (
                        "exclusions",
                        "inclusions",
                        "inclusion_mode",
                        "reason",
                        "spatial_checks",
                    )
                    if k in prior
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
                or state_for(v)["revision"] != b["spatial_revision"]
                or getattr(v, "geofence_proposal", None) != b["fence"]
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

    def needs_visual_review(self):
        return [
            vid
            for vid, w in self.working.items()
            if w["fence_dirty"]
            and self.map_image
            and self.map_image.vehicle_id == vid
            and self.visual_reviewed.get(vid) != w["fence"]
        ]

    async def execute_async(self, name, arguments):
        if name != "get_map_features":
            return self.execute(name, arguments)
        self.guard()
        a = FeatureRead.model_validate(arguments)
        if a.vehicle_id not in self.ids:
            raise ValueError("Tool targets an unselected vehicle")
        v, w = self.live[a.vehicle_id], self.working[a.vehicle_id]
        if a.load_nearby:
            context = vehicle_context(v, self.map_image)
            p = context["current_position"]
            if not p:
                raise ValueError(
                    "Fresh aircraft position unavailable; read existing features or select a known map location"
                )
            try:
                loaded = await nearby_features((p["lon"], p["lat"]), a.radius_m)
                self.guard()
                merge_features(w["spatial"], loaded)
                w["spatial_dirty"] = True
            except ValueError as exc:
                return {**w["spatial"], "lookup_error": str(exc)}
        return w["spatial"]

    def execute(self, name, arguments):
        self.guard()
        if name not in TOOLS or (self.read_only and TOOLS[name][2]):
            raise ValueError("Tool is not available in this turn")
        a = TOOLS[name][0].model_validate(arguments)
        if a.vehicle_id not in self.ids:
            raise ValueError("Tool targets an unselected vehicle")
        v, w = self.live[a.vehicle_id], self.working[a.vehicle_id]
        if name == "get_vehicle_state":
            result = {"state": v.telemetry.snapshot()}
            if a.include_evidence:
                result["observations"] = v.telemetry.observations(v.active, "operational")
            return result
        if name == "get_spatial_context":
            return {
                **vehicle_context(v, self.map_image),
                "spatial": w["spatial"],
                "pending_fence": w["fence"],
            }
        if name == "update_spatial_brief":
            patch = a.model_dump(exclude_none=True, exclude={"vehicle_id"})
            if any(
                len(text) > 500
                for key in ("requirements", "unresolved")
                for text in patch.get(key, [])
            ):
                raise ValueError("Each spatial requirement is limited to 500 characters")
            w["spatial"]["brief"].update(patch)
            w["spatial_dirty"] = True
            return {"brief": w["spatial"]["brief"], "status": "staged until turn completion"}
        if name == "trace_map_feature":
            image = self.map_image if self.map_image and self.map_image.vehicle_id == v.id else None
            f = record_feature(a, "model_trace", image)
            features = [x for x in w["spatial"]["features"] if x["id"] != f["id"]]
            if len(features) >= 50:
                raise ValueError("At most 50 map features per vehicle")
            w["spatial"]["features"] = [*features, f]
            w["spatial_dirty"] = True
            return f
        if name == "build_metric_geofence":
            base = w["fence"] or w["draft"]["intent"]
            rings = copy.deepcopy(base[a.kind + "s"])
            if rings and a.replace_index is None and not a.append:
                raise ValueError(
                    f"There are already {len(rings)} {a.kind} areas. Supply replace_index to revise one; use append=true only for an explicitly requested additional area. Read get_geofence_proposal if needed."
                )
            saved_ids = w["spatial"]["brief"].get("contain_feature_ids", [])
            if not set(saved_ids) <= set(a.contain_feature_ids):
                raise ValueError(
                    "Preserve saved containment requirements, or update the spatial brief if the operator changed them"
                )
            p = vehicle_context(v)["current_position"]
            ring, measurements = construct_metric_fence(
                a, w["spatial"]["features"], (p["lon"], p["lat"]) if p else None
            )
            index = a.replace_index
            if index is None:
                index = len(rings)
                rings.append(ring)
            elif index >= len(rings):
                raise ValueError("replace_index does not identify an existing proposed area")
            else:
                rings[index] = ring
            result = self.execute(
                "propose_geofence",
                {"vehicle_id": v.id, "kind": a.kind, "reason": a.reason, "polygons": rings},
            )
            w["fence"]["spatial_checks"] = measurements
            w["spatial"]["brief"].update(
                a.model_dump(
                    exclude_none=True,
                    exclude={"vehicle_id", "replace_index", "append", "reason"},
                )
            )
            w["spatial_dirty"] = True
            return {**result, "replace_index": index, "measurements": measurements}
        if name == "get_geofence_proposal":
            return {
                "proposal": w["fence"],
                "measurements": {
                    kind: [measure_polygon(ring) for ring in (w["fence"] or {}).get(kind, [])]
                    for kind in ("inclusions", "exclusions")
                },
            }
        if name == "render_spatial_preview":
            if self.map_image is None or self.map_image.vehicle_id != v.id:
                raise ValueError(
                    "No map image shared for this vehicle in this turn; enable Share map"
                )
            if self.render_count >= 3:
                raise ValueError(
                    "At most 3 preview images per turn; inspect the last preview or narrow the request"
                )
            image, info = render_preview(self.map_image, w["spatial"]["features"], w["fence"])
            self.render_count += 1
            self.pending_images.append({"image": image, "context": info})
            self.visual_reviewed[v.id] = copy.deepcopy(w["fence"])
            return {
                **info,
                "preview_number": self.render_count,
                "delivery": "Overlay image follows the tool results in this same turn",
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
            if a.coordinate_space == "map_pixels" and (
                self.map_image is None or self.map_image.vehicle_id != v.id
            ):
                raise ValueError("Pixel geometry must target the vehicle whose map was shared")
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
            w["fence"].pop("spatial_checks", None)
            w["fence_dirty"] = True
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
