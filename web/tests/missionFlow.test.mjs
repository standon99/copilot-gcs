import test from "node:test";
import assert from "node:assert/strict";
import { missionProgress, taskStarters } from "../src/missionFlow.mjs";

const vehicle = { id: "copter-a", epoch: 2 };
const draft = { revision: 3, waypoints: [{ command: 16 }] };
const work = { vehicle_id: vehicle.id, draft };
test("missing or another vehicle workspace cannot advance this mission", () => {
  assert.equal(missionProgress(null, vehicle).stage, 0);
  assert.equal(
    missionProgress({ ...work, vehicle_id: "copter-b" }, vehicle).stage,
    0,
  );
});
test("an empty draft starts with describing the task", () => {
  assert.equal(
    missionProgress({ ...work, draft: { revision: 0, waypoints: [] } }, vehicle)
      .stage,
    0,
  );
});
test("a new route needs review", () =>
  assert.equal(missionProgress(work, vehicle).stage, 1));
test("only a review of this revision and boot epoch advances to upload", () => {
  for (const review of [
    { revision: 2, epoch: 2, upload_allowed: true },
    { revision: 3, epoch: 1, upload_allowed: true },
    { revision: 3, epoch: 2, upload_allowed: false },
  ])
    assert.equal(missionProgress({ ...work, review }, vehicle).stage, 1);
  assert.equal(
    missionProgress(
      { ...work, review: { revision: 3, epoch: 2, upload_allowed: true } },
      vehicle,
    ).stage,
    2,
  );
});
test("editing after an upload never marks the newer draft uploaded", () => {
  assert.equal(
    missionProgress({ ...work, active: { revision: 2 } }, vehicle).uploaded,
    false,
  );
  assert.equal(
    missionProgress(
      { ...work, active: { revision: 3 } },
      { ...vehicle, active_revision: 3 },
    ).stage,
    3,
  );
});
test("a cleared onboard snapshot cannot leave an old workspace marked uploaded", () => {
  assert.equal(
    missionProgress(
      { ...work, active: { revision: 3 } },
      { ...vehicle, epoch: 3, active_revision: null },
    ).uploaded,
    false,
  );
});
test("task starters preserve vehicle-specific constraints and missing locations", () => {
  assert.match(taskStarters("copter")[0].prompt, /10 seconds/);
  assert.match(
    taskStarters("copter")[1].prompt,
    /Ask me for the inspection coordinates/,
  );
  assert.match(taskStarters("rover")[0].prompt, /rover/);
  assert.doesNotMatch(taskStarters("rover")[0].prompt, /take off|takeoff/);
  assert.match(taskStarters("plane")[1].prompt, /Do not assume hover/);
});

test("stale vehicle context cannot be shown as ready to upload", () => {
  const ready = {
    ...work,
    review: { revision: 3, epoch: 2, upload_allowed: true },
  };
  assert.equal(
    missionProgress(ready, { ...vehicle, review_current: false }).reviewed,
    false,
  );
  assert.equal(
    missionProgress({ ...ready, review_current: false }, vehicle).reviewed,
    false,
  );
});
