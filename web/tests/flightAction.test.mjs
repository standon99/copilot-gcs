import test from "node:test";
import assert from "node:assert/strict";
import { flightAction } from "../src/missionFlow.mjs";

const vehicle = {
  id: "v",
  owned: true,
  heartbeat_age: 0,
  profile: "copter",
  mode: "STABILIZE",
  armed: false,
};
const work = { vehicle_id: "v", active: { revision: 2 } };
test("mission launch separates control, mode, arm and start", () => {
  assert.equal(flightAction(work, vehicle, false).action, "control");
  assert.deepEqual(flightAction(work, vehicle, true).args, { mode: "GUIDED" });
  assert.equal(
    flightAction(work, { ...vehicle, mode: "GUIDED" }, true).action,
    "arm",
  );
  assert.equal(
    flightAction(work, { ...vehicle, mode: "GUIDED", armed: true }, true)
      .action,
    "start",
  );
  assert.equal(
    flightAction(work, { ...vehicle, mode: "AUTO", armed: true }, true).action,
    undefined,
  );
});
test("flight helper does not offer writes for missing, wrong or stale sessions", () => {
  assert.equal(
    flightAction(work, { ...vehicle, owned: false }, true).action,
    undefined,
  );
  assert.equal(
    flightAction(work, { ...vehicle, heartbeat_age: 4 }, true).action,
    undefined,
  );
  assert.equal(
    flightAction({ ...work, vehicle_id: "other" }, vehicle, true).action,
    undefined,
  );
  assert.equal(
    flightAction({ ...work, active: null }, vehicle, true).action,
    "plan",
  );
});
test("launch mode follows selected vehicle profile", () => {
  assert.deepEqual(
    flightAction(work, { ...vehicle, profile: "plane" }, true).args,
    { mode: "FBWA" },
  );
  assert.deepEqual(
    flightAction(work, { ...vehicle, profile: "rover" }, true).args,
    { mode: "HOLD" },
  );
});
