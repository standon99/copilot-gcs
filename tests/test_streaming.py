import asyncio
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from backend import main
from backend import provider as provider_module
from backend.agent import run_turn
from backend.inference_worker import StreamError, bounded_lines, read_stream
from backend.provider import Provider
from backend.settings import Preferences
from tests.test_agent import call, vehicle, working


def chunk(delta=None, finish=None, usage=None):
    data = {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}
    if usage:
        data["usage"] = usage
    return "data: " + json.dumps(data, ensure_ascii=False) + "\r\n\r\n"


def parse(parts):
    events = []
    response = httpx.Response(200, content="".join(parts).encode())
    result = read_stream(response, events.append)
    return result, events


def test_stream_assembles_interleaved_tool_calls_and_usage_after_finish():
    result, events = parse(
        [
            ": keepalive\r\n\r\n",
            chunk({"role": "assistant", "reasoning": "Check the runway’s position."}),
            chunk(
                {
                    "content": "I’ll check ",
                    "tool_calls": [
                        {
                            "index": 1,
                            "id": "call-b",
                            "function": {"name": "get_mission", "arguments": '{"vehicle_'},
                        },
                        {
                            "index": 0,
                            "id": "call-",
                            "type": "function",
                            "function": {"name": "get_vehicle", "arguments": '{"vehicle_id":'},
                        },
                    ],
                }
            ),
            chunk(
                {
                    "content": "the plan.",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "a",
                            "function": {"name": "_state", "arguments": '"v"}'},
                        },
                        {"index": 1, "function": {"arguments": 'id":"v"}'}},
                    ],
                }
            ),
            chunk(finish="tool_calls"),
            'data: {"choices":[],"usage":{"total_tokens":42}}\r\n\r\n',
            "data: [DONE]\r\n\r\n",
        ]
    )
    message = result["message"]
    assert message["content"] == "I’ll check the plan."
    assert message["reasoning"] == "Check the runway’s position."
    assert [c["id"] for c in message["tool_calls"]] == ["call-a", "call-b"]
    assert message["tool_calls"][0]["function"]["name"] == "get_vehicle_state"
    assert all(
        json.loads(c["function"]["arguments"]) == {"vehicle_id": "v"} for c in message["tool_calls"]
    )
    assert result["usage"]["total_tokens"] == 42
    assert events[0] == {"event": "delta", "field": "thinking", "text": message["reasoning"]}


def test_ollama_complete_tool_chunks_reusing_index_stay_separate():
    parts = [
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": ident,
                        "type": "function",
                        "function": {"name": name, "arguments": '{"vehicle_id":"v"}'},
                    }
                ]
            }
        )
        for ident, name in [("call-a", "get_vehicle_state"), ("call-b", "get_mission")]
    ]
    result, _ = parse([*parts, chunk(finish="tool_calls"), "data: [DONE]\n\n"])
    calls = result["message"]["tool_calls"]
    assert [c["id"] for c in calls] == ["call-a", "call-b"]
    assert [c["function"]["name"] for c in calls] == ["get_vehicle_state", "get_mission"]
    assert all(json.loads(c["function"]["arguments"]) == {"vehicle_id": "v"} for c in calls)
    with pytest.raises(StreamError, match="repeated"):
        parse([parts[0], parts[0], chunk(finish="tool_calls")])


def test_transport_handles_split_utf8_and_bounds_unterminated_events():
    class Bytes(httpx.SyncByteStream):
        def __iter__(self):
            yield b"data: \xe2"
            yield b"\x86\x92\r"
            yield b"\n\r\n"

    assert list(bounded_lines(httpx.Response(200, stream=Bytes()))) == ["data: →", ""]
    with pytest.raises(StreamError, match="size limit"):
        list(bounded_lines(httpx.Response(200, content=b"x" * (1024 * 1024 + 1))))


