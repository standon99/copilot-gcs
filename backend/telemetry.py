import copy
import math
import time
from collections import deque

from .normalization import normalized_fields
from .planning import distance

# An explicit allowlist, never the full MAVLink stream or parameter cache.
ALLOWED = {
    "HEARTBEAT",
    "GLOBAL_POSITION_INT",
    "GPS_RAW_INT",
    "VFR_HUD",
    "ATTITUDE",
    "SYS_STATUS",
    "BATTERY_STATUS",
    "EKF_STATUS_REPORT",
    "VIBRATION",
    "NAV_CONTROLLER_OUTPUT",
    "POSITION_TARGET_GLOBAL_INT",
    "MISSION_CURRENT",
    "EXTENDED_SYS_STATE",
    "HOME_POSITION",
    "FENCE_STATUS",
    "RC_CHANNELS",
    "SERVO_OUTPUT_RAW",
    "SCALED_PRESSURE",
}
SIGNALS = {
    "HEARTBEAT": ["type", "autopilot", "base_mode", "custom_mode", "system_status", "mode"],
    "GLOBAL_POSITION_INT": ["lat", "lon", "alt", "relative_alt", "vx", "vy", "vz", "hdg"],
    "GPS_RAW_INT": ["fix_type", "eph", "epv", "satellites_visible"],
    "VFR_HUD": ["airspeed", "groundspeed", "heading", "throttle", "alt", "climb"],
    "ATTITUDE": ["roll", "pitch", "yaw", "rollspeed", "pitchspeed", "yawspeed"],
    "SYS_STATUS": [
        "voltage_battery",
        "current_battery",
        "battery_remaining",
        "onboard_control_sensors_present",
        "onboard_control_sensors_enabled",
        "onboard_control_sensors_health",
    ],
    "BATTERY_STATUS": ["voltages", "current_battery", "battery_remaining", "current_consumed"],
    "EKF_STATUS_REPORT": [
        "flags",
        "velocity_variance",
        "pos_horiz_variance",
        "pos_vert_variance",
        "compass_variance",
        "terrain_alt_variance",
    ],
    "VIBRATION": [
        "vibration_x",
        "vibration_y",
        "vibration_z",
        "clipping_0",
        "clipping_1",
        "clipping_2",
    ],
    "NAV_CONTROLLER_OUTPUT": [
        "nav_bearing",
        "target_bearing",
        "nav_roll",
        "nav_pitch",
        "alt_error",
        "aspd_error",
        "xtrack_error",
        "wp_dist",
    ],
    "POSITION_TARGET_GLOBAL_INT": ["coordinate_frame", "type_mask", "lat_int", "lon_int", "alt"],
    "MISSION_CURRENT": ["seq"],
    "EXTENDED_SYS_STATE": ["landed_state"],
    "HOME_POSITION": ["latitude", "longitude", "altitude"],
    "FENCE_STATUS": ["breach_status", "breach_type", "breach_count"],
    "RC_CHANNELS": ["chancount", "rssi", *[f"chan{i}_raw" for i in range(1, 17)]],
    "SERVO_OUTPUT_RAW": ["port", *[f"servo{i}_raw" for i in range(1, 17)]],
    "SCALED_PRESSURE": ["press_abs", "press_diff", "temperature"],
}


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    return value


