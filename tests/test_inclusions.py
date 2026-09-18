from unittest.mock import Mock

import pytest
from test_agent import vehicle

from backend.agent_tools import WorkspaceTurn
from backend.fence import decode_fences, polygon_items
from backend.gateway import Gateway
from backend.planning import Draft, Intent, Waypoint, check
from backend.settings import Preferences

OUTER = [(148.99, -35.01), (149.01, -35.01), (149.01, -34.99), (148.99, -34.99)]
HOME = {"lat": -35, "lon": 149, "alt": 600}


def codes(intent, points):
    draft = Draft(
        intent=Intent(**intent),
        waypoints=[Waypoint(lat=lat, lon=lon, alt=20) for lon, lat in points],
    )
    return {f["code"] for f in check(draft.model_dump(), "rover", HOME)["findings"]}


def test_inclusion_home_points_departure_and_return_validation():
    assert not any(
        c.startswith("outside_inclusion")
        for c in codes({"inclusions": [OUTER]}, [(149, -35), (149.001, -35)])
    )
    assert "outside_inclusion_point" in codes({"inclusions": [OUTER]}, [(149.02, -35)])
    assert "outside_inclusion_point" in codes({"inclusions": [OUTER]}, [(149.01, -35)])
    disjoint = [(149.02, -35.01), (149.04, -35.01), (149.04, -34.99), (149.02, -34.99)]
    assert "outside_inclusion_home" in codes({"inclusions": [disjoint]}, [(149.03, -35)])
    assert "empty_inclusion" in codes({"inclusions": [OUTER, disjoint]}, [(149, -35)])
    assert "outside_inclusion_leg" in codes(
        {"inclusions": [OUTER, disjoint], "inclusion_mode": "union"}, [(149.03, -35)]
    )


def test_concave_polygon_rejects_leg_that_leaves_between_included_endpoints():
    concave = [
        (148.99, -35.01),
        (149.01, -35.01),
        (149.01, -34.99),
        (149.005, -34.99),
        (149.005, -35.005),
        (148.995, -35.005),
        (148.995, -34.99),
        (148.99, -34.99),
    ]
    result = codes({"inclusions": [concave]}, [(148.992, -35), (149.008, -35)])
    assert "outside_inclusion_leg" in result


def test_mixed_native_bank_roundtrips_types_and_rejects_circles():
    exclusion = [(149.002, -35.002), (149.004, -35.002), (149.004, -35), (149.002, -35)]
    items = polygon_items([exclusion], [OUTER])
    bank = decode_fences(items)
    assert bank == {"exclusions": [exclusion], "inclusions": [OUTER]}
    assert items[0]["command"] == 5001 and items[4]["command"] == 5002
    with pytest.raises(ValueError):
        decode_fences([{**items[0], "command": 5003}])
    with pytest.raises(ValueError):
        decode_fences([{**items[0], "p1": 3.5}])
    with pytest.raises(ValueError):
        polygon_items([OUTER] * 10, [OUTER] * 10)


@pytest.mark.parametrize("mode,want", [("union", 3), ("intersection", 1)])
def test_native_fence_sets_only_inclusion_option_bit_before_enable(mode, want):
    g = Gateway.__new__(Gateway)
    import time

    g.epoch = 0
    g.heartbeat = time.time()
    g.latest = {"HEARTBEAT": {"data": {"base_mode": 0}}}
    g.download_mission = Mock(return_value=[])
    expected = {"FENCE_ENABLE": 1, "FENCE_TYPE": 3, "FENCE_ACTION": 1, "FENCE_OPTIONS": 1}
    g.read_param = Mock(side_effect=lambda name: {"value": expected[name]})
    g.set_param = Mock()
    g.upload = Mock(return_value={"status": "verified", "items": []})
    result = g.synchronize_fence(
        {
            "expected_items": [],
            "items": polygon_items([], [OUTER]),
            "expected": expected,
            "action": 1,
            "inclusion_mode": mode,
        }
    )
    assert result["status"] == "verified"
    assert any(c.args == ("FENCE_OPTIONS", want, 1) for c in g.set_param.call_args_list)
    assert g.set_param.call_args_list[-1].args == ("FENCE_ENABLE", 1, 0)


def test_model_can_propose_both_types_without_relaxing_draft():
    v = vehicle()
    t = WorkspaceTurn({"v": v}, ["v"], Preferences())
    for kind in ("inclusion", "exclusion"):
        result = t.execute(
            "propose_geofence",
            {
                "vehicle_id": "v",
                "kind": kind,
                "reason": "Requested",
                "polygons": [OUTER],
            },
        )
        assert "findings" in result["checks"]
    preview = t.working["v"]["fence"]
    assert preview["inclusions"] == preview["exclusions"] == [OUTER]
    assert not v.draft["intent"]["inclusions"] and not v.draft["intent"]["exclusions"]