async def test_parent_deadline_kills_worker_even_after_progress(monkeypatch):
    processes = []
    create = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await create(*args, **kwargs)
        processes.append(process)
        return process

    script = 'import sys,time; sys.stdin.read(); print(\'{"event":"delta","field":"thinking","text":"Started"}\',flush=True); time.sleep(60)'
    monkeypatch.setattr(
        provider_module, "sandbox_command", lambda base: ([sys.executable, "-c", script], False)
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    options = Preferences(base_url="http://localhost:11434/v1").model_dump()
    # Shorten the internal deadline without waiting for a production 10 s minimum.
    options["inference_timeout"] = -4.5
    events = []
    with pytest.raises(RuntimeError, match="timeout.*Settings"):
        await Provider().tool_turn("system", [], [], options, events.append)
    assert any(e.get("field") == "thinking" for e in events)
    assert processes[0].returncode is not None


@pytest.mark.parametrize("field", ["reasoning", "reasoning_content", "thinking"])
def test_only_explicit_supported_thinking_fields_are_exposed(field):
    result, events = parse(
        [
            chunk({field: "Visible thought", "private_metadata": "ignored"}),
            chunk({"content": "Answer"}, finish="stop"),
            "data: [DONE]\n\n",
        ]
    )
    assert result["message"][field] == "Visible thought"
    assert "ignored" not in json.dumps([result, events])
    assert [e["field"] for e in events] == ["thinking", "content"]


@pytest.mark.parametrize("suffix", ["", "data: [DONE]\n\n"])
def test_dropped_stream_never_returns_a_completed_message(suffix):
    with pytest.raises(StreamError, match="before a complete response"):
        parse([chunk({"content": "Done, changes made"}), suffix])


@pytest.mark.parametrize(
    "delta",
    [
        {"content": "x" * 16001},
        {"reasoning": "x" * 32001},
        {"tool_calls": [{"index": 8}]},
        {"tool_calls": [{"index": 0, "function": {"arguments": {"vehicle_id": "v"}}}]},
    ],
)
def test_stream_rejects_oversized_text_and_invalid_tool_fragments(delta):
    with pytest.raises(StreamError):
        parse([chunk(delta), chunk(finish="stop")])


def test_stream_error_does_not_reflect_provider_details():
    with pytest.raises(StreamError, match="Provider reported an error") as error:
        parse(['data: {"error":{"message":"private-token and prompt"}}\n\n'])
    assert "private-token" not in str(error.value)


@pytest.fixture
def endpoint():
    received = []
    hold = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append({"body": body, "auth": self.headers.get("Authorization")})
            model = body["model"]
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/json" if model == "buffered" else "text/event-stream"
            )
            self.end_headers()
            try:
                if model == "buffered":
                    self.wfile.write(
                        json.dumps(
                            {
                                "choices": [
                                    {
                                        "message": {
                                            "content": "Buffered answer",
                                            "reasoning": "Explicit thought",
                                        },
                                        "finish_reason": "stop",
                                    }
                                ]
                            }
                        ).encode()
                    )
                    return
                self.wfile.write(chunk({"reasoning": "First thought"}).encode())
                self.wfile.flush()
                if model == "hold":
                    hold.wait(3)
                else:
                    time.sleep(0.15)
                if model == "dropped":
                    return
                self.wfile.write(chunk({"content": "Answer"}).encode())
                self.wfile.write(
                    chunk(
                        finish="length" if model == "length" else "stop", usage={"total_tokens": 11}
                    ).encode()
                )
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", received, hold
    finally:
        hold.set()
        server.shutdown()
        server.server_close()
        thread.join()


async def test_isolated_worker_delivers_thinking_before_http_request_finishes(endpoint):
    base, received, hold = endpoint
    events = []
    ready = asyncio.Event()

    def update(event):
        events.append(event)
        if event.get("field") == "thinking":
            ready.set()

    task = asyncio.create_task(
        Provider().tool_turn(
            "system", [], [], Preferences(base_url=base, model="hold").model_dump(), update
        )
    )
    await asyncio.wait_for(ready.wait(), 2)
    assert not task.done()
    hold.set()
    message, meta = await task
    assert message["content"] == "Answer" and meta["usage"]["total_tokens"] == 11
    assert meta["streamed"] is True
    assert received[0]["body"]["stream"] is True
    assert received[0]["body"]["stream_options"]["include_usage"] is True
    assert received[0]["auth"] is None and len(received) == 1
    assert events[-1]["field"] == "content"