class Telemetry:
    def __init__(self, ident, profile):
        self.id = ident
        self.profile = profile
        self.latest = {}
        self.history = deque(maxlen=20000)
        self.messages = deque(maxlen=150)
        self.epoch = 0
        self.sysid = None
        self.dropped = 0

    def ingest(self, event):
        event = finite(event)
        if event["epoch"] != self.epoch:
            self.latest.clear()
            self.history.clear()
            self.epoch = event["epoch"]
        event["evidence_id"] = f"{self.id}:{self.epoch}:{event['seq']}"
        self.sysid = event["sysid"]
        self.dropped = event.get("dropped", 0)
        self.latest[event["type"]] = event
        if event["type"] in ALLOWED:
            self.history.append(event)
        if event["type"] == "STATUSTEXT":
            self.messages.append(event)

    def snapshot(self, now=None):
        now = now or time.time()

        def d(t):
            return self.latest.get(t, {}).get("data", {})

        h, p, g, v, b = (
            d("HEARTBEAT"),
            d("GLOBAL_POSITION_INT"),
            d("GPS_RAW_INT"),
            d("VFR_HUD"),
            d("SYS_STATUS"),
        )
        hp = d("HOME_POSITION")
        home = (
            {"lat": hp["latitude"] / 1e7, "lon": hp["longitude"] / 1e7, "alt": hp["altitude"] / 1e3}
            if hp
            else None
        )
        return finite(
            {
                "id": self.id,
                "profile": self.profile,
                "epoch": self.epoch,
                "sysid": self.sysid,
                "mode": h.get("mode", "CONNECTING"),
                "armed": bool(h.get("base_mode", 0) & 128),
                "heartbeat_age": now - self.latest["HEARTBEAT"]["ts"] if h else None,
                "position": {
                    "lat": p["lat"] / 1e7,
                    "lon": p["lon"] / 1e7,
                    "amsl": p["alt"] / 1000,
                    "relative": p["relative_alt"] / 1000,
                }
                if p
                else None,
                "home": home,
                "speed": v.get("groundspeed"),
                "airspeed": v.get("airspeed"),
                "climb": v.get("climb"),
                "heading": v.get("heading"),
                "voltage": b["voltage_battery"] / 1000
                if b.get("voltage_battery", 65535) != 65535
                else None,
                "battery": b.get("battery_remaining")
                if b.get("battery_remaining", -1) >= 0
                else None,
                "gps_fix": g.get("fix_type"),
                "satellites": g.get("satellites_visible")
                if g.get("satellites_visible", 255) != 255
                else None,
                "attitude": d("ATTITUDE"),
                "mission_seq": d("MISSION_CURRENT").get("seq"),
                "coverage": {
                    k: round(now - e["ts"], 2) for k, e in self.latest.items() if k in ALLOWED
                },
                "dropped_display_messages": self.dropped,
            }
        )

    def rules(self, active=None, now=None):
        now = now or time.time()
        s = self.snapshot(now)
        out = []

        def add(code, severity, text, typ):
            out.append(
                {
                    "code": code,
                    "severity": severity,
                    "text": text,
                    "evidence": [self.latest[typ]["evidence_id"]] if typ in self.latest else [],
                }
            )

        if s["heartbeat_age"] is None or s["heartbeat_age"] > 3:
            add(
                "link_stale",
                "critical",
                "Vehicle heartbeat is stale; command outcome cannot be assumed.",
                "HEARTBEAT",
            )
        gps_age = s["coverage"].get("GPS_RAW_INT", 999)
        if gps_age > 5:
            add(
                "gps_unknown",
                "unknown",
                "GPS observations are unavailable or stale.",
                "GPS_RAW_INT",
            )
        elif s["gps_fix"] is not None and s["gps_fix"] < 3:
            add("gps_fix", "warning", "GPS lacks a 3D fix.", "GPS_RAW_INT")
        if (
            s["battery"] is not None
            and s["coverage"].get("SYS_STATUS", 999) < 5
            and s["battery"] < 20
        ):
            add("battery", "critical", "Reported battery remaining is below 20%.", "SYS_STATUS")
        ekf = self.latest.get("EKF_STATUS_REPORT", {}).get("data", {})
        if ekf and any(
            (ekf.get(k) or 0) > 1
            for k in (
                "velocity_variance",
                "pos_horiz_variance",
                "pos_vert_variance",
                "compass_variance",
            )
        ):
            add(
                "estimator",
                "warning",
                "Estimator innovation variance exceeds 1.",
                "EKF_STATUS_REPORT",
            )
        if active:
            intent = active["intent"]
            p = s["position"]
            fresh = s["coverage"].get("GLOBAL_POSITION_INT", 999) < 3
            if not p or not fresh:
                add(
                    "intent_unknown",
                    "unknown",
                    "Position/altitude constraints cannot be assessed with missing or stale position.",
                    "GLOBAL_POSITION_INT",
                )
            else:
                # Intent is anchored to the reviewed home, not a relocated live home.
                a = p["amsl"]
                if intent["altitude_frame"] == "relative_home":
                    a = p["amsl"] - active["home"]["alt"] if active.get("home") else p["relative"]
                landed = (
                    self.latest.get("EXTENDED_SYS_STATE", {}).get("data", {}).get("landed_state")
                )
                if self.profile != "rover" and s["armed"]:
                    if intent.get("min_alt") is not None and landed is None:
                        add(
                            "intent_phase_unknown",
                            "unknown",
                            "Cruise minimum altitude cannot be fully assessed: flight-phase data is unavailable.",
                            "EXTENDED_SYS_STATE",
                        )
                    if intent.get("max_alt") is not None and a > intent["max_alt"] + 1:
                        add(
                            "intent_max_alt",
                            "critical",
                            f"Altitude {a:.1f} m exceeds approved maximum {intent['max_alt']:g} m.",
                            "GLOBAL_POSITION_INT",
                        )
                    if (
                        landed == 2
                        and s["mode"] not in ("LAND", "RTL")
                        and intent.get("min_alt") is not None
                        and a < intent["min_alt"] - 1
                    ):
                        add(
                            "intent_min_alt",
                            "warning",
                            "Airborne altitude is below approved cruise minimum.",
                            "GLOBAL_POSITION_INT",
                        )
                if (
                    intent.get("max_speed")
                    and s["speed"] is not None
                    and s["coverage"].get("VFR_HUD", 999) < 3
                    and s["speed"] > intent["max_speed"] + 0.5
                ):
                    add(
                        "intent_speed",
                        "warning",
                        "Groundspeed exceeds approved maximum.",
                        "VFR_HUD",
                    )
                from shapely.geometry import LineString, Point, Polygon

                for ring in intent.get("exclusions", []):
                    if Polygon(ring).intersects(Point(p["lon"], p["lat"])):
                        add(
                            "intent_exclusion",
                            "critical",
                            "Vehicle is inside an approved exclusion region.",
                            "GLOBAL_POSITION_INT",
                        )
                nav = [w for w in active["waypoints"] if w["command"] in (16, 17, 19, 21, 22)]
                if intent.get("corridor_m") and len(nav) > 1 and s["armed"] and s["mode"] == "AUTO":
                    scale = math.cos(math.radians(p["lat"]))
                    xy = lambda w: (
                        math.radians(w["lon"] - p["lon"]) * 6371000 * scale,
                        math.radians(w["lat"] - p["lat"]) * 6371000,
                    )
                    if (
                        LineString([xy(w) for w in nav]).distance(Point(0, 0))
                        > intent["corridor_m"]
                    ):
                        add(
                            "intent_corridor",
                            "warning",
                            "Vehicle is outside the approved route corridor.",
                            "GLOBAL_POSITION_INT",
                        )
            if (
                active.get("home")
                and s["home"]
                and (
                    distance(active["home"], s["home"]) > 2
                    or abs(active["home"]["alt"] - s["home"]["alt"]) > 2
                )
            ):
                add(
                    "home_changed",
                    "warning",
                    "Home changed after mission review; relative-altitude intent needs review.",
                    "HOME_POSITION",
                )
        return out

    def observations(self, active=None, track="telemetry", now=None):
        now = now or time.time()
        if active and track == "telemetry":
            active = copy.deepcopy(active)
            active["intent"]["brief"] = ""
            active["intent"]["unresolved"] = []
            for i, w in enumerate(active["waypoints"]):
                w["id"] = f"item_{i + 1}"
        samples = []
        # Downsample by message type/second; preserve short-window extrema separately.
        buckets = {}
        for e in self.history:
            if e["ts"] <= now and now - e["ts"] < 60:
                buckets[(e["type"], int(e["ts"] / 5))] = e
        for e in sorted(buckets.values(), key=lambda e: e["ts"]):
            fields = {k: v for k, v in e["data"].items() if k in SIGNALS[e["type"]]}
            if track == "telemetry":
                for k in (
                    "flags",
                    "onboard_control_sensors_present",
                    "onboard_control_sensors_enabled",
                    "onboard_control_sensors_health",
                    "system_status",
                ):
                    fields.pop(k, None)
            samples.append(
                {
                    "evidence_id": e["evidence_id"],
                    "age_s": round(now - e["ts"], 2),
                    "message": e["type"],
                    "fields": normalized_fields(e["type"], fields, self.profile),
                }
            )
        extrema = {}
        for e in self.history:
            if e["ts"] > now or now - e["ts"] > 10:
                continue
            allowed = {
                k: v
                for k, v in e["data"].items()
                if k in SIGNALS.get(e["type"], [])
                and k
                not in (
                    "flags",
                    "system_status",
                    "onboard_control_sensors_health",
                    "onboard_control_sensors_enabled",
                    "onboard_control_sensors_present",
                )
            }
            for k, v in normalized_fields(e["type"], allowed, self.profile).items():
                if (
                    isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and k
                    not in (
                        "flags",
                        "system_status",
                        "onboard_control_sensors_health",
                        "onboard_control_sensors_enabled",
                        "onboard_control_sensors_present",
                    )
                ):
                    key = e["type"] + "." + k
                    stat = extrema.setdefault(
                        key,
                        {
                            "min": v,
                            "max": v,
                            "count": 0,
                            "min_evidence": e["evidence_id"],
                            "max_evidence": e["evidence_id"],
                        },
                    )
                    if v < stat["min"]:
                        stat["min"] = v
                        stat["min_evidence"] = e["evidence_id"]
                    if v > stat["max"]:
                        stat["max"] = v
                        stat["max_evidence"] = e["evidence_id"]
                    stat["count"] += 1
        result = {
            "vehicle": self.id,
            "profile": self.profile,
            "epoch": self.epoch,
            "observed_at": now,
            "schema": "observations.si.v2",
            "units": "Scaled to SI with units in field names. All altitude_m fields are METRES, never millimetres. hdop/vdop and EKF innovation_test_ratio_sqrt are dimensionless, not metres or metres squared. Ratios below 1 alone do not indicate estimator failure. null means unknown. Native enum fields retain MAVLink definitions; GPS fix_type 3+ is a 3D fix, landed_state 1=ground/2=air/3=takeoff/4=landing. Mission altitudes are metres in the stated frame. Commands/desired targets are not measurements of realized motion. Disarmed vehicles are not executing the uploaded mission; navigation controller targets can remain nonzero while disarmed.",
            "samples": samples[-180:],
            "extrema_10s": extrema,
            "coverage_age_s": {
                e["type"]: round(now - e["ts"], 2) for e in self.history if e["ts"] <= now
            },
            "active_plan": active,
        }
        if track == "operational":
            result["rules"] = self.rules(active, now)
            result["status_messages"] = [
                {
                    "evidence_id": e["evidence_id"],
                    "text": e["data"].get("text", ""),
                    "age_s": now - e["ts"],
                }
                for e in self.messages
                if 0 <= now - e["ts"] < 30
            ]
        return result
