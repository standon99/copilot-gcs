# Copilot GCS

**An AI-enabled ground control station that makes everyday drone tasks easy.**

The operator starts with an outcome: fly a short route, visit a point for an
inspection, or adjust a mission. Copilot turns that request into an inspectable
plan and helps refine it. The map, parameters, instruments and AI conversation
share the same selected vehicles and mission workspace.

## Primary workflow

1. **Describe:** type a task or choose an editable starter. Connect a vehicle or
   continue in simulation. No inference runs merely from choosing a starter.
2. **Review:** inspect waypoints, altitude references and constraints on the map.
   Ask for changes and run the plan checks. Clarify missing locations or units.
3. **Upload:** choose the reviewed revision, apply it explicitly and verify the
   onboard mission. Uploading does not arm or start a vehicle.
4. **Operate:** use vehicle controls and instruments, follow progress and ask
   Copilot to explain telemetry. Further edits prepare a separate future draft.

The first task starters emphasize **simple waypoint flights and point
inspections**. A Copter inspection means flying to a specified point, holding
for a specified duration and returning. Camera capture and payload automation
are outside the current implementation. Plane and Rover starters adapt the
questions to their vehicle type instead of assuming every vehicle can hover.

## Design priorities

- Put the operator's task and next useful action ahead of protocol details.
- Make AI planning immediately available while keeping its vehicle targets
  visible. Show proposed changes and ask when information is missing.
- Keep manual planning available alongside conversation; both edit one draft.
- Clearly separate local edits, onboard configuration and flight actions.
- Preserve usable telemetry and controls when inference is slow or unavailable.
- Make simulation an easy way to rehearse a task, with diagnostics available
  when needed. Failure detection supports operation; it is not the product's
  central promise.

## Current delivery boundary

The web app controls app-launched ArduPilot simulators and can monitor external
local MAVLink feeds. It has not been validated for controlling physical drones.
Task starters prepare editable prompts, not certified flight procedures. The
onboard autopilot and operator remain responsible for execution.

Saved vehicle connections, conversational connection setup, physical-vehicle
control, survey coverage planning and payload workflows are future extensions.
They should use the same task-to-mission experience when implemented; none are
claimed as shipped here. See [implementation](implementation.md) for current
behavior, [technical design](design.md) for the architecture baseline, and
[validation](validation.md) for evidence.
