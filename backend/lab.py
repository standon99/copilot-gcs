"""SITL-only fault adapters. Scenario truth never enters inference payloads."""

CATALOG = {
    "nominal": {
        "label": "Nominal control",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {},
        "symptoms": [],
    },
    "gps_loss": {
        "label": "GPS receiver loss",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {"SIM_GPS1_ENABLE": 0},
        "symptoms": ["gps", "satellite", "position", "fix", "navigation"],
    },
    "gps_jump": {
        "label": "GPS position jump",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {"SIM_GPS1_GLTCH_X": 0.001},
        "symptoms": ["gps", "position", "jump", "estimator", "innovation"],
    },
    "low_voltage": {
        "label": "Battery voltage sag",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {"SIM_BATT_VOLTAGE": 9.0},
        "symptoms": ["battery", "voltage", "power"],
    },
    "rc_loss": {
        "label": "RC receiver loss",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {"SIM_RC_FAIL": 1},
        "symptoms": ["radio", "rc", "receiver", "failsafe"],
    },
    "wind": {
        "label": "Strong crosswind",
        "profiles": ["copter", "plane"],
        "parameters": {"SIM_WIND_SPD": 15, "SIM_WIND_DIR": 90},
        "symptoms": ["wind", "drift", "track", "airspeed", "groundspeed"],
    },
    "baro_drift": {
        "label": "Barometer drift",
        "profiles": ["copter", "plane"],
        "parameters": {"SIM_BARO_DRIFT": 2.0},
        "symptoms": ["altitude", "barometer", "barometric", "vertical", "estimator"],
    },
    "motor_loss": {
        "label": "Motor 1 reduced output",
        "profiles": ["copter"],
        "parameters": {"SIM_ENGINE_FAIL": 1, "SIM_ENGINE_MUL": 0.65},
        "symptoms": ["motor", "attitude", "roll", "pitch", "actuator", "control"],
    },
    "airspeed_stuck": {
        "label": "Airspeed held at 5 m/s",
        "profiles": ["plane"],
        "parameters": {"SIM_ARSPD_FAIL": 5},
        "symptoms": ["airspeed", "air speed", "stall", "speed"],
    },
    "mag_failure": {
        "label": "Primary magnetometer failure",
        "profiles": ["copter", "plane", "rover"],
        "parameters": {"SIM_MAG1_FAIL": 1},
        "symptoms": ["compass", "magnet", "heading", "yaw", "estimator"],
    },
}


def score(predictions, scenario, onset, end, evidence_times=None):
    """Transparent lexical screening; manual adjudication required for publication."""
    terms = CATALOG[scenario]["symptoms"]
    hits = []
    concerns = []
    evidence_times = evidence_times or {}
    unsupported_hits = 0
    for p in predictions:
        if not onset <= p["observed_at"] <= end:
            continue
        if p["status"] == "concern":
            concerns.append(p)
            matching = [
                i
                for i in p["incidents"]
                if i.get("severity") in ("warning", "critical", "unknown")
                and any(t in i["summary"].lower() for t in terms)
            ]
            if matching:
                if any(
                    onset <= evidence_times.get(eid, -1) <= p["observed_at"]
                    for i in matching
                    for eid in i.get("evidence", [])
                ):
                    hits.append(p)
                else:
                    unsupported_hits += 1
    assessed = len([p for p in predictions if onset <= p["observed_at"] <= end])
    return {
        "scoring": "v2 lexical symptom screening with post-onset evidence; needs human adjudication",
        "unqualified_symptom_mentions": unsupported_hits,
        "scenario": scenario,
        "assessment_count": assessed,
        "coverage": "assessed" if assessed else "unassessed",
        "symptom_detected": bool(hits) if terms and assessed else None,
        "first_detection_s": round(hits[0]["completed_at"] - onset, 2) if hits else None,
        "concerns": len(concerns),
        "nominal_false_alerts": len(concerns) if scenario == "nominal" and assessed else None,
        "limitation": "A miss can reflect unobservable conditions (e.g. motor loss while disarmed). A symptom match does not establish causal diagnosis.",
    }
