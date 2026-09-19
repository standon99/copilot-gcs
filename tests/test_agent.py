import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend import main
from backend.agent import TurnLimit, run_turn
from backend.agent_tools import TurnConflict, WorkspaceTurn, tool_schemas
from backend.monitoring import (
    AutomaticBudget,
    AutomaticRateLimited,
    Monitoring,
)
from backend.planning import Draft, Waypoint
from backend.settings import Preferences
from backend.telemetry import Telemetry
from backend.watches import WatchBook, WatchRule, reading


def vehicle():
    telemetry = Telemetry("v", "copter")
    return SimpleNamespace(
        id="v",
        profile="copter",
        telemetry=telemetry,
        closed=False,
        trial_task=None,
        draft=Draft(waypoints=[Waypoint(id="wp", lat=-35, lon=149, alt=20)]).model_dump(),
        watches=WatchBook(),
        params={"LOG_DISARMED": {"value": 0, "type": 2}},
        active=None,
        monitoring=Monitoring(),
        monitor_enabled=True,
        monitor_track="operational",
        inference=None,
        chat=[],
        parameter_proposals=[],
        agent_task=None,
        review=None,
        intent_proposal=None,
        geofence_proposal=None,
        revisions=[],
        agent_run=None,
    )


def call(name, args, ident="call1"):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": ident,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


def working(v=None, **prefs):
    v = v or vehicle()
    p = Preferences(**prefs)
    return v, p, WorkspaceTurn({"v": v}, ["v"], p)


async def test_native_multistep_results_feed_next_model_call_without_live_edits():
    v, p, turn = working()
    replies = [
        call("get_mission", {"vehicle_id": "v"}, "read"),
        call(
            "update_waypoint",
            {"vehicle_id": "v", "expected_revision": 0, "waypoint_id": "wp", "fields": {"alt": 35}},
            "edit",
        ),
        call("validate_mission", {"vehicle_id": "v"}, "check"),
        {"content": "Changed altitude to 35 m above home."},
    ]

    async def respond(system, messages, tools, options, on_event=None):
        assert v.draft["waypoints"][0]["alt"] == 20
        if len(messages) > 2:
            assert messages[-1]["role"] == "tool"
            assert json.loads(messages[-1]["content"])["ok"]
        return replies.pop(0), {"usage": {"total_tokens": 10}}

    run = {"steps": []}
    reply, meta = await run_turn(
        SimpleNamespace(tool_turn=respond), turn, "system", {}, p.model_dump(), run, lambda: None
    )
    assert "35" in reply and meta["rounds"] == 4 and meta["usage"]["total_tokens"] == 40
    assert turn.working["v"]["draft"]["waypoints"][0]["alt"] == 35
    assert len(run["steps"]) == 3 and not turn.missing_validation()


async def test_invalid_tool_arguments_return_error_and_model_can_repair():
    _, p, turn = working()
    replies = [
        call(
            "update_waypoint",
            {
                "vehicle_id": "v",
                "expected_revision": 99,
                "waypoint_id": "wp",
                "fields": {"alt": 30},
            },
            "bad",
        ),
        call("get_mission", {"vehicle_id": "v"}, "reread"),
        {"content": "No changes."},
    ]
    count = 0

    async def respond(system, messages, tools, options, on_event=None):
        nonlocal count
        if count == 1:
            assert not json.loads(messages[-1]["content"])["ok"]
        count += 1
        return replies.pop(0), {}

    run = {"steps": []}
    await run_turn(
        SimpleNamespace(tool_turn=respond), turn, "system", {}, p.model_dump(), run, lambda: None
    )
    assert run["steps"][0]["status"] == "error" and turn.working["v"]["draft"]["revision"] == 0


async def test_round_limit_discards_work_and_requires_final_validation():
    v, p, turn = working(agent_max_rounds=2)
    replies = [
        call(
            "update_waypoint",
            {"vehicle_id": "v", "expected_revision": 0, "waypoint_id": "wp", "fields": {"alt": 30}},
        ),
        {"content": "Done"},
    ]
    provider = SimpleNamespace(tool_turn=AsyncMock(side_effect=[(r, {}) for r in replies]))
    with pytest.raises(TurnLimit):
        await run_turn(provider, turn, "system", {}, p.model_dump(), {"steps": []}, lambda: None)
    assert v.draft["revision"] == 0


