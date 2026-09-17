import time
from unittest.mock import AsyncMock

import pytest

from backend.provider import AssessmentValidationError, Provider


def observation():
    return {"observed_at": time.time(), "samples": [{"evidence_id": "a:0:1"}], "extrema_10s": {}}


async def test_invalid_evidence_gets_one_bounded_repair():
    p = Provider()
    p.complete = AsyncMock(
        side_effect=[
            (
                {
                    "status": "concern",
                    "summary": "bad",
                    "incidents": [
                        {"severity": "warning", "summary": "x", "evidence": ["other:0:1"]}
                    ],
                },
                {},
            ),
            (
                {"status": "nominal", "summary": "No further concern", "incidents": []},
                {"latency_s": 1},
            ),
        ]
    )
    result = await p.monitor(observation())
    assert result["repair_attempted"] and p.complete.await_count == 2
    assert result["status"] == "nominal"
    assert p.complete.call_args.args[1]["observations"]["samples"] == [{"evidence_id": "a:0:1"}]


async def test_cross_vehicle_evidence_never_accepted():
    p = Provider()
    p.complete = AsyncMock(
        return_value=(
            {
                "status": "concern",
                "summary": "x",
                "incidents": [{"severity": "warning", "summary": "x", "evidence": ["other:0:1"]}],
            },
            {},
        )
    )
    with pytest.raises(AssessmentValidationError):
        await p.monitor(observation())
    assert p.complete.await_count == 2
