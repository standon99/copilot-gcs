import test from "node:test";
import assert from "node:assert/strict";
import { chatState } from "../src/chatState.mjs";

const request = {
  targets: ["copter"],
  text: "Check the plan",
  startedAt: 100,
  previousRuns: { copter: "previous" },
  model: "test-model",
};

test("sending immediately shows the new message without stale tool progress", () => {
  const oldRun = {
    id: "previous",
    status: "completed",
    round: 5,
    steps: [{ name: "old edit" }],
  };
  const oldMessage = { role: "user", text: "Previous request", ts: 90 };
  const s = chatState("copter", oldRun, [oldMessage], request);
  assert.equal(s.waiting, true);
  assert.equal(s.run, null);
  assert.deepEqual(s.messages, [oldMessage]);
  assert.equal(s.outgoing.text, request.text);
  assert.equal(s.outgoing.pending, true);
});

test("server acknowledgement replaces the sending bubble without duplication", () => {
  const old = { role: "assistant", text: "Previous reply", ts: 90 };
  const sent = { role: "user", text: request.text, ts: 100.5 };
  const s = chatState(
    "copter",
    { id: "new", status: "running" },
    [old, sent],
    request,
  );
  assert.deepEqual(s.messages, [old]);
  assert.deepEqual(s.outgoing, sent);
  assert.equal(s.waiting, true);
});

test("changing to an unrelated vehicle does not display another vehicle's request", () => {
  const s = chatState("plane", null, [], request);
  assert.equal(s.waiting, false);
  assert.equal(s.outgoing, null);
  assert.equal(s.local, null);
});

test("server completion, cancellation and failure remove waiting before HTTP cleanup", () => {
  for (const status of ["completed", "cancelled", "failed"]) {
    const messages = [
      { role: "user", text: request.text, ts: 100 },
      { role: "assistant", text: "Done", ts: 101 },
    ];
    const s = chatState("copter", { id: "new", status }, messages, request);
    assert.equal(s.waiting, false);
    assert.equal(s.outgoing, null);
    assert.deepEqual(s.messages, messages);
  }
});

test("an in-progress reply remains visible after browser reload", () => {
  const run = { id: "new", status: "running", round: 2 };
  const sent = { role: "user", text: "Read vehicle state", ts: 50 };
  const s = chatState("copter", run, [sent]);
  assert.equal(s.waiting, true);
  assert.equal(s.run, run);
  assert.equal(s.outgoing, sent);
});

test("multi-vehicle pending chat follows each explicitly selected target", () => {
  const shared = {
    ...request,
    targets: ["copter", "plane"],
    previousRuns: { copter: "previous", plane: "plane-old" },
  };
  assert.equal(
    chatState("plane", { id: "plane-old", status: "completed" }, [], shared)
      .waiting,
    true,
  );
  assert.equal(chatState("rover", null, [], shared).waiting, false);
});
