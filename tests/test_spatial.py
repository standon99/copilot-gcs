import base64
import copy
import io
import json
import time
from types import SimpleNamespace

import pytest
from PIL import Image
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import transform
from test_agent import call, vehicle, working

from backend.agent import run_turn
from backend.agent_tools import TurnConflict, WorkspaceTurn, tool_schemas
from backend.geography import MapAnnotation, MapImage
from backend.settings import Preferences
from backend.spatial import (
    FeatureInput,
    MetricFence,
    construct_metric_fence,
    empty_spatial,
    local_frame,
    measure_polygon,
    merge_features,
    parse_features,
    proposal_issues,
    record_feature,
    render_preview,
    vehicle_context,
)

ORIGIN = (149.16523, -35.363261)


def test_untrusted_map_metadata_is_bounded_and_finite():
    with pytest.raises(ValueError, match="contain_feature_ids"):
        MetricFence(kind="inclusion", width_m=1000, length_m=1000, reason="Missing requirements")
    for data in ([], {}, {"elements": "bad"}):
        with pytest.raises(ValueError):
            parse_features(data, ORIGIN)
    assert parse_features({"elements": [None, {"geometry": [None]}]}, ORIGIN) == []
    for changes in ({"coordinates": [float("nan"), 0]}, {"pixel": [0, float("inf")]}):
        with pytest.raises(ValueError):
            MapAnnotation.model_validate(
                dict(
                    kind="aircraft", label="test", coordinates=ORIGIN, pixel=[10, 10], in_view=True
                )
                | changes
            )
    state = empty_spatial()
    state["features"] = [{"id": f"trace:{i}", "source": "operator_trace"} for i in range(40)]
    state["selected_ids"] = ["trace:1", "gone"]
    merge_features(
        state,
        {
            "features": [{"id": f"osm:{i}", "source": "OpenStreetMap"} for i in range(35)],
            "status": "loaded",
        },
    )
    assert len(state["features"]) == 50
    assert state["selected_ids"] == ["trace:1"]


def test_rectangle_on_bent_road_preserves_size_and_stays_on_requested_side():
    with pytest.raises(ValueError, match="append or replace_index"):
        args(append=True, replace_index=0)
    ring, checks = construct_metric_fence(
        args(road_id="road", side="west", clearance_m=10), fixtures(curved=True), ORIGIN
    )
    assert all(abs(length - 1000) < 0.1 for length in checks["edge_lengths_m"])
    assert not checks["road"]["crosses_interior"]
    assert checks["road"]["minimum_distance_to_mapped_line_m"] >= 9.9
    assert proposal_issues({"spatial_checks": checks}) == []
    assert proposal_issues({"spatial_checks": {"all_requested_features_contained": False}})
    assert proposal_issues({"spatial_checks": {"road": {"crosses_interior": True}}})
    assert measure_polygon(ring)["all_requested_features_contained"] is None


def image():
    buffer = io.BytesIO()
    Image.new("RGB", (500, 500), "#557755").save(buffer, "PNG")
    return MapImage(
        vehicle_id="v",
        draft_revision=0,
        captured_at=time.time(),
        width=500,
        height=500,
        bounds=[149.15, -35.375, 149.18, -35.35],
        image="data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(),
    )


def feature(ident, geometry, kind="road", outline=False):
    _, unproject = local_frame(ORIGIN)
    return {
        "id": ident,
        "kind": kind,
        "label": ident,
        "geometry": mapping(transform(unproject, geometry)),
        "source": "fixture",
        "outline_known": outline,
        "uncertainty": "Measured test geometry",
    }


def fixtures(curved=False):
    road = LineString(
        [(100, -1500), (130, 0), (100, 1500)] if curved else [(100, -1500), (100, 1500)]
    )
    airstrip = Polygon([(-100, -150), (20, -150), (20, 150), (-100, 150)])
    return [feature("road", road), feature("airstrip", airstrip, "airstrip", True)]


def args(**changes):
    return MetricFence(
        **{
            "kind": "inclusion",
            "reason": "Explicit test request",
            "width_m": 1000,
            "length_m": 1000,
            "center": ORIGIN,
            "contain_feature_ids": [],
            **changes,
        }
    )


def test_metric_rectangle_dimensions_area_and_rotation():
    for bearing in (0, 37, 90):
        ring, measured = construct_metric_fence(args(bearing_deg=bearing), [], None)
        assert measured["edge_lengths_m"] == pytest.approx([1000] * 4, abs=0.02)
        assert measured["area_m2"] == pytest.approx(1_000_000, abs=1)
        assert Polygon(ring).is_valid


