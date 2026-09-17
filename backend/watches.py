"""Bounded, declarative operator watches. No generated code or vehicle actions."""

import copy
import math
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .planning import distance

METRICS = {
    "agl_m": {
        "label": "Height above ground",
        "unit": "m",
        "source": "Valid downward range or local terrain estimate; never relative home",
    },
    "relative_alt_m": {
        "label": "Altitude above home",
        "unit": "m",
        "source": "GLOBAL_POSITION_INT.relative_alt",
    },
    "groundspeed_m_s": {"label": "Ground speed", "unit": "m/s", "source": "VFR_HUD.groundspeed"},
    "airspeed_m_s": {
        "label": "Air speed",
        "unit": "m/s",
        "source": "VFR_HUD.airspeed (reported estimate, not necessarily a physical sensor)",
    },
    "climb_m_s": {
        "label": "Climb rate",
        "unit": "m/s",
        "source": "VFR_HUD.climb; negative is descent",
    },
    "vibration_m_s2": {
        "label": "Maximum vibration axis",
        "unit": "m/s²",
        "source": "Max VIBRATION axis; symptom, not a propeller diagnosis",
    },
    "roll_abs_deg": {"label": "Absolute roll", "unit": "°", "source": "ATTITUDE.roll"},
    "pitch_abs_deg": {"label": "Absolute pitch", "unit": "°", "source": "ATTITUDE.pitch"},
    "battery_percent": {
        "label": "Battery remaining",
        "unit": "%",
        "source": "SYS_STATUS.battery_remaining",
    },
    "battery_voltage_v": {
        "label": "Battery voltage",
        "unit": "V",
        "source": "SYS_STATUS.voltage_battery",
    },
    "cross_track_m": {
        "label": "Absolute cross-track error",
        "unit": "m",
        "source": "NAV_CONTROLLER_OUTPUT.xtrack_error; armed AUTO only",
    },
}


class WatchRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)
    metric: str
    operator: Literal["lt", "gt"]
    threshold: float = Field(allow_inf_nan=False, ge=-100000, le=100000)
    scope: Literal["always", "armed", "airborne"] = "armed"
    dwell_s: float = Field(default=0, ge=0, le=60, allow_inf_nan=False)
    hysteresis: float = Field(default=0, ge=0, le=10000, allow_inf_nan=False)
    cooldown_s: int = Field(default=60, ge=10, le=3600)
    severity: Literal["warning", "critical"] = "warning"
    reason: str = Field(default="", max_length=1000)

    @field_validator("metric")
    @classmethod
    def known_metric(cls, value):
        if value not in METRICS:
            raise ValueError("Choose a supplied telemetry metric")
        return value


WATCH_CONTRACT = """Additional response contract: each selected vehicle may include watch_rules (array of the supplied watch_rule_schema) and watch_notes (string). These are local advisory monitoring only, NEVER executable scripts or flight actions. Rules are proposed DISABLED and the operator must Enable them in Watch rules. Only propose requested watches; no implicit rules when just planning a route. When the operator gives a concern, include watch_notes with that concern and retain previous concerns unless asked to remove them. For mission waypoints described as home, use the supplied actual home latitude and longitude, never zero placeholders; if home is missing, ask the operator to wait. Notes describe the operator's concern as an unverified hypothesis, not a diagnosis. Use only supplied watch_metrics. Ask for missing numerical thresholds/phase rather than inventing them. 'At any point while armed' includes ground, takeoff and landing; airborne requires fresh reported flight phase and includes takeoff/landing. Never substitute relative_alt_m for agl_m. Missing AGL is unknown, not safe. Vibration/attitude may indicate propulsion symptoms but cannot confirm a damaged propeller. No arbitrary code, automatic actions, parameter changes or mission edits to implement watches. The existing schema for mission operations and parameter proposals still applies."""


def reading(telemetry, metric, now):
    try:
        return _reading(telemetry, metric, now)
    except (TypeError, KeyError, ValueError, OverflowError):
        return None