@pytest.mark.parametrize("change", ["draft", "epoch", "watches", "monitoring", "trial", "session"])
def test_all_target_conflicts_abort(change):
    v, _, turn = working()
    if change == "draft":
        v.draft["revision"] += 1
    if change == "epoch":
        v.telemetry.epoch += 1
    if change == "watches":
        v.watches.revision += 1
    if change == "monitoring":
        v.monitoring.revision += 1
    if change == "trial":
        v.trial_task = SimpleNamespace(done=lambda: False)
    if change == "session":
        turn.live["v"] = vehicle()
    with pytest.raises(TurnConflict):
        turn.execute("get_mission", {"vehicle_id": "v"})


def test_targeting_read_only_and_tool_allowlist():
    _, _, turn = working()
    with pytest.raises(ValueError):
        turn.execute("get_mission", {"vehicle_id": "other"})
    with pytest.raises(ValueError):
        turn.execute("arm", {"vehicle_id": "v"})
    turn.read_only = True
    with pytest.raises(ValueError):
        turn.execute(
            "configure_monitoring",
            {"vehicle_id": "v", "expected_revision": 0, "periodic_enabled": True},
        )
    assert "configure_monitoring" not in str(tool_schemas(True))


def test_watch_can_enable_event_only_and_monitoring_cannot_override_settings(monkeypatch):
    v, p, turn = working(monitor_enabled=False, automatic_min_interval=300)
    state = turn.execute(
        "configure_monitoring",
        {
            "vehicle_id": "v",
            "expected_revision": 0,
            "periodic_enabled": True,
            "interval_s": 10,
            "watch_advice_enabled": True,
            "focus": "Yaw response",
        },
    )
    assert (
        state["effective_interval_s"] == 300
        and not state["periodic_effective"]
        and state["watch_advice_effective"]
    )
    spec = WatchRule(
        label="Yaw",
        metric="yaw_rate_abs_deg_s",
        operator="gt",
        threshold=30,
        ai_prompt="Check the yaw response",
    ).model_dump()
    r = turn.execute(
        "manage_watch",
        {
            "vehicle_id": "v",
            "expected_revision": 0,
            "operation": "add",
            "rule": spec,
            "enabled": True,
        },
    )
    assert r["rules"][0]["enabled"] and not v.watches.rules
    monkeypatch.setattr(main.settings, "value", p)
    assert main.watch_inference_state(v) == "Enabled"
    with pytest.raises(ValueError):
        turn.execute(
            "configure_monitoring",
            {"vehicle_id": "v", "expected_revision": 1, "automatic_min_interval": 1},
        )


def test_global_budget_counts_failed_requests_restart_and_new_stricter_limit(tmp_path):
    path = tmp_path / "usage.json"
    budget = AutomaticBudget(path)
    budget.reserve(60, 100)
    with pytest.raises(AutomaticRateLimited):
        budget.reserve(60, 101)
    restarted = AutomaticBudget(path)
    assert not restarted.ready(60, 159) and restarted.ready(60, 160)
    assert not restarted.ready(300, 160)
    restarted.reserve(300, 400)


def test_merge_watch_config_preserves_triggers_arriving_during_model_turn():
    v, _, turn = working()
    spec = WatchRule(label="Speed", metric="groundspeed_m_s", operator="gt", threshold=5)
    original = v.watches.add(spec)
    original["enabled"] = True
    clone = copy.deepcopy(v.watches)
    clone.edit(clone.revision, "notes", notes="New concern")
    original.update(latched=True, count=4, last_trigger=100)
    v.watches.pending[original["id"]] = {"at": 100}
    v.watches.apply_configuration(clone)
    assert v.watches.rules[0]["latched"] and v.watches.rules[0]["count"] == 4
    assert v.watches.pending and v.watches.notes == "New concern"


def test_altitude_change_and_yaw_rate_evidence_with_gap():
    v = vehicle()
    t = v.telemetry

    def ingest(kind, data, at):
        t.ingest(
            {
                "type": kind,
                "data": data,
                "ts": at,
                "epoch": 0,
                "seq": len(t.history) + 1,
                "sysid": 1,
            }
        )

    for now in range(100, 111):
        ingest("GPS_RAW_INT", {"fix_type": 3}, now)
        ingest(
            "GLOBAL_POSITION_INT",
            {
                "lat": -350000000,
                "lon": 1490000000,
                "alt": 600000,
                "relative_alt": (now - 100) * 1000,
            },
            now,
        )
    value = reading(t, "relative_alt_change_m", 110, 10)
    assert value["value"] == 10 and len(value["evidence"]) == 2
    assert reading(t, "relative_alt_change_m", 110, 20) is None
    ingest("ATTITUDE", {"yawspeed": -1}, 110)
    assert reading(t, "yaw_rate_abs_deg_s", 110)["value"] == pytest.approx(57.2958)
    t.history = [e for e in t.history if not 102 < e["ts"] < 108]
    assert reading(t, "relative_alt_change_m", 110, 10) is None