def test_road_side_clearance_airstrip_containment_and_infeasible_size():
    fs = fixtures()
    ring, measured = construct_metric_fence(
        args(road_id="road", side="west", clearance_m=10, contain_feature_ids=["airstrip"]),
        fs,
        None,
    )
    assert measured["all_requested_features_contained"]
    assert measured["fully_identified_outlines"]
    assert measured["road"]["minimum_distance_to_mapped_line_m"] == pytest.approx(10, abs=0.1)
    assert not measured["road"]["crosses_interior"]
    assert max(lon for lon, _ in ring) < ORIGIN[0] + 0.002
    _, too_small = construct_metric_fence(
        args(width_m=30, length_m=30, contain_feature_ids=["airstrip"]), fs, None
    )
    assert not too_small["all_requested_features_contained"]
    assert too_small["edge_lengths_m"] == pytest.approx([30] * 4, abs=0.01)


def test_curved_road_offset_is_a_polygon_and_not_mislabeled_square():
    _, measured = construct_metric_fence(
        args(shape="road_following", road_id="road", side="west", clearance_m=15),
        fixtures(True),
        None,
    )
    assert measured["vertices"] > 4
    assert measured["road_alignment"] == "follows mapped line offset"
    assert measured["road"]["minimum_distance_to_mapped_line_m"] == pytest.approx(15, abs=0.1)


def test_missing_type_clearance_invalid_road_and_short_segment():
    with pytest.raises(ValueError):
        MetricFence(width_m=1000, length_m=1000, reason="unspecified type")
    with pytest.raises(ValueError, match="clearance"):
        args(road_id="road", side="west")
    with pytest.raises(ValueError, match="Unknown feature"):
        construct_metric_fence(
            args(road_id="missing", side="west", clearance_m=0), fixtures(), None
        )
    with pytest.raises(ValueError, match="shorter"):
        construct_metric_fence(
            args(length_m=5000, road_id="road", side="west", clearance_m=0), fixtures(), None
        )
    with pytest.raises(ValueError, match="perpendicular"):
        construct_metric_fence(args(road_id="road", side="north", clearance_m=0), fixtures(), None)


def test_pixel_roundtrip_scale_and_explicit_image_availability():
    im = image()
    for pixel in ((0, 0), (250, 250), (500, 500)):
        assert im.pixel(im.geographic(pixel)) == pytest.approx(pixel, abs=1e-8)
    assert 2000 < im.context()["metric_scale"]["width_m"] < 3000
    v = vehicle()
    s = {
        "position_valid": True,
        "position": {"lon": ORIGIN[0], "lat": ORIGIN[1]},
        "home": {"lon": 149, "lat": -35},
        "coverage": {"GLOBAL_POSITION_INT": 0.2},
        "heading": 90,
    }
    v.telemetry.snapshot = lambda: s
    c = vehicle_context(v, im)
    assert c["image_available_this_turn"] and c["current_position"] != c["home"]
    assert not vehicle_context(v)["image_available_this_turn"]
    s["coverage"]["GLOBAL_POSITION_INT"] = 4
    assert vehicle_context(v)["current_position"] is None
    assert vehicle_context(v)["home"] is not None


def test_vector_parsing_marks_runway_line_as_unknown_outline():
    data = {
        "elements": [
            {
                "id": 1,
                "tags": {"aeroway": "runway"},
                "geometry": [{"lon": 149.165, "lat": -35.364}, {"lon": 149.165, "lat": -35.363}],
            }
        ]
    }
    f = parse_features(data, ORIGIN)[0]
    assert not f["outline_known"] and "width" in f["uncertainty"]
    ring, _ = construct_metric_fence(args(), [], None)
    checks = measure_polygon(ring, [f], [f["id"]])
    assert not checks["fully_identified_outlines"]


def test_feature_trace_pixel_scope_and_invalid_lines():
    data = FeatureInput(
        kind="road",
        label="Road",
        geometry_type="LineString",
        points=[(100, 100), (200, 200)],
        coordinate_space="map_pixels",
        uncertainty="Unverified visual trace",
    )
    with pytest.raises(ValueError, match="shared"):
        record_feature(data, "model_trace")
    f = record_feature(data, "model_trace", image())
    assert f["source"] == "model_trace" and not f["outline_known"]
    data.points = [(100, 100), (100, 100)]
    with pytest.raises(ValueError, match="distinct"):
        record_feature(data, "model_trace", image())


