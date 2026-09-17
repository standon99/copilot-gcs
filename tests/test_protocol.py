import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.gateway import Gateway


def gateway():
    g = Gateway.__new__(Gateway)
    g.sys = 1
    g.comp = 1
    g.epoch = 0
    g.profile = "copter"
    g.link = SimpleNamespace(mav=Mock())
    g.wait = Mock()
    g.heartbeat = time.time()
    g.latest = {"HEARTBEAT": {"data": {"base_mode": 0, "mode": "GUIDED"}}}
    return g


def test_param_conflict_sends_nothing():
    g = gateway()
    g.read_param = Mock(return_value={"value": 2, "type": 9})
    with pytest.raises(ValueError, match="changed externally"):
        g.set_param("TEST", 3, expected=1)
    g.link.mav.param_set_send.assert_not_called()


def test_readback_not_echo_is_authoritative():
    g = gateway()
    g.read_param = Mock(side_effect=[{"value": 1, "type": 9}, {"value": 1, "type": 9}])
    with pytest.raises(RuntimeError, match="readback mismatch"):
        g.set_param("TEST", 2, expected=1)
    assert g.read_param.call_count == 2


def test_integer_type_cannot_truncate_fraction():
    g = gateway()
    g.read_param = Mock(return_value={"value": 1, "type": 6})
    with pytest.raises(ValueError, match="fraction"):
        g.set_param("TEST", 1.5)
    g.link.mav.param_set_send.assert_not_called()


def test_expired_queue_entry_sends_nothing():
    g = gateway()
    with pytest.raises(RuntimeError, match="expired"):
        g.operation({"action": "arm", "args": {"armed": True}, "expires_at": time.time() - 1})
    g.link.mav.command_long_send.assert_not_called()


def test_reboot_invalidates_commands():
    g = gateway()
    g.epoch = 2
    with pytest.raises(RuntimeError, match="epoch"):
        g.operation(
            {"action": "arm", "args": {"armed": True}, "epoch": 1, "expires_at": time.time() + 10}
        )


def test_armed_parameter_write_rejected_at_execution():
    g = gateway()
    g.latest["HEARTBEAT"]["data"]["base_mode"] = 128
    with pytest.raises(RuntimeError, match="Disarm"):
        g.operation(
            {"action": "parameter_write", "args": {}, "epoch": 0, "expires_at": time.time() + 10}
        )


def test_arm_requires_state_after_ack():
    g = gateway()
    g.wait.side_effect = [SimpleNamespace(result=0), TimeoutError("No matching armed heartbeat")]
    with pytest.raises(TimeoutError):
        g.send_command(400, [1], lambda m: bool(m.base_mode & 128))
    assert g.wait.call_args_list[1].args[0] == "HEARTBEAT"


def test_command_progress_then_final_ack():
    g = gateway()
    g.wait.side_effect = [SimpleNamespace(result=5), SimpleNamespace(result=0)]
    assert g.send_command(22, [0] * 7)["status"] == "accepted"


def test_command_rejection_is_not_success():
    g = gateway()
    g.wait.return_value = SimpleNamespace(result=2)
    with pytest.raises(RuntimeError, match="rejected"):
        g.send_command(400, [1])


def timed_hold_roundtrip(changes=None, requested=None):
    g = gateway()
    point = {
        "command": 19,
        "frame": 3,
        "lat": -35.3628,
        "lon": 149.16553,
        "alt": 30,
        "p1": 30,
        "p2": 0,
        "p3": 0,
        "p4": 0,
        **(requested or {}),
    }
    returned = {**point, "p3": 1, **(changes or {})}
    messages = [
        SimpleNamespace(seq=0, get_type=lambda: "MISSION_REQUEST_INT"),
        SimpleNamespace(seq=1, get_type=lambda: "MISSION_REQUEST_INT"),
        SimpleNamespace(type=0, get_type=lambda: "MISSION_ACK"),
    ]
    g.wait.side_effect = messages
    g.download_mission = Mock(return_value=[{}, returned])
    return g, point


def test_timed_hold_default_direction_verifies_pinned_ardupilot_readback():
    g, point = timed_hold_roundtrip()
    result = g.upload([point], {"lat": -35.363261, "lon": 149.16523, "alt": 584.09})
    assert result["status"] == "verified"
    assert result["items"][1]["p1"] == 30
    assert result["items"][1]["p3"] == 1
    assert g.link.mav.mission_item_int_send.call_args.args[9] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"p1": 10},
        {"lat": -35.3638},
        {"lon": 149.16653},
        {"alt": 20},
        {"p3": -1},
        {"p3": 2},
        {"frame": 0},
        {"command": 17},
    ],
)
def test_timed_hold_readback_still_rejects_changed_mission_fields(changes):
    g, point = timed_hold_roundtrip(changes)
    with pytest.raises(RuntimeError, match="mismatch"):
        g.upload([point], {"lat": -35.363261, "lon": 149.16523, "alt": 584.09})


@pytest.mark.parametrize("requested", [{"command": 17}, {"p3": 25}])
def test_direction_normalization_is_limited_to_default_timed_hold(requested):
    g, point = timed_hold_roundtrip(requested=requested)
    with pytest.raises(RuntimeError, match="p3 readback mismatch"):
        g.upload([point], {"lat": -35.363261, "lon": 149.16523, "alt": 584.09})


def test_log_download_repairs_missing_chunk_and_publishes_atomically(tmp_path):
    g = gateway()
    g.folder = tmp_path
    pending = []
    calls = []

    def request_data(system, component, logid, start, count):
        calls.append((start, count))
        positions = list(range(start, start + count, 90))
        for offset in reversed(positions):
            if len(calls) == 1 and offset == 90:
                continue
            n = min(90, 200 - offset)
            pending.append(SimpleNamespace(id=1, ofs=offset, count=n, data=[offset // 90] * n))

    def wait_data(typ, predicate, timeout):
        if typ == "LOG_ENTRY":
            return SimpleNamespace(id=1, num_logs=1, size=200)
        if not pending:
            raise TimeoutError("simulated dropped packet")
        message = pending.pop(0)
        assert predicate(message)
        return message

    g.link.mav.log_request_data_send.side_effect = request_data
    g.wait = wait_data
    result = g.operation(
        {
            "action": "log_download",
            "args": {"id": 1, "size": 200},
            "epoch": 0,
            "expires_at": time.time() + 20,
        }
    )
    assert result["status"] == "verified"
    assert calls == [(0, 200), (90, 90)]
    assert (tmp_path / "dataflash-1.bin").read_bytes() == bytes([0] * 90 + [1] * 90 + [2] * 20)
    assert not (tmp_path / "dataflash-1.partial").exists()