async def test_endpoint_commit_and_cancel_are_reviewable(monkeypatch):
    v = vehicle()
    monkeypatch.setattr(main, "vehicles", {"v": v})
    monkeypatch.setattr(main, "event", lambda *a: None)
    monkeypatch.setattr(main.store, "put", lambda *a: None)
    replies = [
        call(
            "update_waypoint",
            {"vehicle_id": "v", "expected_revision": 0, "waypoint_id": "wp", "fields": {"alt": 40}},
            "a",
        ),
        call("validate_mission", {"vehicle_id": "v"}, "b"),
        {"content": "Updated and checked."},
    ]
    monkeypatch.setattr(
        main.provider, "tool_turn", AsyncMock(side_effect=[(r, {}) for r in replies])
    )
    await main.interaction(
        main.Interaction(message="Raise altitude to 40 m above home", targets=["v"], enabled=True)
    )
    assert v.draft["revision"] == 1 and v.draft["waypoints"][0]["alt"] == 40
    assert len(v.chat[-1]["tool_trace"]) == 2 and v.agent_run["status"] == "completed"

    async def pending(*args, **kwargs):
        await asyncio.Future()

    monkeypatch.setattr(main.provider, "tool_turn", pending)
    task = asyncio.create_task(
        main.interaction(main.Interaction(message="read", targets=["v"], enabled=True))
    )
    await asyncio.sleep(0)
    await main.cancel_agent("v")
    with pytest.raises(main.HTTPException):
        await task
    assert v.agent_run["status"] == "cancelled" and v.draft["revision"] == 1


def test_native_tool_schemas_use_explicit_objects_for_optional_configuration():
    schemas = {s["function"]["name"]: s["function"]["parameters"] for s in tool_schemas()}
    rule = schemas["manage_watch"]["properties"]["rule"]
    assert rule["type"] == "object" and "anyOf" not in rule
    assert "rule" not in schemas["manage_watch"]["required"]
    assert (
        schemas["update_waypoint"]["properties"]["fields"]["properties"]["alt"]["type"] == "number"
    )
    assert "$ref" not in json.dumps(schemas)


async def test_repeated_identical_bad_tool_calls_stop_before_turn_budget():
    _, p, turn = working()
    provider = SimpleNamespace(
        tool_turn=AsyncMock(
            side_effect=[
                (call("get_mission", {"vehicle_id": "unselected"}, str(i)), {}) for i in range(3)
            ]
        )
    )
    with pytest.raises(TurnLimit, match="Repeated identical"):
        await run_turn(provider, turn, "system", {}, p.model_dump(), {"steps": []}, lambda: None)
    assert provider.tool_turn.call_count == 3


async def test_malformed_assessment_does_not_requeue_a_budget_blocked_repair():
    from backend.provider import AssessmentValidationError, Provider

    provider = Provider(
        SimpleNamespace(value=Preferences(), get=lambda: Preferences().model_dump())
    )
    provider.complete = AsyncMock(
        side_effect=[ValueError("Invalid JSON"), AutomaticRateLimited(1000)]
    )
    with pytest.raises(AssessmentValidationError, match="repair blocked"):
        await provider.monitor({"samples": [], "extrema_10s": {}})
    assert provider.complete.call_count == 2


def test_shared_scheduler_uses_oldest_due_vehicle_and_prioritizes_queued_events(monkeypatch):
    first, second, third = vehicle(), vehicle(), vehicle()
    for v, due in zip((first, second, third), (100, 80, 90)):
        v.next_monitor = due
        v.telemetry.latest["HEARTBEAT"] = {}
    monkeypatch.setattr(main, "vehicles", {"a": first, "b": second, "c": third})
    monkeypatch.setattr(main.settings, "value", Preferences(monitor_enabled=True))
    monkeypatch.setattr(main.provider, "automatic_ready", lambda now: True)
    for expected in (second, third, first):
        chosen, batch = main.due_assessment(100)
        assert chosen is expected and not batch
        chosen.next_monitor = 110
    assert main.due_assessment(100) is None
    first.watches.pending["new"] = {"id": "new", "at": 99}
    third.watches.pending["old"] = {"id": "old", "at": 98}
    chosen, batch = main.due_assessment(100)
    assert chosen is third and batch[0]["id"] == "old"
    assert first.watches.pending and not third.watches.pending
    monkeypatch.setattr(main.provider, "automatic_ready", lambda now: False)
    assert main.due_assessment(100) is None and first.watches.pending