async def test_buffered_endpoint_uses_same_response_without_retry(endpoint):
    base, received, _ = endpoint
    events = []
    message, meta = await Provider().tool_turn(
        "system", [], [], Preferences(base_url=base, model="buffered").model_dump(), events.append
    )
    assert message["content"] == "Buffered answer"
    assert events[-2]["field"] == "thinking" and events[-1]["field"] == "content"
    assert meta["streamed"] is False and len(received) == 1


@pytest.mark.parametrize(
    "model,match", [("dropped", "before a complete response"), ("length", "output token limit")]
)
async def test_partial_or_token_limited_response_fails_without_retry(endpoint, model, match):
    base, received, _ = endpoint
    with pytest.raises((RuntimeError, ValueError), match=match):
        await Provider().tool_turn(
            "system", [], [], Preferences(base_url=base, model=model).model_dump()
        )
    assert len(received) == 1


async def test_cancelling_stream_kills_worker_and_releases_request_slot(endpoint, monkeypatch):
    base, received, hold = endpoint
    provider = Provider()
    ready = asyncio.Event()
    processes = []
    create = asyncio.create_subprocess_exec

    async def capture(*args, **kwargs):
        process = await create(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", capture)
    task = asyncio.create_task(
        provider.tool_turn(
            "system",
            [],
            [],
            Preferences(base_url=base, model="hold").model_dump(),
            lambda event: ready.set() if event.get("field") == "thinking" else None,
        )
    )
    await asyncio.wait_for(ready.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].returncode is not None
    hold.set()
    await asyncio.wait_for(
        provider.tool_turn(
            "system", [], [], Preferences(base_url=base, model="buffered").model_dump()
        ),
        2,
    )
    assert len(received) == 2


async def test_thinking_and_preamble_replayed_with_tool_results_and_rounds_kept_separate():
    _, prefs, turn = working()
    run = {"steps": []}

    async def respond(system, messages, tools, options, on_event):
        if len(messages) == 2:
            on_event({"event": "delta", "field": "thinking", "text": "Need current mission"})
            on_event({"event": "delta", "field": "content", "text": "Checking"})
            assert run["phase"] == "responding" and run["responses"][0]["thinking"]
            result = call("get_mission", {"vehicle_id": "v"})
            result.update(reasoning="Need current mission", content="Checking")
            return result, {}
        assert messages[-2]["reasoning"] == "Need current mission"
        assert messages[-2]["content"] == "Checking"
        assert messages[-1]["role"] == "tool"
        on_event({"event": "delta", "field": "content", "text": "Read the plan."})
        return {"content": "Read the plan."}, {}

    reply, _ = await run_turn(
        SimpleNamespace(tool_turn=respond),
        turn,
        "system",
        {},
        prefs.model_dump(),
        run,
        lambda: None,
    )
    assert reply == "Read the plan."
    assert [r["status"] for r in run["responses"]] == ["tool_calls", "final"]
    assert run["responses"][1]["thinking"] == ""


async def test_interrupted_stream_keeps_trace_but_never_commits_staged_edit(monkeypatch):
    v = vehicle()
    monkeypatch.setattr(main, "vehicles", {"v": v})
    monkeypatch.setattr(main, "event", lambda *args: None)

    async def respond(system, messages, tools, options, on_event):
        if len(messages) == 2:
            return call(
                "update_waypoint",
                {
                    "vehicle_id": "v",
                    "expected_revision": 0,
                    "waypoint_id": "wp",
                    "fields": {"alt": 55},
                },
            ), {}
        on_event({"event": "delta", "field": "thinking", "text": "Check the new altitude"})
        on_event({"event": "delta", "field": "content", "text": "Updated to 55"})
        raise RuntimeError("Model stream interrupted")

    monkeypatch.setattr(main.provider, "tool_turn", respond)
    with pytest.raises(main.HTTPException):
        await main.interaction(
            main.Interaction(message="Raise waypoint to 55 m", targets=["v"], enabled=True)
        )
    assert v.draft["waypoints"][0]["alt"] == 20 and v.draft["revision"] == 0
    assert v.chat[-1]["role"] == "error"
    trace = v.chat[-1]["model_responses"]
    assert trace[-1]["content"] == "Updated to 55" and trace[-1]["status"] == "interrupted"
    assert trace[-1]["thinking"] == "Check the new altitude"
