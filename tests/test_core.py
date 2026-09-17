import json
import subprocess
import sys
import time

import pytest

from backend.config import ROOT
from backend.lab import score
from backend.normalization import normalized_fields
from backend.planning import Draft, Intent, Waypoint, apply_patch, check, revise
from backend.provider import sandbox_command
from backend.telemetry import Telemetry


def draft():
    return Draft(
        waypoints=[
            Waypoint(id="a", lat=0, lon=0, alt=30),
            Waypoint(id="b", lat=0, lon=0.002, alt=30),
        ]
    ).model_dump()


def test_revision_conflict():
    with pytest.raises(ValueError):
        revise(draft(), draft(), 4)


def test_patch_preserves_intent():
    d = draft()
    d["intent"]["max_alt"] = 40
    new = apply_patch(d, [{"op": "update", "id": "a", "fields": {"alt": 35}}], 0)
    assert new["revision"] == 1 and new["intent"] == d["intent"] and d["waypoints"][0]["alt"] == 30


@pytest.mark.parametrize(
    "op",
    [
        {"op": "shell", "command": "ignored"},
        {"op": "update", "id": "a", "fields": {"intent": {}}},
        {"op": "reorder", "ids": ["a", "a"]},
        {"op": "remove", "id": "unknown"},
    ],
)
def test_reject_unauthorized_patch(op):
    with pytest.raises(ValueError):
        apply_patch(draft(), [op], 0)


def test_exclusion_leg_not_just_points():
    d = draft()
    d["intent"]["exclusions"] = [
        [(0.0009, -0.001), (0.0011, -0.001), (0.0011, 0.001), (0.0009, 0.001)]
    ]
    result = check(d, "copter")
    assert not result["upload_allowed"]
    assert any(f["code"] == "excluded_leg" for f in result["findings"])
    assert not any(f["code"] == "excluded_point" for f in result["findings"])


def test_altitude_frame_conversion():
    d = draft()
    d["intent"]["max_alt"] = 50
    d["waypoints"][0].update(frame=0, alt=630)
    assert check(d, "copter", {"lat": 0, "lon": 0, "alt": 600})["upload_allowed"]
    assert not check(d, "copter")["upload_allowed"]


def test_profile_commands():
    d = draft()
    d["waypoints"][0]["command"] = 22
    assert not check(d, "rover")["upload_allowed"]
    assert check(d, "copter")["upload_allowed"]


def test_intent_validation():
    with pytest.raises(ValueError):
        Intent(min_alt=30, max_alt=20)
    with pytest.raises(ValueError):
        Intent(exclusions=[[(0, 0), (1, 1)]])
    with pytest.raises(ValueError):
        Waypoint(lat=float("nan"), lon=1)


def ingest(t, typ, data, ts, seq):
    t.ingest(
        {"kind": "message", "type": typ, "data": data, "ts": ts, "epoch": 0, "seq": seq, "sysid": 1}
    )


def test_blind_observation_allowlist_and_causality():
    t = Telemetry("v", "copter")
    now = time.time()
    ingest(t, "SIMSTATE", {"scenario": "SECRET_FAULT"}, now - 1, 1)
    ingest(t, "PARAM_VALUE", {"name": "SIM_GPS1_ENABLE", "value": 0}, now - 1, 2)
    ingest(t, "STATUSTEXT", {"text": "GPS failsafe SECRET_FAULT"}, now - 1, 3)
    ingest(
        t,
        "GLOBAL_POSITION_INT",
        {"lat": 1, "lon": 2, "alt": 10, "relative_alt": 0, "future": "SECRET"},
        now + 10,
        4,
    )
    ingest(t, "EKF_STATUS_REPORT", {"flags": 123, "velocity_variance": 2.2}, now - 1, 5)
    obs = t.observations(track="telemetry", now=now)
    encoded = json.dumps(obs)
    assert (
        "SECRET" not in encoded
        and "SIM_" not in encoded
        and "flags" not in encoded
        and "failsafe" not in encoded
    )
    assert len(obs["samples"]) == 1
    assert "status_messages" in t.observations(track="operational", now=now)