def _reading(telemetry, metric, now):
    """Return SI value and exact supporting records, or explicit missing coverage."""

    def fresh(typ):
        e = telemetry.latest.get(typ)
        return e if e and 0 <= now - e["ts"] <= 3 else None

    def result(value, events, source):
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            return None
        return {
            "value": round(value, 4),
            "source": source,
            "evidence": [e["evidence_id"] for e in events],
            "records": copy.deepcopy(events),
        }

    s = telemetry.snapshot(now)
    if metric == "agl_m":
        # Downward beam is projected vertically; large tilt or invalid range is unknown.
        for e in sorted(telemetry.ranges.values(), key=lambda e: e["ts"], reverse=True):
            d = e["data"]
            a = fresh("ATTITUDE")
            if (
                not 0 <= now - e["ts"] <= 3
                or not a
                or d.get("orientation") != 25
                or d.get("signal_quality") == 1
                or not d.get("min_distance", 0)
                < d.get("current_distance", 0)
                < d.get("max_distance", 0)
            ):
                continue
            roll, pitch = a["data"].get("roll"), a["data"].get("pitch")
            if roll is None or pitch is None or max(abs(roll), abs(pitch)) > math.radians(20):
                continue
            return result(
                d["current_distance"] / 100 * math.cos(roll) * math.cos(pitch),
                [e, a],
                "Downward range, tilt-corrected (surface clearance)",
            )
        e, p = fresh("TERRAIN_REPORT"), fresh("GLOBAL_POSITION_INT")
        if e and p and s.get("position_valid"):
            d, pos = e["data"], s["position"]
            spacing = d.get("spacing", 0)
            if spacing > 0 and distance(pos, {"lat": d["lat"] / 1e7, "lon": d["lon"] / 1e7}) <= min(
                30, spacing / 2
            ):
                return result(
                    pos["amsl"] - d["terrain_height"],
                    [p, e],
                    "AMSL minus local terrain estimate (not obstacle clearance)",
                )
        return None
    mapping = {
        "relative_alt_m": ("GLOBAL_POSITION_INT", "relative_alt", 0.001),
        "groundspeed_m_s": ("VFR_HUD", "groundspeed", 1),
        "airspeed_m_s": ("VFR_HUD", "airspeed", 1),
        "climb_m_s": ("VFR_HUD", "climb", 1),
        "battery_percent": ("SYS_STATUS", "battery_remaining", 1),
        "battery_voltage_v": ("SYS_STATUS", "voltage_battery", 0.001),
        "roll_abs_deg": ("ATTITUDE", "roll", 180 / math.pi),
        "pitch_abs_deg": ("ATTITUDE", "pitch", 180 / math.pi),
        "cross_track_m": ("NAV_CONTROLLER_OUTPUT", "xtrack_error", 1),
    }
    if metric == "vibration_m_s2":
        e = fresh("VIBRATION")
        values = [e["data"].get("vibration_" + axis) for axis in "xyz"] if e else []
        return (
            result(max(values), [e], "VIBRATION maximum axis")
            if values and all(v is not None and v >= 0 for v in values)
            else None
        )
    typ, field, scale = mapping[metric]
    e = fresh(typ)
    value = e["data"].get(field) if e else None
    if value is None or (metric == "battery_percent" and not 0 <= value <= 100):
        return None
    if metric == "battery_voltage_v" and value == 65535:
        return None
    if metric == "relative_alt_m" and not s.get("position_valid"):
        return None
    if metric == "cross_track_m" and not (s["armed"] and s["mode"] == "AUTO"):
        return None
    value *= scale
    if metric in ("roll_abs_deg", "pitch_abs_deg", "cross_track_m"):
        value = abs(value)
    return result(value, [e], typ + "." + field)


