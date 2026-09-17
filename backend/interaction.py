"""Validate multi-vehicle draft edits and stage parameter changes for operator review."""

import math
import re

from pydantic import BaseModel, ConfigDict, Field

from .config import PROFILES
from .metadata import metadata, validate_parameter
from .planning import apply_patch


class ParameterProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[A-Z0-9_]{1,16}$")
    value: float = Field(allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=1000)


class VehicleEdits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: str
    operations: list[dict] = Field(default_factory=list, max_length=100)
    parameters: list[ParameterProposal] = Field(default_factory=list, max_length=20)


class InteractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str = Field(min_length=1, max_length=16000)
    vehicles: list[VehicleEdits] = Field(default_factory=list, max_length=6)


def parameter_context(profile, params, message):
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9_]+", message) if len(w) > 2}
    meta = metadata(profile)
    candidates = []
    for name, entry in params.items():
        if name.startswith("SIM_"):
            continue
        detail = meta.get(name, {})
        description = str(detail.get("Description", ""))[:500]
        text = (name + " " + str(detail.get("DisplayName", "")) + " " + description).lower()
        rank = (100 if name.lower() in words else 0) + sum(w in text for w in words)
        if rank:
            candidates.append(
                (
                    rank,
                    {
                        "name": name,
                        "value": entry["value"],
                        "type": entry["type"],
                        "description": description,
                        "units": detail.get("Units"),
                        "range": detail.get("Range"),
                        "values": detail.get("Values"),
                        "bitmask": detail.get("Bitmask"),
                        "read_only": detail.get("ReadOnly"),
                    },
                )
            )
    return [entry for _, entry in sorted(candidates, key=lambda p: (-p[0], p[1]["name"]))[:40]]


def validate_edits(raw, snapshots, live):
    """Validate the entire response before changing any vehicle's local draft."""
    response = InteractionResponse.model_validate(raw)
    for vid, before in snapshots.items():
        v = live.get(vid)
        if not v or v.closed or v.telemetry.epoch != before["epoch"]:
            raise ValueError("Target session changed during inference; nothing applied")
        if v.draft["revision"] != before["draft"]["revision"]:
            raise ValueError("A target draft changed during inference; nothing applied")
    seen = set()
    prepared = []
    for edit in response.vehicles:
        vid = edit.vehicle_id
        if vid not in snapshots or vid in seen:
            raise ValueError("Response targets an unselected or repeated vehicle; nothing applied")
        seen.add(vid)
        before = snapshots[vid]
        v = live.get(vid)
        if not v or v.closed or v.telemetry.epoch != before["epoch"]:
            raise ValueError("Target session changed during inference; nothing applied")
        if v.draft["revision"] != before["draft"]["revision"]:
            raise ValueError("A target draft changed during inference; nothing applied")
        draft = (
            apply_patch(v.draft, edit.operations, before["draft"]["revision"])
            if edit.operations
            else None
        )
        if draft and any(
            w["command"] not in PROFILES[v.profile]["commands"] for w in draft["waypoints"]
        ):
            raise ValueError("Unsupported mission command for target vehicle profile")
        supplied = {p["name"]: p for p in before["parameters"]}
        params = []
        names = set()
        for p in edit.parameters:
            if p.name in names or p.name.startswith("SIM_") or p.name not in supplied:
                raise ValueError("Parameter was not uniquely present in the supplied catalog")
            names.add(p.name)
            old = supplied[p.name]
            actual = v.params.get(p.name)
            if not actual or not math.isclose(
                actual["value"], old["value"], rel_tol=1e-6, abs_tol=1e-5
            ):
                raise ValueError("A proposed parameter changed during inference")
            if actual["type"] != 9 and p.value != int(p.value):
                raise ValueError("An integer parameter cannot contain a fraction")
            validate_parameter(v.profile, p.name, p.value)
            params.append({**p.model_dump(), "expected": old["value"]})
        prepared.append(
            {"vehicle": v, "draft": draft, "operations": edit.operations, "parameters": params}
        )
    return response.reply, prepared
