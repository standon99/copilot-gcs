import test from "node:test";
import assert from "node:assert/strict";
import { chatProgress } from "../src/chatProgress.mjs";
import { chatState } from "../src/chatState.mjs";

test("stream phases distinguish waiting, thinking, text and actual tools", () => {
  assert.equal(chatProgress({ phase: "queued" }), "Waiting to start…");
  assert.equal(chatProgress({ phase: "waiting" }), "Waiting for the model…");
  assert.equal(chatProgress({ phase: "thinking" }), "Thinking…");
  assert.equal(chatProgress({ phase: "responding" }), "Writing reply…");
  assert.equal(
    chatProgress({ phase: "tool", active_tool: "build_metric_geofence" }),
    "Building the boundary…",
  );
  assert.equal(
    chatProgress({ phase: "tool", active_tool: "validate_mission" }),
    "Checking the mission…",
  );
  assert.equal(chatProgress({ phase: "thinking" }, true), "Stopping…");
});

test("reload recovers partial text only for the vehicle's running turn", () => {
  const run = {
    id: "turn",
    status: "running",
    phase: "responding",
    responses: [{ round: 1, content: "Partial reply", thinking: "Checking" }],
  };
  assert.equal(
    chatState("copter", run).run.responses[0].content,
    "Partial reply",
  );
  assert.equal(chatState("plane", null).run, null);
  for (const status of ["completed", "failed", "cancelled"])
    assert.equal(chatState("copter", { ...run, status }).run, null);
});
