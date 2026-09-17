"""Model-facing SI fields for the pinned ArduPilot firmware.

Original MAVLink messages remain in recordings/evidence. Explicit names avoid
asking a language model to repeatedly infer scaling and altitude references.
"""

import math

SCALES = {
    "TERRAIN_REPORT": {
        "lat": ("latitude_deg", 1e-7),
        "lon": ("longitude_deg", 1e-7),
        "spacing": ("grid_spacing_m", 1),
        "terrain_height": ("terrain_amsl_m", 1),
        "current_height": ("height_above_terrain_m", 1),
    },
    "DISTANCE_SENSOR": {
        name: (name + "_m", 0.01) for name in ("min_distance", "max_distance", "current_distance")
    },
    "GLOBAL_POSITION_INT": {
        "lat": ("latitude_deg", 1e-7),
        "lon": ("longitude_deg", 1e-7),
        "alt": ("altitude_amsl_m", 0.001),
        "relative_alt": ("altitude_relative_home_m", 0.001),
        "vx": ("velocity_north_m_s", 0.01),
        "vy": ("velocity_east_m_s", 0.01),
        "vz": ("velocity_down_m_s", 0.01),
        "hdg": ("heading_deg", 0.01),
    },
    "POSITION_TARGET_GLOBAL_INT": {
        "lat_int": ("latitude_deg", 1e-7),
        "lon_int": ("longitude_deg", 1e-7),
        "alt": ("altitude_in_coordinate_frame_m", 1),
    },
    "HOME_POSITION": {
        "latitude": ("latitude_deg", 1e-7),
        "longitude": ("longitude_deg", 1e-7),
        "altitude": ("altitude_amsl_m", 0.001),
    },
    "GPS_RAW_INT": {"eph": ("hdop", 0.01), "epv": ("vdop", 0.01)},
    "SYS_STATUS": {
        "voltage_battery": ("pack_voltage_V", 0.001),
        "current_battery": ("current_A", 0.01),
    },
    "BATTERY_STATUS": {
        "current_battery": ("current_A", 0.01),
        "current_consumed": ("consumed_mAh", 1),
    },
    "ATTITUDE": {
        k: (k + "_deg_s" if k.endswith("speed") else k + "_deg", 180 / math.pi)
        for k in ("roll", "pitch", "yaw", "rollspeed", "pitchspeed", "yawspeed")
    },
    "VFR_HUD": {
        "airspeed": ("airspeed_m_s", 1),
        "groundspeed": ("groundspeed_m_s", 1),
        "alt": ("altitude_amsl_m", 1),
        "climb": ("climb_m_s", 1),
        "heading": ("heading_deg", 1),
        "throttle": ("throttle_percent", 1),
    },
    "NAV_CONTROLLER_OUTPUT": {
        "nav_bearing": ("navigation_bearing_deg", 1),
        "target_bearing": ("target_bearing_deg", 1),
        "nav_roll": ("desired_roll_deg", 1),
        "nav_pitch": ("desired_pitch_deg", 1),
        "alt_error": ("altitude_error_m", 1),
        "xtrack_error": ("cross_track_error_m", 1),
        "wp_dist": ("waypoint_distance_m", 1),
        "aspd_error": ("airspeed_error_m_s", 1),
    },
    "EKF_STATUS_REPORT": {
        k: (k.replace("_variance", "_innovation_test_ratio_sqrt"), 1)
        for k in (
            "velocity_variance",
            "pos_horiz_variance",
            "pos_vert_variance",
            "compass_variance",
            "terrain_alt_variance",
        )
    },
}


def normalized_fields(message, fields, profile):
    result = {}
    for name, value in fields.items():
        dest, scale = SCALES.get(message, {}).get(name, (name, 1))
        if message == "SCALED_PRESSURE":
            dest, scale = {
                "press_abs": ("absolute_pressure_Pa", 100),
                "press_diff": ("differential_pressure_Pa", 100),
                "temperature": ("temperature_C", 0.01),
            }.get(name, (name, 1))
        if message in ("RC_CHANNELS", "SERVO_OUTPUT_RAW") and name.endswith("_raw"):
            dest = name.replace("_raw", "_pwm_us")
            if value == 65535:
                value = None
        if name == "rssi" and value == 255:
            value = None
        if name in ("eph", "epv", "voltage_battery", "hdg") and value == 65535:
            value = None
        if name == "satellites_visible" and value == 255:
            value = None
        if name in ("battery_remaining", "current_battery", "current_consumed") and value == -1:
            value = None
        if name == "battery_remaining":
            dest = "battery_remaining_percent"
        if message == "HEARTBEAT" and name == "base_mode":
            result["armed"] = bool(value & 128)
            continue
        if message == "BATTERY_STATUS" and name == "voltages":
            cells = [v / 1000 for v in value if v not in (0, 65535)]
            result["reported_pack_voltage_V"] = round(sum(cells), 4) if cells else None
            continue
        if message == "NAV_CONTROLLER_OUTPUT" and name == "aspd_error" and profile == "plane":
            # Pinned ArduPlane/GCS_MAVLink_Plane.cpp explicitly transmits cm/s,
            # despite MAVLink's declared m/s (source comment references PR#7933).
            scale = 0.01
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = round(value * scale, 6)
        result[dest] = value
    return result
