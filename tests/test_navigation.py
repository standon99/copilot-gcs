import pytest

from backend.navigation import destination, navigation_cue
from backend.planning import distance
from backend.telemetry import Telemetry


def telemetry():
    t = Telemetry("v", "copter")
    values = {
        "HEARTBEAT": {"base_mode": 128, "mode": "AUTO"},
        "GLOBAL_POSITION_INT": {
            "lat": -353632610,
            "lon": 1491652300,
            "alt": 600000,
            "relative_alt": 16000,
        },
        "NAV_CONTROLLER_OUTPUT": {"nav_bearing": 90, "wp_dist": 120},
        "MISSION_CURRENT": {"seq": 1},
    }
    for n, (typ, data) in enumerate(values.items()):
        t.ingest({"type": typ, "data": data, "epoch": 0, "seq": n, "sysid": 1, "ts": 100})
    return t


def test_target_and_projected_carrot_separate_with_correct_home_offset():
    t = telemetry()
    plan = {"waypoints": [{"command": 16, "lat": -35.36, "lon": 149.16}]}
    cue = navigation_cue(t, plan, now=101)
    assert cue["target"]["lat"] == -35.36
    assert cue["target"]["source"] == "Uploaded mission item 1"
    assert cue["carrot"]["length"] == 50
    assert cue["carrot"]["lon"] > 149.165230
    assert abs(cue["carrot"]["lat"] + 35.363261) < 0.00001


def test_reported_target_preferred_and_mask_enforced():
    t = telemetry()
    t.latest["POSITION_TARGET_GLOBAL_INT"] = {
        "ts": 100,
        "data": {
            "coordinate_frame": 6,
            "type_mask": 0,
            "lat_int": -350000000,
            "lon_int": 1490000000,
        },
    }
    assert navigation_cue(t, now=101)["target"]["source"] == "Autopilot position target"
    t.latest["POSITION_TARGET_GLOBAL_INT"]["data"]["type_mask"] = 1
    assert navigation_cue(t, now=101)["target"] is None
    t.latest["POSITION_TARGET_GLOBAL_INT"]["data"].update(type_mask=0, lat_int=None)
    assert navigation_cue(t, now=101)["target"] is None


@pytest.mark.parametrize("condition", ["stale", "disarmed", "manual", "position"])
def test_cues_hidden_without_current_navigation(condition):
    t = telemetry()
    if condition == "disarmed":
        t.latest["HEARTBEAT"]["data"]["base_mode"] = 0
    if condition == "manual":
        t.latest["HEARTBEAT"]["data"]["mode"] = "STABILIZE"
    if condition == "position":
        t.latest["GLOBAL_POSITION_INT"]["ts"] = 90
    assert navigation_cue(t, now=105 if condition == "stale" else 101) is None


def test_null_distance_and_antimeridian_projection():
    t = telemetry()
    t.latest["NAV_CONTROLLER_OUTPUT"]["data"]["wp_dist"] = None
    assert navigation_cue(t, now=101)["carrot"]["length"] == 20
    result = destination(0, 179.9999, 90, 50)
    assert -180 <= result["lon"] < -179.99
    assert abs(distance({"lon": 0, "lat": 0}, destination(0, 0, 90, 50)) - 50) < 0.1
