"""Telemetry-backed map cues; projected bearing cues are labelled as projections."""

import math
import time


def destination(lat, lon, bearing, metres):
    lat, lon, bearing = map(math.radians, (lat, lon, bearing))
    delta = metres / 6371000
    y = math.asin(
        math.sin(lat) * math.cos(delta) + math.cos(lat) * math.sin(delta) * math.cos(bearing)
    )
    x = lon + math.atan2(
        math.sin(bearing) * math.sin(delta) * math.cos(lat),
        math.cos(delta) - math.sin(lat) * math.sin(y),
    )
    return {"lat": math.degrees(y), "lon": (math.degrees(x) + 180) % 360 - 180}


def navigation_cue(telemetry, active=None, now=None):
    now = now or time.time()
    s = telemetry.snapshot(now)
    age = s["coverage"]
    if not s["armed"] or s["mode"] not in ("AUTO", "GUIDED", "RTL", "LOITER"):
        return None
    if (
        not s["position"]
        or s["heartbeat_age"] is None
        or s["heartbeat_age"] > 3
        or age.get("GLOBAL_POSITION_INT", 999) > 3
    ):
        return None
    target = None
    event = telemetry.latest.get("POSITION_TARGET_GLOBAL_INT", {})
    t = event.get("data", {})
    if (
        now - event.get("ts", 0) <= 3
        and isinstance(t.get("type_mask"), int)
        and not (t["type_mask"] & 3)
    ):
        if t.get("coordinate_frame") in (0, 3, 5, 6, 10, 11) and all(
            isinstance(t.get(k), (int, float)) and math.isfinite(t[k])
            for k in ("lat_int", "lon_int")
        ):
            lat, lon = t.get("lat_int", 0) / 1e7, t.get("lon_int", 0) / 1e7
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
                target = {
                    "lat": lat,
                    "lon": lon,
                    "source": "Autopilot position target",
                    "age": round(now - event["ts"], 2),
                }
    seq = s["mission_seq"]
    if target is None and s["mode"] == "AUTO" and active and age.get("MISSION_CURRENT", 999) <= 3:
        # Uploaded mission has a synthetic home at sequence zero.
        if isinstance(seq, int) and 1 <= seq <= len(active["waypoints"]):
            w = active["waypoints"][seq - 1]
            if w["command"] in (16, 17, 19, 21, 22) and (w["lat"] or w["lon"]):
                target = {
                    "lat": w["lat"],
                    "lon": w["lon"],
                    "source": f"Uploaded mission item {seq}",
                    "age": age["MISSION_CURRENT"],
                }
    nav = telemetry.latest.get("NAV_CONTROLLER_OUTPUT", {}).get("data", {})
    carrot = None
    if age.get("NAV_CONTROLLER_OUTPUT", 999) <= 3 and nav.get("nav_bearing") is not None:
        distance = nav.get("wp_dist")
        length = min(50, max(5, distance / 2 if distance is not None else 20))
        carrot = {
            **destination(s["position"]["lat"], s["position"]["lon"], nav["nav_bearing"], length),
            "bearing": nav["nav_bearing"],
            "length": length,
            "source": "Projected navigation bearing (5–50 m display cue)",
        }
    if not target and not carrot:
        return None
    return {
        "target": target,
        "carrot": carrot,
        "mission_seq": seq,
        "wp_distance": nav.get("wp_dist") if age.get("NAV_CONTROLLER_OUTPUT", 999) <= 3 else None,
    }
