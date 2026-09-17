import copy
from types import SimpleNamespace

import pytest

from backend.interaction import parameter_context, validate_edits
from backend.planning import Draft
from backend.settings import Preferences


def setup_targets():
    live = {
        vid: SimpleNamespace(
            id=vid,
            profile="copter",
            closed=False,
            telemetry=SimpleNamespace(epoch=1),
            draft=Draft().model_dump(),
            params={"LOG_DISARMED": {"value": 0, "type": 2}},
        )
        for vid in ("one", "two")
    }
    before = {
        vid: {
            "epoch": 1,
            "draft": copy.deepcopy(v.draft),
            "parameters": [{"name": "LOG_DISARMED", "value": 0, "type": 2}],
        }
        for vid, v in live.items()
    }
    return before, live


def edit(vid="one"):
    return {
        "vehicle_id": vid,
        "operations": [{"op": "add", "waypoint": {"lat": -35.36, "lon": 149.16, "alt": 30}}],
        "parameters": [{"name": "LOG_DISARMED", "value": 1, "reason": "Log while disarmed"}],
    }


def test_two_vehicles_prepare_without_mutating_live_drafts_or_parameters():
    before, live = setup_targets()
    reply, prepared = validate_edits(
        {"reply": "Staged", "vehicles": [edit(), edit("two")]}, before, live
    )
    assert len(prepared) == 2 and prepared[0]["draft"]["revision"] == 1
    assert prepared[0]["parameters"][0]["expected"] == 0
    assert all(
        v.draft["revision"] == 0 and v.params["LOG_DISARMED"]["value"] == 0 for v in live.values()
    )


@pytest.mark.parametrize("second", ["unselected", "one"])
def test_invalid_second_target_does_not_partially_edit_first(second):
    before, live = setup_targets()
    with pytest.raises(ValueError, match="unselected or repeated"):
        validate_edits({"reply": "Staged", "vehicles": [edit(), edit(second)]}, before, live)
    assert live["one"].draft["waypoints"] == []


@pytest.mark.parametrize("change", ["revision", "epoch", "closed", "deleted"])
def test_session_race_even_when_response_does_not_edit_that_target(change):
    before, live = setup_targets()
    if change == "revision":
        live["two"].draft["revision"] += 1
    if change == "epoch":
        live["two"].telemetry.epoch += 1
    if change == "closed":
        live["two"].closed = True
    if change == "deleted":
        del live["two"]
    with pytest.raises(ValueError, match="changed"):
        validate_edits({"reply": "Staged", "vehicles": [edit()]}, before, live)


@pytest.mark.parametrize(
    "name,value",
    [("SIM_GPS1_ENABLE", 0), ("UNKNOWN", 1), ("LOG_DISARMED", 0.5), ("LOG_DISARMED", 99)],
)
def test_parameter_proposals_reject_out_of_catalog_fraction_and_enum(name, value):
    before, live = setup_targets()
    e = edit()
    e["parameters"][0].update(name=name, value=value)
    with pytest.raises(ValueError):
        validate_edits({"reply": "Staged", "vehicles": [e]}, before, live)


def test_parameter_changed_during_inference():
    before, live = setup_targets()
    live["one"].params["LOG_DISARMED"]["value"] = 1
    with pytest.raises(ValueError, match="parameter changed"):
        validate_edits({"reply": "Staged", "vehicles": [edit()]}, before, live)


def test_rover_cannot_receive_takeoff_command():
    before, live = setup_targets()
    live["one"].profile = "rover"
    e = edit()
    e["operations"][0]["waypoint"]["command"] = 22
    with pytest.raises(ValueError, match="Unsupported mission command"):
        validate_edits({"reply": "Staged", "vehicles": [e]}, before, live)


def test_parameter_catalog_prioritizes_exact_names_excludes_simulator():
    context = parameter_context(
        "copter",
        {"LOG_DISARMED": {"value": 0, "type": 2}, "SIM_GPS1_ENABLE": {"value": 1, "type": 2}},
        "Set LOG_DISARMED=1 and SIM_GPS1_ENABLE=0",
    )
    assert [p["name"] for p in context] == ["LOG_DISARMED"]


def test_existing_install_gets_interaction_prompt_preserving_custom_prompts():
    old = Preferences().model_dump()
    del old["prompts"]["interaction"]
    old["prompts"]["planner"] += " Custom instruction retained."
    loaded = Preferences.model_validate(old)
    assert loaded.prompts.planner == old["prompts"]["planner"]
    assert "selected vehicles" in loaded.prompts.interaction