def test_rendered_preview_changes_pixels_keeps_dimensions_and_reports_clipping():
    im = image()
    ring, _ = construct_metric_fence(args(), [], None)
    data, info = render_preview(im, fixtures(), {"inclusions": [ring]})
    assert data != im.image and info["complete_view"]
    with Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) as raster:
        assert raster.size == (500, 500)
        assert raster.getpixel((250, 250)) != (85, 119, 85)
    ring, _ = construct_metric_fence(args(width_m=5000, length_m=5000), [], None)
    _, info = render_preview(im, [], {"inclusions": [ring]})
    assert not info["complete_view"] and info["offscreen_proposal_geometries"] == 1
    road, airstrip = fixtures()
    roads_only, _ = render_preview(im, [road] * 35, None)
    with_trace, _ = render_preview(im, [road] * 35 + [airstrip], None)
    assert roads_only != with_trace  # A trace after the 35 fetched candidates is still rendered.


def test_existing_preview_is_readable_and_followup_preserves_other_areas():
    v = vehicle()
    ring, _ = construct_metric_fence(args(), [], None)
    v.geofence_proposal = {
        "id": "prior",
        "base_revision": 0,
        "epoch": 0,
        "inclusions": [ring],
        "exclusions": [],
        "inclusion_mode": "intersection",
        "reason": "Earlier request",
    }
    v, p, turn = working(v)
    got = turn.execute("get_geofence_proposal", {"vehicle_id": "v"})
    assert got["proposal"]["inclusions"] == [ring]
    assert not turn.working["v"]["fence_dirty"]
    original = copy.deepcopy(v.geofence_proposal)
    with pytest.raises(ValueError, match="replace_index"):
        turn.execute("build_metric_geofence", {"vehicle_id": "v", **args(width_m=800).model_dump()})
    assert not turn.working["v"]["fence_dirty"]
    assert turn.working["v"]["fence"]["inclusions"] == [ring]
    turn.execute(
        "build_metric_geofence",
        {"vehicle_id": "v", **args(width_m=800, replace_index=0).model_dump(exclude_none=True)},
    )
    assert len(turn.working["v"]["fence"]["inclusions"]) == 1
    assert v.geofence_proposal == original
    turn.execute("build_metric_geofence", {"vehicle_id": "v", **args(append=True).model_dump()})
    assert len(turn.working["v"]["fence"]["inclusions"]) == 2
    v.geofence_proposal = None
    with pytest.raises(TurnConflict):
        turn.guard()


def test_spatial_revision_conflict_and_readonly_guards():
    v, p, turn = working()
    v.spatial = {**empty_spatial(), "revision": 1}
    with pytest.raises(TurnConflict):
        turn.guard()
    read = WorkspaceTurn({"v": v}, ["v"], p, read_only=True)
    with pytest.raises(ValueError, match="not available"):
        read.execute("update_spatial_brief", {"vehicle_id": "v", "width_m": 1000})
    names = {t["function"]["name"] for t in tool_schemas(True)}
    assert "get_spatial_context" in names and "build_metric_geofence" not in names


async def test_visual_feedback_reaches_next_model_call_without_raster_in_trace():
    v = vehicle()
    p = Preferences()
    turn = WorkspaceTurn({"v": v}, ["v"], p, image())
    replies = [
        call(
            "build_metric_geofence",
            {"vehicle_id": "v", **args().model_dump(exclude_none=True)},
            "build",
        ),
        {"content": "Premature answer"},
        call("render_spatial_preview", {"vehicle_id": "v"}, "render"),
        {"content": "Proposed a 1 km square; review the boundary."},
    ]

    async def respond(system, messages, tools, options):
        if len(replies) == 1:
            assert messages[-1]["role"] == "user"
            assert messages[-1]["content"][-1]["type"] == "image_url"
        return replies.pop(0), {}

    run = {"steps": []}
    reply, meta = await run_turn(
        SimpleNamespace(tool_turn=respond), turn, "system", {}, p.model_dump(), run, lambda: None
    )
    assert meta["rounds"] == 4 and "1 km" in reply
    assert "data:image" not in json.dumps(run)
    assert not turn.needs_visual_review()


def test_map_pixels_cannot_target_another_vehicle_image():
    v, p, turn = working()
    im = image()
    im.vehicle_id = "another"
    turn.map_image = im
    with pytest.raises(ValueError, match="vehicle whose map"):
        turn.execute(
            "propose_geofence",
            {
                "vehicle_id": "v",
                "kind": "inclusion",
                "reason": "test",
                "coordinate_space": "map_pixels",
                "polygons": [[(10, 10), (20, 10), (20, 20)]],
            },
        )
