"""Endpoint guards and truthful partial-write results without running simulators."""

import copy
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend import main
from backend.planning import Draft


def fake_vehicle():
    return SimpleNamespace(
        id="v",
        closed=False,
        profile="copter",
        params={"LOG_DISARMED": {"value": 0, "type": 2}},
        telemetry=SimpleNamespace(epoch=1, snapshot=lambda: {"armed": False, "home": None}),
        parameter_proposals=[
            {
                "id": "p",
                "epoch": 1,
                "expires_at": time.time() + 300,
                "status": "pending",
                "results": [],
                "parameters": [{"name": "LOG_DISARMED", "expected": 0, "value": 1}],
            }
        ],
        parameter_apply_busy=False,
        fence_busy=False,
        trial_task=None,
        draft=Draft().model_dump(),
        review=None,
        active=None,
        chat=[],
        intent_proposal=None,
    )


@pytest.fixture
def v(monkeypatch):
    v = fake_vehicle()
    monkeypatch.setattr(main, "vehicles", {"v": v})
    monkeypatch.setattr(main, "authorize", lambda *args: None)
    monkeypatch.setattr(main, "event", lambda *args: None)
    return v


@pytest.mark.parametrize(
    "reason", ["stale_epoch", "expired", "changed", "armed", "busy", "attempted"]
)
async def test_apply_preconditions_send_no_vehicle_writes(v, monkeypatch, reason):
    p = v.parameter_proposals[0]
    if reason == "stale_epoch":
        p["epoch"] = 0
    if reason == "expired":
        p["expires_at"] = 0
    if reason == "changed":
        v.params["LOG_DISARMED"]["value"] = 1
    if reason == "armed":
        v.telemetry.snapshot = lambda: {"armed": True}
    if reason == "busy":
        v.fence_busy = True
    if reason == "attempted":
        p["status"] = "failed"

    def no_submit(*args):
        raise AssertionError("Must not write")

    monkeypatch.setattr(main, "submit", no_submit)
    with pytest.raises(HTTPException) as exc:
        await main.apply_parameters("v", "p", None)
    assert exc.value.status_code == 409


async def test_success_idempotent_and_partial_failure_is_not_claimed_verified(v, monkeypatch):
    sent = []

    def submit(*args):
        sent.append(args)
        return {"id": str(len(sent)), "status": "verified"}

    monkeypatch.setattr(main, "submit", submit)
    monkeypatch.setattr(main, "await_job", AsyncMock())
    result = await main.apply_parameters("v", "p", None)
    assert result["parameter_proposals"][0]["status"] == "verified" and len(sent) == 1
    await main.apply_parameters("v", "p", None)
    assert len(sent) == 1
    p = v.parameter_proposals[0]
    p.update(status="pending", results=[])
    p["parameters"].append(copy.deepcopy(p["parameters"][0]))
    monkeypatch.setattr(
        main, "await_job", AsyncMock(side_effect=[None, RuntimeError("Readback mismatch")])
    )
    result = await main.apply_parameters("v", "p", None)
    p = result["parameter_proposals"][0]
    assert p["status"] == "failed" and "Earlier verified writes remain applied" in p["error"]
    assert len(p["results"]) == 2 and not v.parameter_apply_busy


async def test_interaction_off_and_cross_vehicle_proposal_rejected(v):
    with pytest.raises(HTTPException) as exc:
        await main.interaction(main.Interaction(message="change", targets=["v"], enabled=False))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        await main.apply_parameters("v", "other-vehicle-proposal", None)
    assert exc.value.status_code == 404
