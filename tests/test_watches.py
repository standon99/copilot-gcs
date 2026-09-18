"""Watch timing, sensor validity, blind isolation and operator boundaries."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend import main
from backend.interaction import validate_edits
from backend.planning import Draft
from backend.settings import Preferences
from backend.telemetry import Telemetry
from backend.watches import WatchBook, WatchRule, add_watch_context, reading


def ingest(t, typ, data, now=100, epoch=0):
    t.ingest(dict(type=typ, data=data, ts=now, epoch=epoch, seq=len(t.history) + 1, sysid=1))


def observe(t, value, now=100, armed=True):
    ingest(t, "HEARTBEAT", {"base_mode": 128 if armed else 0, "mode": "AUTO"}, now)
    ingest(t, "VFR_HUD", {"groundspeed": value}, now)


def rule(**changes):
    return WatchRule.model_validate(
        dict(label="Speed", metric="groundspeed_m_s", operator="gt", threshold=5, **changes)
    ).model_dump()


def enabled(**changes):
    b = WatchBook()
    r = b.add(rule(**changes))
    r["enabled"] = True
    return b, r


def test_startup_position_waits_for_a_real_fix_including_drifting_near_zero():
    t = Telemetry("v", "plane")
    ingest(t, "GPS_RAW_INT", {"fix_type": 0})
    ingest(t, "GLOBAL_POSITION_INT", {"lat": 2803, "lon": -1053, "alt": 500, "relative_alt": 0})
    assert not t.snapshot(100)["position_valid"]
    ingest(t, "GPS_RAW_INT", {"fix_type": 6}, 101)
    assert not t.snapshot(101)["position_valid"]  # wait for a position after that fix
    ingest(t, "GLOBAL_POSITION_INT", {"lat": 0, "lon": 0, "alt": 500, "relative_alt": 0}, 101.1)
    assert t.snapshot(101.1)["position_valid"]  # legitimate position at 0,0 allowed
    ingest(t, "GPS_RAW_INT", {"fix_type": 0}, 102)
    assert t.snapshot(102)["position_valid"]  # don't discard initialized dead reckoning
    ingest(t, "HEARTBEAT", {"base_mode": 0}, 103, epoch=1)
    assert not t.snapshot(103)["position_valid"]


def test_dwell_hysteresis_cooldown_and_latched_acknowledgement():
    t = Telemetry("v", "copter")
    b, r = enabled(dwell_s=1, hysteresis=1, cooldown_s=10)
    observe(t, 6)
    assert not b.evaluate(t, 100)
    observe(t, 6, 101)
    assert len(b.evaluate(t, 101)) == 1 and r["latched"]
    r["latched"] = False  # acknowledgement doesn't clear an ongoing breach
    observe(t, 4.5, 102)
    assert not b.evaluate(t, 102) and r["state"] == "triggered"
    observe(t, 4, 103)
    assert not b.evaluate(t, 103) and r["state"] == "watching"
    observe(t, 6, 104)
    assert not b.evaluate(t, 104)
    observe(t, 6, 105)
    assert not b.evaluate(t, 105) and r["state"] == "triggered"
    observe(t, 6, 111)
    assert len(b.evaluate(t, 111)) == 1
    observe(t, 6, 130)
    assert not b.evaluate(t, 130)  # sustained condition never burns more calls


def test_stale_data_breaks_dwell_and_does_not_retrigger_an_active_breach():
    t = Telemetry("v", "plane")
    b, r = enabled(dwell_s=2)
    observe(t, 6)
    b.evaluate(t, 100)
    assert not b.evaluate(t, 104) and r["state"] == "unknown"
    observe(t, 6, 105)
    assert not b.evaluate(t, 105)
    observe(t, 6, 107)
    assert len(b.evaluate(t, 107)) == 1
    b.evaluate(t, 150)
    observe(t, 6, 170)
    assert not b.evaluate(t, 170)


def test_phase_is_unknown_without_evidence_and_takeoff_is_included():
    t = Telemetry("v", "plane")
    b, r = enabled(scope="airborne")
    observe(t, 6)
    assert not b.evaluate(t, 100) and r["state"] == "unknown"
    ingest(t, "EXTENDED_SYS_STATE", {"landed_state": 1})
    assert not b.evaluate(t, 100) and r["state"] == "inactive"
    ingest(t, "EXTENDED_SYS_STATE", {"landed_state": 3})
    assert len(b.evaluate(t, 100)) == 1
    observe(t, 6, 101, armed=False)
    b.evaluate(t, 101)
    assert r["state"] == "inactive" and r["latched"]


def test_agl_never_substitutes_relative_home_and_rejects_invalid_range():
    t = Telemetry("v", "copter")
    ingest(t, "GPS_RAW_INT", {"fix_type": 6})
    ingest(
        t,
        "GLOBAL_POSITION_INT",
        {"lat": -350000000, "lon": 1490000000, "alt": 600000, "relative_alt": 20000},
    )
    assert reading(t, "agl_m", 100) is None
    ingest(t, "ATTITUDE", {"roll": 0, "pitch": 0})
    data = dict(
        id=1,
        orientation=25,
        min_distance=20,
        max_distance=4000,
        current_distance=900,
        signal_quality=0,
    )
    ingest(t, "DISTANCE_SENSOR", data)
    assert reading(t, "agl_m", 100)["value"] == 9
    for patch in (
        {"signal_quality": 1},
        {"orientation": 0},
        {"current_distance": 4000},
        {"current_distance": None},
    ):
        ingest(t, "DISTANCE_SENSOR", {**data, **patch})
        assert reading(t, "agl_m", 100) is None
    ingest(t, "DISTANCE_SENSOR", data)
    ingest(t, "ATTITUDE", {"roll": 0.5, "pitch": 0})
    assert reading(t, "agl_m", 100) is None
    assert reading(t, "agl_m", 104) is None


def test_local_terrain_coverage_must_be_fresh_and_available():
    t = Telemetry("v", "plane")
    ingest(t, "GPS_RAW_INT", {"fix_type": 6})
    ingest(
        t,
        "GLOBAL_POSITION_INT",
        {"lat": -350000000, "lon": 1490000000, "alt": 600000, "relative_alt": 20000},
    )
    terrain = dict(
        lat=-350000000, lon=1490000000, terrain_height=592, current_height=0, spacing=100
    )
    ingest(t, "TERRAIN_REPORT", terrain)
    assert reading(t, "agl_m", 100)["value"] == 8
    for patch in ({"spacing": 0}, {"lat": -351000000}, {"terrain_height": None}):
        ingest(t, "TERRAIN_REPORT", {**terrain, **patch})
        assert reading(t, "agl_m", 100) is None


def test_coalescing_bounded_calls_pause_and_reboot():
    t = Telemetry("v", "rover")
    b, r = enabled()
    observe(t, 6)
    triggers = b.evaluate(t, 100)
    b.queue(triggers, False, "Paused")
    assert not b.pending and r["ai_status"] == "Paused"
    b.queue(triggers, True, "")
    assert len(b.take_pending(100, 60)) == 1
    b.queue(triggers, True, "")
    b.queue(triggers, True, "")
    assert len(b.pending) == 1 and b.take_pending(159, 60) == []
    assert len(b.take_pending(160, 60)) == 1
    ingest(t, "HEARTBEAT", {"base_mode": 128}, 161, epoch=1)
    b.evaluate(t, 161)
    assert not r["enabled"] and not b.pending


@pytest.mark.parametrize(
    "patch",
    [
        {"metric": "eval"},
        {"threshold": float("nan")},
        {"action": "RTL"},
        {"code": "print(1)"},
        {"cooldown_s": 0},
        {"scope": "cruise"},
    ],
)
def test_rule_language_rejects_code_actions_and_unbounded_values(patch):
    with pytest.raises(ValidationError):
        WatchRule.model_validate({**rule(), **patch})


def test_event_observation_keeps_exact_evidence_even_after_downsampling():
    t = Telemetry("v", "rover")
    b, r = enabled()
    b.notes = "Suspected prop damage, not confirmed"
    observe(t, 6)
    triggers = b.evaluate(t, 100)
    observe(t, 2, 100.5)
    obs = t.observations(track="operational", now=100.5)
    add_watch_context(obs, b, triggers, t)
    assert obs["assessment_trigger"] == "watch_rule"
    assert set(triggers[0]["evidence"]) <= {e["evidence_id"] for e in obs["samples"]}
    assert "Suspected" in obs["operator_watch_notes"]
    blind = t.observations(track="telemetry", now=100.5)
    assert "watch" not in json.dumps(blind).lower() and "prop damage" not in json.dumps(blind)


@pytest.mark.parametrize(
    "track,trial,enabled,watch_enabled,expected",
    [
        ("operational", False, True, True, "Enabled"),
        ("telemetry", False, True, True, "telemetry-only"),
        ("operational", True, True, True, "diagnostics"),
        ("operational", False, False, True, "Enabled"),
        ("operational", False, True, False, "Settings"),
    ],
)
def test_event_inference_respects_pause_track_and_trial(
    monkeypatch, track, trial, enabled, watch_enabled, expected
):
    monkeypatch.setattr(
        main.settings,
        "value",
        Preferences(monitor_enabled=enabled, watch_inference_enabled=watch_enabled),
    )
    v = SimpleNamespace(
        trial_task=SimpleNamespace(done=lambda: False) if trial else None,
        monitor_track=track,
        monitor_enabled=True,
    )
    assert expected in main.watch_inference_state(v)


async def test_monitor_does_not_leak_operator_notes_or_triggers_to_trials(monkeypatch, tmp_path):
    t = Telemetry("v", "copter")
    observe(t, 6)
    b, r = enabled()
    b.notes = "SECRET OPERATOR HYPOTHESIS"
    v = SimpleNamespace(
        id="v",
        telemetry=t,
        active=None,
        monitor_track="operational",
        watches=b,
        trial_task=SimpleNamespace(done=lambda: False),
        closed=False,
        predictions=[],
        folder=tmp_path,
        inference=None,
    )
    fake = AsyncMock(return_value={"observed_at": 100})
    monkeypatch.setattr(main.provider, "monitor", fake)
    monkeypatch.setattr(main, "event", lambda *a: None)
    await main.monitor(v)
    obs = fake.call_args.args[0]
    assert "watch_rules" not in obs and "SECRET" not in json.dumps(obs)


async def test_edit_watches_conflict_cross_vehicle_and_no_vehicle_commands(monkeypatch):
    b = WatchBook()
    v = SimpleNamespace(id="v", trial_task=None, watches=b)
    monkeypatch.setattr(main, "vehicles", {"v": v})
    monkeypatch.setattr(main, "workspace", AsyncMock(return_value={}))
    monkeypatch.setattr(main.store, "put", lambda *a: None)
    monkeypatch.setattr(main, "event", lambda *a: None)
    monkeypatch.setattr(
        main, "submit", lambda *a: pytest.fail("Watch must never command a vehicle")
    )
    await main.edit_watches(
        "v", main.WatchEdit(expected_revision=0, operation="add", rule=WatchRule(**rule()))
    )
    r = b.rules[0]
    assert not r["enabled"]
    with pytest.raises(HTTPException):
        await main.edit_watches(
            "v", main.WatchEdit(expected_revision=0, operation="enable", id=r["id"])
        )
    with pytest.raises(HTTPException):
        await main.edit_watches(
            "v", main.WatchEdit(expected_revision=b.revision, operation="enable", id="other")
        )
    await main.edit_watches(
        "v", main.WatchEdit(expected_revision=b.revision, operation="enable", id=r["id"])
    )
    assert r["enabled"]
    await main.edit_watches(
        "v",
        main.WatchEdit(
            expected_revision=b.revision,
            operation="update",
            id=r["id"],
            rule=WatchRule(**rule()),
        ),
    )
    assert not r["enabled"]


def test_watch_batch_and_revision_conflicts_never_partially_apply():
    b = WatchBook()
    v = SimpleNamespace(
        id="v",
        watches=b,
        telemetry=SimpleNamespace(epoch=0),
        closed=False,
        draft=Draft().model_dump(),
        params={},
        profile="copter",
    )
    before = {
        "v": {"epoch": 0, "draft": copy.deepcopy(v.draft), "parameters": [], "watches": b.public()}
    }
    raw = {"reply": "Proposed only", "vehicles": [{"vehicle_id": "v", "watch_rules": [rule()]}]}
    _, edits = validate_edits(raw, before, {"v": v})
    assert edits[0]["watch_rules"] and b.rules == []
    b.revision += 1
    with pytest.raises(ValueError, match="Watch rules changed"):
        validate_edits(raw, before, {"v": v})


def test_review_hash_ignores_runtime_counters_but_retains_configuration():
    v = SimpleNamespace(params={"STAT_RUNTIME": {"value": 1}, "WPNAV_SPEED": {"value": 500}})
    original = main.parameter_hash(v)
    v.params["STAT_RUNTIME"]["value"] = 2
    assert main.parameter_hash(v) == original
    v.params["WPNAV_SPEED"]["value"] = 600
    assert main.parameter_hash(v) != original


def test_voltage_watch_uses_volts_and_unknown_sentinel_cannot_trigger():
    t = Telemetry("v", "copter")
    b = WatchBook()
    r = b.add(
        {
            "label": "Battery sag",
            "metric": "battery_voltage_v",
            "operator": "lt",
            "threshold": 11,
            "scope": "always",
        }
    )
    r["enabled"] = True
    observe(t, 0)
    ingest(t, "SYS_STATUS", {"voltage_battery": 65535, "battery_remaining": -1})
    assert not b.evaluate(t, 100) and r["state"] == "unknown"
    ingest(t, "SYS_STATUS", {"voltage_battery": 10500, "battery_remaining": -1})
    assert len(b.evaluate(t, 100)) == 1 and r["reading"]["value"] == 10.5
