"""One process, reader and serialized command writer per MAVLink connection.

No provider calls or browser dependencies run here. Even long transfers pump
telemetry and GCS heartbeats. Every command is bound to the current boot epoch.
"""

import hashlib
import math
import os
import queue
import signal
import struct
import time
from pathlib import Path

os.environ["MAVLINK20"] = "1"
from pymavlink import mavutil


class Gateway:
    def __init__(self, endpoint, profile, events, commands, results, folder):
        self.events, self.commands, self.results = events, commands, results
        self.profile = profile
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.log = (self.folder / "telemetry.tlog").open("ab")
        self.link = mavutil.mavlink_connection(
            endpoint,
            source_system=255,
            source_component=190,
            dialect="ardupilotmega",
            autoreconnect=False,
        )

        def disconnected():
            raise ConnectionError(
                "MAVLink TCP connection closed; pending commands will not be replayed"
            )

        if endpoint.startswith("tcp:"):
            self.link.handle_eof = disconnected
            self.link.handle_disconnect = disconnected
        self.sys = 0
        self.comp = 0
        self.epoch = 0
        self.boot = None
        self.heartbeat = 0
        self.last_send = 0
        self.params = {}
        self.latest = {}
        self.seq = 0
        self.dropped = 0
        self.configured = False

    def emit(self, value):
        try:
            self.events.put_nowait(value)
        except queue.Full:
            self.dropped += 1

    def pump(self):
        now = time.time()
        if now - self.last_send >= 1:
            self.link.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0
            )
            self.last_send = now
        m = self.link.recv_match(blocking=True, timeout=0.025)
        if not m or m.get_type() == "BAD_DATA":
            return None
        typ = m.get_type()
        if self.log and self.log.tell() < 256 * 1024 * 1024:
            try:
                self.log.write(struct.pack(">Q", int(now * 1e6)) + m.get_msgbuf())
            except OSError:
                self.log.close()
                self.log = None
                self.emit(
                    {
                        "kind": "recording_error",
                        "error": "Raw telemetry recording failed; live telemetry continues",
                    }
                )
        elif self.log:
            self.log.close()
            self.log = None
            self.emit(
                {
                    "kind": "recording_error",
                    "error": "Raw telemetry recording reached 256 MiB quota",
                }
            )
        if typ == "HEARTBEAT" and m.autopilot == 3:
            if self.sys and (m.get_srcSystem(), m.get_srcComponent()) != (self.sys, self.comp):
                self.emit(
                    {"kind": "error", "error": "Multiple autopilots on this link; writes disabled"}
                )
                self.sys = 0
                return None
            self.sys = m.get_srcSystem()
            self.comp = m.get_srcComponent()
            self.heartbeat = now
        if not self.sys or m.get_srcSystem() != self.sys or m.get_srcComponent() != self.comp:
            return None
        data = m.to_dict()
        if typ == "GLOBAL_POSITION_INT":
            boot = data.get("time_boot_ms", 0)
            if self.boot is not None and boot + 2000 < self.boot:
                self.epoch += 1
                self.params = {}
                self.configured = False
                self.emit({"kind": "reboot", "epoch": self.epoch})
            self.boot = boot
        if typ == "PARAM_VALUE":
            name = (
                m.param_id.decode(errors="replace") if isinstance(m.param_id, bytes) else m.param_id
            )
            self.params[name] = {
                "name": name,
                "value": m.param_value,
                "type": m.param_type,
                "index": m.param_index,
                "count": m.param_count,
            }
            data = self.params[name]
        if typ == "HEARTBEAT":
            data["mode"] = mavutil.mode_string_v10(m)
        self.seq += 1
        event = {
            "kind": "message",
            "type": typ,
            "data": data,
            "ts": now,
            "epoch": self.epoch,
            "seq": self.seq,
            "sysid": self.sys,
            "component": self.comp,
            "dropped": self.dropped,
        }
        self.latest[typ] = event
        self.emit(event)
        return m

    def wait(self, typ, predicate=lambda m: True, timeout=5):
        deadline = time.monotonic() + timeout
        epoch = self.epoch
        types = (typ,) if isinstance(typ, str) else typ
        while time.monotonic() < deadline:
            m = self.pump()
            if self.epoch != epoch:
                raise RuntimeError("Vehicle rebooted during operation; completion unknown")
            if m and m.get_type() in types and predicate(m):
                return m
        raise TimeoutError(f"Timed out waiting for {typ}; completion may be unknown")

    def send_command(self, command, params, verify=None, timeout=8):
        sent_at = time.time()
        self.link.mav.command_long_send(self.sys, self.comp, command, 0, *(params + [0] * 7)[:7])
        ack = self.wait("COMMAND_ACK", lambda m: m.command == command, timeout)
        while ack.result == 5:
            ack = self.wait("COMMAND_ACK", lambda m: m.command == command, timeout)
        if ack.result != 0:
            recent = self.latest.get("STATUSTEXT", {})
            detail = (
                recent.get("data", {}).get("text", "") if recent.get("ts", 0) >= sent_at else ""
            )
            raise RuntimeError(f"Command rejected with MAV_RESULT={ack.result}. {detail}")
        if verify:
            self.wait("HEARTBEAT", verify, timeout)
        return {"status": "verified" if verify else "accepted", "command": command}

    def read_param(self, name):
        self.link.mav.param_request_read_send(self.sys, self.comp, name.encode(), -1)
        self.wait("PARAM_VALUE", lambda m: m.param_id == name or m.param_id == name.encode())
        return self.params[name]

    def set_param(self, name, value, expected=None):
        old = self.read_param(name).copy()
        if expected is not None and not math.isclose(
            old["value"], expected, rel_tol=1e-6, abs_tol=1e-5
        ):
            raise ValueError(f"{name} changed externally; refresh before writing")
        if not math.isfinite(value):
            raise ValueError("Parameter must be finite")
        if old["type"] != 9 and value != int(value):
            raise ValueError("Integer parameter cannot contain a fraction")
        self.link.mav.param_set_send(self.sys, self.comp, name.encode(), value, old["type"])
        self.wait("PARAM_VALUE", lambda m: m.param_id == name or m.param_id == name.encode())
        observed = self.read_param(name).copy()
        if not math.isclose(observed["value"], value, rel_tol=1e-5, abs_tol=1e-5):
            raise RuntimeError(f"{name} readback mismatch: {observed['value']}")
        return {
            "status": "verified",
            "name": name,
            "old": old["value"],
            "requested": value,
            "observed": observed["value"],
        }

    def download_mission(self, mission_type=0):
        self.link.mav.mission_request_list_send(self.sys, self.comp, mission_type)
        count = self.wait(
            "MISSION_COUNT", lambda m: getattr(m, "mission_type", 0) == mission_type
        ).count
        if count > 501:
            raise ValueError("Mission exceeds supported item count")
        items = []
        for seq in range(count):
            for attempt in range(3):
                self.link.mav.mission_request_int_send(self.sys, self.comp, seq, mission_type)
                try:
                    m = self.wait(
                        "MISSION_ITEM_INT",
                        lambda m, seq=seq: (
                            m.seq == seq and getattr(m, "mission_type", 0) == mission_type
                        ),
                        2,
                    )
                    break
                except TimeoutError:
                    if attempt == 2:
                        raise
            items.append(
                {
                    "seq": seq,
                    "command": m.command,
                    "frame": m.frame,
                    "lat": m.x / 1e7,
                    "lon": m.y / 1e7,
                    "alt": m.z,
                    "p1": m.param1,
                    "p2": m.param2,
                    "p3": m.param3,
                    "p4": m.param4,
                }
            )
        self.link.mav.mission_ack_send(self.sys, self.comp, 0, mission_type)
        return items

    def upload(self, waypoints, home, mission_type=0):
        items = [
            {
                "command": 16,
                "frame": 0,
                "lat": (home or {}).get("lat", 0),
                "lon": (home or {}).get("lon", 0),
                "alt": (home or {}).get("alt", 0),
                "p1": 0,
                "p2": 0,
                "p3": 0,
                "p4": 0,
            },
            *waypoints,
        ]
        if mission_type == 1:
            items = waypoints
        self.link.mav.mission_count_send(self.sys, self.comp, len(items), mission_type)
        deadline = time.monotonic() + 30
        sent = set()
        while time.monotonic() < deadline:
            m = self.wait(
                ("MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"),
                lambda m: getattr(m, "mission_type", 0) == mission_type,
                timeout=8,
            )
            if m.get_type() == "MISSION_ACK":
                if m.type != 0:
                    raise RuntimeError(f"Mission rejected: MAV_MISSION_RESULT={m.type}")
                if len(sent) != len(items):
                    raise RuntimeError("Premature mission acknowledgement")
                break
            if not 0 <= m.seq < len(items):
                raise RuntimeError("Invalid mission item request")
            w = items[m.seq]
            # Even deprecated MISSION_REQUEST must receive MISSION_ITEM_INT.
            self.link.mav.mission_item_int_send(
                self.sys,
                self.comp,
                m.seq,
                w["frame"],
                w["command"],
                int(mission_type == 0 and m.seq == 0),
                1,
                w["p1"],
                w["p2"],
                w["p3"],
                w["p4"],
                round(w["lat"] * 1e7),
                round(w["lon"] * 1e7),
                w["alt"],
                mission_type,
            )
            sent.add(m.seq)
        else:
            raise TimeoutError("Mission upload deadline expired; completion unknown")
        received = self.download_mission(mission_type) if mission_type else self.download_mission()
        if len(received) != len(items):
            raise RuntimeError("Mission readback count mismatch")
        for i, (want, got) in enumerate(zip(items, received)):
            if i == 0 and mission_type == 0:
                continue  # ArduPilot owns/normalizes the synthetic home item.
            if want["command"] != got["command"] or (
                want["command"] not in (20, 178) and want["frame"] != got["frame"]
            ):
                raise RuntimeError(f"Mission item {i}: command/frame mismatch")
            for k in ("lat", "lon", "alt", "p1", "p2", "p3", "p4"):
                # Non-location commands may normalize unused coordinates.
                if k in ("lat", "lon", "alt") and want["command"] in (20, 178):
                    continue
                expected = want[k]
                # Pinned AP_Mission stores LOITER_TIME direction, not radius,
                # and returns +1 for the default (zero) clockwise value.
                # Accept only that default encoding; explicit radii, duration,
                # location, altitude and direction still require matching readback.
                if want["command"] == 19 and k == "p3" and expected == 0:
                    expected = 1
                # AP_Mission NAV_LAND stores deepstall yaw direction as a sign
                # bit and returns +1 for default zero (also on Copter).
                if want["command"] == 21 and k == "p4" and expected == 0:
                    expected = 1
                if not math.isclose(
                    expected, got[k], rel_tol=0, abs_tol=2e-7 if k in ("lat", "lon") else 0.01
                ):
                    raise RuntimeError(f"Mission item {i}: {k} readback mismatch")
        return {"status": "verified", "items": received}

    def synchronize_fence(self, args):
        from .fence import decode_polygons

        epoch = self.epoch
        applied = []

        def guard():
            if self.epoch != epoch or time.time() - self.heartbeat > 3:
                raise RuntimeError("Vehicle epoch/freshness changed during fence update")
            if self.latest["HEARTBEAT"]["data"]["base_mode"] & 128:
                raise RuntimeError("Vehicle armed during fence update")

        existing = self.download_mission(1)
        if existing != args["expected_items"]:
            raise ValueError("Onboard fence changed externally; reload before uploading")
        decode_polygons(existing)  # Do not erase unknown inclusion/circle/return items.
        decode_polygons(args["items"])
        expected = args["expected"]
        for name, value in expected.items():
            if not math.isclose(self.read_param(name)["value"], value, rel_tol=0, abs_tol=1e-5):
                raise ValueError(f"{name} changed externally; reload before uploading")
        try:
            guard()
            self.set_param("FENCE_ENABLE", 0, expected["FENCE_ENABLE"])
            applied.append("FENCE_ENABLE=0")
            guard()
            result = self.upload(args["items"], None, 1)
            applied.append("polygon bank verified")
            types = int(expected["FENCE_TYPE"])
            types = (types | 4) if args["items"] else (types & ~4)
            changes = {"FENCE_TYPE": types, "FENCE_ACTION": args["action"]}
            if "FENCE_AUTOENABLE" in expected:
                changes["FENCE_AUTOENABLE"] = 0
            changes["FENCE_ENABLE"] = int(
                bool(types) and (bool(args["items"]) or bool(expected["FENCE_ENABLE"]))
            )
            for name, value in changes.items():
                guard()
                self.set_param(name, value, 0 if name == "FENCE_ENABLE" else expected[name])
                applied.append(f"{name}={value}")
            return {**result, "applied": applied}
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"Fence update incomplete: {exc}. Reload before retrying; inspect enable state.",
                "applied": applied,
            }

    def operation(self, request):
        action = request["action"]
        args = request.get("args", {})
        if time.time() > request.get("expires_at", 0):
            raise RuntimeError("Queued request expired before execution; nothing sent")
        if time.time() - self.heartbeat > 3:
            raise RuntimeError("Vehicle heartbeat stale")
        if request.get("epoch", self.epoch) != self.epoch:
            raise RuntimeError("Vehicle boot epoch changed")
        armed = bool(self.latest["HEARTBEAT"]["data"]["base_mode"] & 128)
        if (
            action in ("parameter_write", "mission_upload", "fence_upload", "log_download")
            and armed
        ):
            raise RuntimeError("Disarm before this operation")
        if action == "fence_download":
            return {"status": "verified", "items": self.download_mission(1)}
        if action == "fence_upload":
            return self.synchronize_fence(args)
        if action == "parameters":
            self.link.mav.param_request_list_send(self.sys, self.comp)
            until = time.monotonic() + 25
            while time.monotonic() < until:
                self.pump()
                count = max((p["count"] for p in self.params.values()), default=0)
                indices = {p["index"] for p in self.params.values()}
                if count and len(indices) >= count:
                    break
            count = max((p["count"] for p in self.params.values()), default=0)
            for idx in set(range(count)) - {p["index"] for p in self.params.values()}:
                self.link.mav.param_request_read_send(self.sys, self.comp, b"", idx)
                try:
                    self.wait("PARAM_VALUE", lambda m, idx=idx: m.param_index == idx, 1)
                except TimeoutError:
                    pass
            return {
                "status": "verified" if count and len(self.params) >= count else "partial",
                "received": len(self.params),
                "expected": count,
            }
        if action in ("parameter_write", "inject"):
            return self.set_param(args["name"], float(args["value"]), args.get("expected"))
        if action == "arm":
            return self.send_command(
                400, [1 if args["armed"] else 0], lambda m: bool(m.base_mode & 128) == args["armed"]
            )
        if action == "mode":
            mode = args["mode"]
            mapping = self.link.mode_mapping()
            if mode not in mapping:
                raise ValueError("Unsupported mode")
            self.link.mav.set_mode_send(self.sys, 1, mapping[mode])
            self.wait("HEARTBEAT", lambda m: m.custom_mode == mapping[mode], 8)
            return {"status": "verified", "mode": mode}
        if action == "takeoff":
            if (
                self.profile != "copter"
                or not armed
                or self.latest["HEARTBEAT"]["data"].get("mode") != "GUIDED"
            ):
                raise RuntimeError("Takeoff preconditions changed while queued")
            return self.send_command(22, [0, 0, 0, 0, 0, 0, args["alt"]], timeout=10)
        if action == "start":
            if not armed:
                raise RuntimeError("Vehicle disarmed while start was queued")
            return self.send_command(300, [0, 0], lambda m: mavutil.mode_string_v10(m) == "AUTO")
        if action == "mission_download":
            return {"status": "verified", "items": self.download_mission()}
        if action == "mission_upload":
            return self.upload(args["waypoints"], args["home"])
        if action == "log_list":
            self.link.mav.log_request_list_send(self.sys, self.comp, 0, 65535)
            entries = {}
            expected = None
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                m = self.pump()
                if m and m.get_type() == "LOG_ENTRY":
                    expected = m.num_logs
                    if m.num_logs == 0:
                        break
                    entries[m.id] = m.to_dict()
                    if len(entries) >= m.num_logs:
                        break
            if expected is None:
                raise TimeoutError("No LOG_ENTRY response received")
            return {
                "status": "verified" if len(entries) == expected else "partial",
                "logs": list(entries.values()),
                "expected": expected,
            }
        if action == "log_download":
            logid = int(args["id"])
            self.link.mav.log_request_list_send(self.sys, self.comp, logid, logid)
            entry = self.wait("LOG_ENTRY", lambda m: m.id == logid and m.num_logs > 0, 5)
            size = int(entry.size)
            if not 0 < size <= 128 * 1024 * 1024:
                raise ValueError("Log size outside 1..128 MiB")
            path = self.folder / f"dataflash-{logid}.bin"
            partial = path.with_suffix(".partial")
            digest = hashlib.sha256()
            try:
                with partial.open("wb") as out:
                    for offset in range(0, size, 90 * 128):
                        if self.latest["HEARTBEAT"]["data"]["base_mode"] & 128:
                            raise RuntimeError(
                                "Vehicle armed during log transfer; download aborted"
                            )
                        end = min(size, offset + 90 * 128)
                        expected = set(range(offset, end, 90))
                        chunks = {}
                        for _attempt in range(4):
                            missing = sorted(expected - chunks.keys())
                            if not missing:
                                break
                            # A contiguous window streams efficiently. Retry missing spans.
                            spans = []
                            for position in missing:
                                if spans and position == spans[-1][1]:
                                    spans[-1][1] = min(end, position + 90)
                                else:
                                    spans.append([position, min(end, position + 90)])
                            for start, stop in spans:
                                self.link.mav.log_request_data_send(
                                    self.sys, self.comp, logid, start, stop - start
                                )
                                deadline = time.monotonic() + 3
                                while time.monotonic() < deadline and any(
                                    x not in chunks for x in expected if start <= x < stop
                                ):
                                    try:
                                        m = self.wait(
                                            "LOG_DATA",
                                            lambda m, start=start, stop=stop: (
                                                m.id == logid and start <= m.ofs < stop
                                            ),
                                            max(0.05, deadline - time.monotonic()),
                                        )
                                    except TimeoutError:
                                        break
                                    if m.ofs in expected and m.count == min(90, size - m.ofs):
                                        chunks[m.ofs] = bytes(m.data[: m.count])
                        if expected - chunks.keys():
                            raise TimeoutError(
                                "DataFlash download has missing ranges after four attempts"
                            )
                        for position in sorted(expected):
                            out.write(chunks[position])
                            digest.update(chunks[position])
                    out.flush()
                    os.fsync(out.fileno())
                partial.replace(path)
            finally:
                self.link.mav.log_request_end_send(self.sys, self.comp)
            return {
                "status": "verified",
                "file": path.name,
                "bytes": size,
                "sha256": digest.hexdigest(),
                "coverage": "Exact advertised-size snapshot; later onboard appends are not included",
            }
        raise ValueError("Unsupported operation")

    def run(self):
        try:
            while True:
                self.pump()
                if self.sys and not self.configured:
                    self.configured = True
                    self.link.mav.request_data_stream_send(self.sys, self.comp, 0, 4, 1)
                    self.link.mav.command_long_send(
                        self.sys, self.comp, 512, 0, 148, 0, 0, 0, 0, 0, 0
                    )
                    self.link.mav.command_long_send(
                        self.sys, self.comp, 512, 0, 242, 0, 0, 0, 0, 0, 0
                    )
                    self.link.mav.command_long_send(
                        self.sys, self.comp, 511, 0, 87, 250000, 0, 0, 0, 0, 0
                    )
                    for message_id in (132, 136, 245):
                        self.link.mav.command_long_send(
                            self.sys, self.comp, 511, 0, message_id, 500000, 0, 0, 0, 0, 0
                        )
                    self.link.mav.param_request_list_send(self.sys, self.comp)
                try:
                    request = self.commands.get_nowait()
                except queue.Empty:
                    continue
                if request["action"] == "shutdown":
                    break
                try:
                    result = self.operation(request)
                except Exception as exc:
                    result = {"status": "failed", "error": str(exc)}
                self.results.put({"job": request["job"], **result})
        finally:
            if self.log:
                self.log.close()
            self.link.close()


def gateway_main(endpoint, profile, events, commands, results, folder):
    # This child does not need inference credentials.
    os.environ.pop("OLLAMA_API_KEY", None)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        Gateway(endpoint, profile, events, commands, results, folder).run()
    except Exception as exc:
        events.put({"kind": "error", "error": str(exc)})
    finally:
        # A stopped UI reader must not keep the child alive flushing display data.
        for q in (events, results):
            q.close()
            q.cancel_join_thread()
