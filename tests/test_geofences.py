import base64
import copy
import struct
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from test_interaction import setup_targets
from test_interaction_api import fake_vehicle
from test_protocol import gateway

from backend import main
from backend.ai_contract import capabilities
from backend.fence import decode_polygons, polygon_items
from backend.geography import ExclusionProposal, MapImage, validate_polygons
from backend.planning import Draft, check

RING = [(1, 1), (2, 1), (2, 2), (1, 2)]


def map_image(**changes):
    # Header is enough for the boundary validator: it never decodes raster data.
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 100, 100)
    return MapImage(
        **{
            "vehicle_id": "one",
            "draft_revision": 0,
            "captured_at": time.time(),
            "width": 100,
            "height": 100,
            "bounds": (1, 1, 2, 2),
            "image": "data:image/png;base64," + base64.b64encode(png).decode(),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "ring",
    [
        [(0, 0), (1, 1)],
        [(0, 0), (1, 1), (2, 2)],
        [(0, 0), (1, 1), (0, 1), (1, 0)],
        [(float("nan"), 0), (1, 1), (0, 1)],
        [(179, 0), (-179, 0), (-179, 1)],
        [(0, 0), (1, 0), (1, 0), (0, 1)],
    ],
)
def test_invalid_areas_rejected(ring):
    with pytest.raises(ValueError):
        validate_polygons([ring])


def test_closed_ring_normalized_and_quantized_degeneracy_rejected():
    assert validate_polygons([RING + [RING[0]]]) == [RING]
    with pytest.raises(ValueError):
        polygon_items([[(1, 1), (1.00000002, 1), (1, 1.000002)]])


def test_multiple_polygon_bank_roundtrip_and_limit():
    polygons = [RING, [(3, 3), (4, 3), (3, 4)]]
    items = polygon_items(polygons)
    assert [w["p1"] for w in items] == [4] * 4 + [3] * 3
    assert decode_polygons(items) == polygons
    with pytest.raises(ValueError, match="70"):
        polygon_items([RING] * 18)
    with pytest.raises(ValueError, match="unsupported"):
        decode_polygons([{**items[0], "command": 5001}])
    with pytest.raises(ValueError, match="Incomplete"):
        decode_polygons(items[:-1])


def test_route_checks_departure_rtl_home_and_touching_boundary():
    home = {"lat": 0, "lon": 0, "alt": 0}
    d = Draft(waypoints=[{"lat": 3, "lon": 3}], intent={"exclusions": [RING]}).model_dump()
    assert any(f["code"] == "excluded_leg" for f in check(d, "rover", home)["findings"])
    d["waypoints"] = [
        {"id": "a", "command": 16, "lat": 0, "lon": 3},
        {"id": "b", "command": 16, "lat": 3, "lon": 3},
        {"id": "return", "command": 20, "lat": 0, "lon": 0},
    ]
    findings = check(d, "rover", home)["findings"]
    assert any(f["code"] == "excluded_leg" and f["waypoint"] == "return" for f in findings)
    assert not check(d, "rover")["upload_allowed"]
    assert any(
        f["code"] == "excluded_home"
        for f in check(d, "rover", {"lat": 1.5, "lon": 1.5, "alt": 0})["findings"]
    )


def test_pixel_transform_and_missing_or_stale_image():
    image = map_image()
    assert image.geographic([0, 0]) == pytest.approx((1, 2))
    assert image.geographic([100, 100]) == pytest.approx((2, 1))
    proposal = ExclusionProposal(
        reason="test", coordinate_space="map_pixels", polygons=[[(10, 10), (90, 10), (10, 90)]]
    )
    assert len(proposal.resolve(image)["polygons"][0]) == 3
    with pytest.raises(ValueError, match="attached"):
        proposal.resolve()
    with pytest.raises(ValueError, match="outside"):
        image.geographic([101, 0])
    with pytest.raises(ValueError, match="expired"):
        map_image(captured_at=time.time() - 181)
    with pytest.raises(ValueError, match="dimensions"):
        map_image(width=101)
    with pytest.raises(ValueError, match="bounds"):
        map_image(bounds=(179, 1, -179, 2))


def test_ai_proposals_do_not_mutate_or_remove_existing_intent():
    from backend.interaction import validate_edits

    before, live = setup_targets()
    live["one"].draft["intent"]["exclusions"] = [RING]
    before["one"]["draft"] = copy.deepcopy(live["one"].draft)
    raw = {
        "reply": "Review the proposed removal",
        "vehicles": [
            {"vehicle_id": "one", "exclusion_proposal": {"reason": "requested", "polygons": []}}
        ],
    }
    _, prepared = validate_edits(raw, before, live)
    assert prepared[0]["draft"] is None
    assert prepared[0]["exclusion_proposal"]["polygons"] == []
    assert live["one"].draft["intent"]["exclusions"] == [RING]
    raw["vehicles"].append(
        {
            "vehicle_id": "two",
            "exclusion_proposal": {"reason": "invalid", "polygons": [[(0, 0), (1, 1)]]},
        }
    )
    with pytest.raises(ValueError):
        validate_edits(raw, before, live)
    assert live["one"].draft["intent"]["exclusions"] == [RING]


async def test_accept_proposal_requires_matching_revision_and_epoch(monkeypatch):
    v = fake_vehicle()
    v.exclusion_proposal = {"id": "p", "base_revision": 0, "epoch": 1, "polygons": [RING]}
    monkeypatch.setattr(main, "vehicles", {"v": v})
    monkeypatch.setattr(main, "event", Mock())
    save = Mock(side_effect=lambda v, d: setattr(v, "draft", d))
    monkeypatch.setattr(main, "save_draft", save)
    v.draft["revision"] = 1
    with pytest.raises(HTTPException):
        await main.accept_exclusions("v", "accept", {"proposal_id": "p"})
    v.draft["revision"] = 0
    v.exclusion_proposal["epoch"] = 0
    with pytest.raises(HTTPException):
        await main.accept_exclusions("v", "accept", {"proposal_id": "p"})
    save.assert_not_called()
    v.exclusion_proposal["epoch"] = 1
    await main.accept_exclusions("v", "accept", {"proposal_id": "p"})
    assert v.draft["intent"]["exclusions"] == [RING] and v.exclusion_proposal is None


def test_fence_protocol_type_isolation_and_first_vertex_readback():
    g = gateway()
    items = polygon_items([RING])
    pending = [
        SimpleNamespace(seq=n, mission_type=1, get_type=lambda: "MISSION_REQUEST_INT")
        for n in range(4)
    ]
    pending += [SimpleNamespace(type=0, mission_type=1, get_type=lambda: "MISSION_ACK")]

    def wait(types, predicate, timeout):
        assert not predicate(SimpleNamespace(mission_type=0))
        return pending.pop(0)

    g.wait = wait
    g.download_mission = Mock(return_value=items)
    result = g.upload(items, None, 1)
    assert result["status"] == "verified"
    assert all(c.args[-1] == 1 for c in g.link.mav.mission_item_int_send.call_args_list)
    g.download_mission.assert_called_once_with(1)
    # Vertex zero is not synthetic home; it must also verify.
    g = gateway()
    g.wait.side_effect = [
        *[
            SimpleNamespace(seq=n, mission_type=1, get_type=lambda: "MISSION_REQUEST_INT")
            for n in range(4)
        ],
        SimpleNamespace(type=0, mission_type=1, get_type=lambda: "MISSION_ACK"),
    ]
    g.download_mission = Mock(return_value=[{**items[0], "lat": 0}, *items[1:]])
    with pytest.raises(RuntimeError, match="readback mismatch"):
        g.upload(items, None, 1)


def fence_transaction():
    g = gateway()
    args = {
        "items": polygon_items([RING]),
        "expected_items": [],
        "expected": {"FENCE_ENABLE": 1, "FENCE_TYPE": 3, "FENCE_ACTION": 1},
        "action": 1,
    }
    g.download_mission = Mock(return_value=[])
    g.read_param = lambda name: {"value": args["expected"][name]}
    g.set_param = Mock()
    g.upload = Mock(return_value={"status": "verified", "items": args["items"]})
    return g, args


def test_fence_conflicts_no_writes_and_enable_only_after_verified_bank():
    g, args = fence_transaction()
    g.download_mission.return_value = polygon_items([RING])
    with pytest.raises(ValueError, match="changed"):
        g.synchronize_fence(args)
    g.set_param.assert_not_called()
    g.download_mission.return_value = []
    result = g.synchronize_fence(args)
    assert result["status"] == "verified"
    assert g.set_param.call_args_list[0].args == ("FENCE_ENABLE", 0, 1)
    assert g.set_param.call_args_list[-1].args == ("FENCE_ENABLE", 1, 0)
    assert g.set_param.call_args_list[1].args == ("FENCE_TYPE", 7, 3)


def test_fence_failed_readback_leaves_disabled_with_partial_journal():
    g, args = fence_transaction()
    g.upload.side_effect = RuntimeError("bad readback")
    result = g.synchronize_fence(args)
    assert result["status"] == "failed" and "bad readback" in result["error"]
    assert result["applied"] == ["FENCE_ENABLE=0"]
    g.set_param.assert_called_once_with("FENCE_ENABLE", 0, 1)


def test_contract_schema_tracks_live_response_and_has_no_vehicle_write_tool():
    manifest = capabilities()
    fields = manifest["response_schema"]["$defs"]["VehicleEdits"]["properties"]
    assert "exclusion_proposal" in fields and "watch_rules" in fields
    assert "upload mission" in manifest["operator_only"]
    assert not any(op["name"] in ("arm", "upload", "shell") for op in manifest["operations"])