def test_missing_and_stale_are_unknown():
    t = Telemetry("v", "rover")
    out = t.rules()
    assert {"link_stale", "gps_unknown"} <= {r["code"] for r in out}


def test_epoch_resets_history():
    t = Telemetry("v", "rover")
    ingest(t, "VFR_HUD", {"groundspeed": 10}, time.time(), 1)
    e = {
        "kind": "message",
        "type": "VFR_HUD",
        "data": {"groundspeed": 0},
        "ts": time.time(),
        "epoch": 1,
        "seq": 2,
        "sysid": 1,
    }
    t.ingest(e)
    assert len(t.history) == 1 and t.epoch == 1


def test_no_zero_for_unknown_battery():
    t = Telemetry("v", "copter")
    ingest(t, "SYS_STATUS", {"battery_remaining": -1, "voltage_battery": 65535}, time.time(), 1)
    assert t.snapshot()["voltage"] is None and t.snapshot()["battery"] is None


def test_active_intent_not_future_draft():
    t = Telemetry("v", "copter")
    now = time.time()
    ingest(t, "HEARTBEAT", {"base_mode": 128, "mode": "AUTO"}, now, 1)
    ingest(
        t, "GLOBAL_POSITION_INT", {"lat": 0, "lon": 0, "relative_alt": 50000, "alt": 650000}, now, 2
    )
    active = draft()
    active["intent"]["max_alt"] = 40
    assert any(r["code"] == "intent_max_alt" for r in t.rules(active))


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS sandbox only")
@pytest.mark.parametrize("target", [".env", "runtime/copilot/private-test.json", ".git/config"])
def test_os_sandbox_denies_private_reads(target):
    path = ROOT / target
    if not path.exists():
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text("private test fixture")
    command, _ = sandbox_command()
    cmd = command[:-3] + [sys.executable, "-c", f"open({str(path)!r}).read()"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode != 0 and "Operation not permitted" in r.stderr


def test_score_is_phase_bounded():
    p = {
        "observed_at": 20,
        "completed_at": 25,
        "status": "concern",
        "incidents": [{"severity": "warning", "summary": "GPS fix unavailable", "evidence": ["e"]}],
    }
    assert score([p], "gps_loss", 10, 30, {"e": 20})["first_detection_s"] == 15
    assert not score([p], "gps_loss", 30, 40, {"e": 20})["symptom_detected"]
    assert not score([p], "gps_loss", 10, 30, {"e": 5})["symptom_detected"]


def test_model_si_contract_and_ardupilot_airspeed_quirk():
    fields = normalized_fields(
        "GLOBAL_POSITION_INT",
        {"relative_alt": -106, "alt": 584000, "lat": -353632610, "lon": 1491652300},
        "rover",
    )
    assert fields["altitude_relative_home_m"] == -0.106
    assert fields["altitude_amsl_m"] == 584
    assert fields["latitude_deg"] == -35.363261
    assert (
        normalized_fields("NAV_CONTROLLER_OUTPUT", {"aspd_error": -119}, "plane")[
            "airspeed_error_m_s"
        ]
        == -1.19
    )
    assert normalized_fields("GPS_RAW_INT", {"eph": 121, "epv": 65535}, "copter") == {
        "hdop": 1.21,
        "vdop": None,
    }


def test_pinned_home_altitude_does_not_follow_new_home():
    t = Telemetry("v", "copter")
    now = time.time()
    ingest(t, "HEARTBEAT", {"base_mode": 128, "mode": "AUTO"}, now, 1)
    ingest(
        t, "GLOBAL_POSITION_INT", {"lat": 0, "lon": 0, "relative_alt": 20000, "alt": 650000}, now, 2
    )
    active = draft()
    active["intent"]["max_alt"] = 40
    active["home"] = {"lat": 0, "lon": 0, "alt": 600}
    assert any(r["code"] == "intent_max_alt" for r in t.rules(active))
