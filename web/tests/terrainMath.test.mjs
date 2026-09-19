import test from "node:test";
import assert from "node:assert/strict";
import {
  aircraftFitBounds,
  projectClip,
  tiltedPitch,
} from "../src/terrainMath.mjs";

test("scroll up tilts from 2D and down returns to 2D within pitch limits", () => {
  assert(tiltedPitch(0, -50) > 0);
  assert.equal(tiltedPitch(0, -1000), 65);
  assert.equal(tiltedPitch(40, 1000), 0);
});

test("fitting includes aircraft altitude above terrain and multiple positions", () => {
  const a = {
    position_valid: true,
    coverage: { GLOBAL_POSITION_INT: 0.2 },
    heartbeat_age: 0.2,
    position: { lon: 149, lat: -35, amsl: 600 },
  };
  const low = aircraftFitBounds([a], () => 580);
  const high = aircraftFitBounds(
    [{ ...a, position: { ...a.position, amsl: 1600 } }],
    () => 580,
  );
  assert(high[2] - high[0] > 10 * (low[2] - low[0]));
  const both = aircraftFitBounds(
    [a, { ...a, position: { lon: 149.1, lat: -35, amsl: 900 } }],
    () => 580,
  );
  assert(both[0] < 149 && both[2] > 149.1);
  assert.equal(
    aircraftFitBounds([{ ...a, position_valid: false }], () => 580),
    null,
  );
  assert.equal(
    aircraftFitBounds(
      [{ ...a, coverage: { GLOBAL_POSITION_INT: 4 } }],
      () => 580,
    ),
    null,
  );
});

test("screen projection keeps vertical coordinates and rejects points behind camera", () => {
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const p = projectClip(identity, { x: 0, y: 0, z: 0.5 }, 1000, 600);
  assert.equal(p.x, 500);
  assert.equal(p.y, 300);
  assert.equal(p.clip[2], 0.5);
  identity[15] = -1;
  assert.equal(
    projectClip(identity, { x: 0, y: 0, z: 0 }, 1000, 600).inFront,
    false,
  );
});