class WatchBook:
    def __init__(self):
        self.revision = 0
        self.notes = ""
        self.rules = []
        self.epoch = None
        self.pending = {}
        self.last_inference = -1e30

    def add(self, spec, origin="operator"):
        if len(self.rules) >= 20:
            raise ValueError("At most 20 watches per vehicle; remove an existing watch first")
        rule = {
            "id": uuid.uuid4().hex[:12],
            "spec": WatchRule.model_validate(spec).model_dump(),
            "enabled": False,
            "origin": origin,
            "state": "disabled",
            "latched": False,
            "last_trigger": None,
            "count": 0,
            "ai_status": "Not requested",
            "reading": None,
            "since": None,
            "active": False,
        }
        self.rules.append(rule)
        self.revision += 1
        return rule

    def public(self):
        return {
            "revision": self.revision,
            "notes": self.notes,
            "rules": [
                {k: copy.deepcopy(v) for k, v in r.items() if k not in ("since", "active")}
                for r in self.rules
            ],
        }

    def evaluate(self, telemetry, now):
        if self.epoch != telemetry.epoch:
            if self.epoch is not None:
                for r in self.rules:
                    r.update(
                        enabled=False,
                        latched=False,
                        active=False,
                        since=None,
                        last_trigger=None,
                        ai_status="Re-enable after reboot",
                    )
                self.pending.clear()
                self.last_inference = -1e30
                self.revision += 1
            self.epoch = telemetry.epoch
        s = telemetry.snapshot(now)
        triggers = []
        for r in self.rules:
            spec = r["spec"]
            sample = reading(telemetry, spec["metric"], now)
            r["reading"] = {k: v for k, v in sample.items() if k != "records"} if sample else None
            state = None
            if not r["enabled"]:
                state = "disabled"
            elif s["heartbeat_age"] is None or s["heartbeat_age"] > 3:
                state = "unknown"
            elif spec["scope"] != "always" and not s["armed"]:
                state = "inactive"
            elif spec["scope"] == "airborne":
                phase = telemetry.latest.get("EXTENDED_SYS_STATE")
                if (
                    not phase
                    or now - phase["ts"] > 3
                    or phase["data"].get("landed_state") not in (1, 2, 3, 4)
                ):
                    state = "unknown"
                elif phase["data"]["landed_state"] == 1:
                    state = "inactive"
            if not state and sample is None:
                state = "unknown"
            if state:
                r["state"], r["since"] = state, None
                # Gaps must not create repeat triggers; only an observed clear condition rearms.
                if state in ("disabled", "inactive"):
                    r["active"] = False
                continue
            value, threshold = sample["value"], spec["threshold"]
            crossed = value < threshold if spec["operator"] == "lt" else value > threshold
            cleared = (
                value >= threshold + spec["hysteresis"]
                if spec["operator"] == "lt"
                else value <= threshold - spec["hysteresis"]
            )
            if r["active"] and not cleared:
                r["state"] = "triggered"
                continue
            if cleared:
                r.update(active=False, since=None, state="watching")
                continue
            if not crossed:
                r.update(since=None, state="watching")
                continue
            if r["since"] is None:
                r["since"] = now
            r["state"] = "pending"
            if now - r["since"] < spec["dwell_s"]:
                continue
            r["state"] = "triggered"
            if r["last_trigger"] is not None and now - r["last_trigger"] < spec["cooldown_s"]:
                continue
            r.update(active=True, latched=True, last_trigger=now, count=r["count"] + 1)
            trigger = {
                "id": r["id"],
                "label": spec["label"],
                "spec": copy.deepcopy(spec),
                "at": now,
                "epoch": telemetry.epoch,
                **sample,
            }
            triggers.append(trigger)
        return triggers

    def queue(self, triggers, allowed, reason):
        for t in triggers:
            r = next(r for r in self.rules if r["id"] == t["id"])
            r["ai_status"] = "Queued for AI" if allowed else reason
            if allowed:
                self.pending[t["id"]] = t

    def take_pending(self, now, min_interval):
        if not self.pending or now - self.last_inference < min_interval:
            return []
        batch = list(self.pending.values())
        self.pending.clear()
        self.last_inference = now
        self.mark(batch, "Assessing")
        return batch

    def mark(self, batch, status):
        for t in batch:
            for r in self.rules:
                if r["id"] == t["id"] and r["last_trigger"] == t["at"]:
                    r["ai_status"] = status


def add_watch_context(observation, book, triggers, telemetry):
    """Caller must exclude all custom context and event timing from blinded trials."""
    from .normalization import normalized_fields
    from .telemetry import SIGNALS

    observation["operator_watch_notes"] = book.notes
    observation["watch_rules"] = [r for r in book.public()["rules"] if r["enabled"]]
    observation["assessment_trigger"] = "watch_rule" if triggers else "scheduled"
    observation["watch_triggers"] = [
        {k: v for k, v in t.items() if k != "records"} for t in triggers
    ]
    ids = {e["evidence_id"] for e in observation["samples"]}
    current_ids = {
        eid for r in book.rules if r["enabled"] and r["reading"] for eid in r["reading"]["evidence"]
    }
    record_groups = [t["records"] for t in triggers] + [
        [e for e in telemetry.history if e["evidence_id"] in current_ids]
    ]
    for records in record_groups:
        for e in records:
            if e["evidence_id"] not in ids:
                observation["samples"].append(
                    {
                        "evidence_id": e["evidence_id"],
                        "age_s": round(observation["observed_at"] - e["ts"], 2),
                        "message": e["type"],
                        "fields": normalized_fields(
                            e["type"],
                            {k: v for k, v in e["data"].items() if k in SIGNALS[e["type"]]},
                            telemetry.profile,
                        ),
                    }
                )
                ids.add(e["evidence_id"])
