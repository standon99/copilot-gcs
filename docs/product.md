# Product and workflow

Copilot GCS combines a map, flight instruments, mission editor and model chat
for ArduPilot Copter, Plane and Rover.

1. Start one or more simulations, or connect external telemetry.
2. Select a vehicle. In **Flight**, describe a mission in **Chat**, or use
   **Plan mission** to edit waypoints and exclusion areas.
3. Inspect the draft and run **Check draft**. Upload the reviewed version.
4. **Flight controls** offers the next explicit action: enable controls, prepare
   the launch mode, arm, then start. **Live map** shows progress.
5. **Alerts** holds local warnings and AI assessments. **Watch rules** holds
   thresholds, enabled/disabled states, trigger evidence and acknowledgement.

Chat remains a conversation. Numerical checks live with the plan; alerts and
watch editing do not replace or clutter message history. A map edit revises a
local draft without changing an uploaded mission. Clearing a draft is reversible
with Undo and does not clear the onboard mission or fences.

Use plain labels, concrete status and necessary instructions. Avoid branding
taglines, motivational copy and a separate Describe/Review/Upload/Operate strip.

## Current scope

Waypoint flights and point inspections are supported as navigation tasks.
Camera/payload automation, survey coverage and physical-vehicle control are not
implemented. External MAVLink connections provide telemetry; writes remain
limited to app-owned simulators. Simulation checks are not physical-flight
validation.

AI can edit drafts and propose parameters, exclusion areas and watch rules.
The operator applies onboard changes and controls flight. Vision input is an
explicit map attachment, not a continuous image feed. See the
[AI interface](ai-interface.md), [usage](usage.md), [implementation](implementation.md)
and [validation](validation.md).
