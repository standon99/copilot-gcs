// Presentation state only. The backend revalidates every vehicle operation.
export function missionProgress(workspace, vehicle) {
  if (!workspace || workspace.vehicle_id !== vehicle?.id) {
    return { stage: 0, reviewed: false, uploaded: false, hasDraft: false };
  }
  const draft = workspace.draft;
  const hasDraft = Boolean(draft?.waypoints?.length);
  const review = workspace.review;
  const reviewed = Boolean(
    hasDraft &&
    review &&
    review.revision === draft.revision &&
    review.epoch === vehicle.epoch &&
    vehicle.review_current !== false &&
    workspace.review_current !== false &&
    review.upload_allowed,
  );
  const uploaded = Boolean(
    hasDraft &&
    workspace.active &&
    workspace.active.revision === draft.revision &&
    vehicle.active_revision === draft.revision,
  );
  return {
    stage: uploaded ? 3 : reviewed ? 2 : hasDraft ? 1 : 0,
    reviewed,
    uploaded,
    hasDraft,
  };
}

export function uploadReason(workspace, vehicle, control, busy) {
  if (busy) return "Wait for the current request to finish.";
  if (!vehicle?.owned) return "Uploads require an app-owned simulator.";
  if (!workspace?.draft?.waypoints?.length)
    return "Add a mission before uploading.";
  if (missionProgress(workspace, vehicle).uploaded)
    return "This version is already uploaded and verified. Open Operate for mission controls.";
  if (vehicle.armed) return "Disarm before uploading a mission.";
  if (!missionProgress(workspace, vehicle).reviewed)
    return workspace.review &&
      (vehicle.review_current === false || workspace.review_current === false)
      ? "Vehicle context changed. Refresh checks before uploading."
      : "Review this draft and resolve blocking findings first.";
  if (!control)
    return "Enable vehicle controls, then upload. This does not arm the vehicle.";
  return "Ready to upload this version and verify it on the vehicle.";
}

export function taskStarters(profile = "copter") {
  if (profile === "rover")
    return [
      {
        title: "Waypoint drive",
        detail: "Choose a route and finish point.",
        prompt:
          "Help me create a local waypoint mission for this rover. Ask me for the route coordinates, ground speed and finish behavior before editing. Do not invent locations.",
      },
      {
        title: "Visit a point",
        detail: "Drive to a location for an inspection.",
        prompt:
          "Help me plan a rover inspection visit. Ask me for the inspection coordinates, ground speed and finish behavior. This is a navigation task; do not assume camera or payload actions.",
      },
      {
        title: "Review my route",
        detail: "Explain issues before upload.",
        prompt:
          "Review the current rover mission and explain the route, possible issues and missing information in plain language. Do not edit the draft.",
      },
    ];
  if (profile === "plane")
    return [
      {
        title: "Waypoint flight",
        detail: "Build a route for your fixed-wing vehicle.",
        prompt:
          "Help me create a local waypoint mission for this plane. Ask for route coordinates, altitude and its reference, takeoff setup and finish behavior before editing. Explain any unverified climb, turn or landing requirements.",
      },
      {
        title: "Inspection pass",
        detail: "Plan a pass over a known location.",
        prompt:
          "Help me plan a fixed-wing inspection pass. Ask for the location, pass direction, altitude and its reference, takeoff setup and finish behavior. Do not assume hover, camera capture or validated terrain clearance.",
      },
      {
        title: "Review my route",
        detail: "Check the plan before upload.",
        prompt:
          "Review the current plane mission and explain its route, possible issues and missing information in plain language. Do not edit the draft.",
      },
    ];
  return [
    {
      title: "Quick flight",
      detail: "Take off, hold briefly, return home.",
      prompt:
        "Replace this copter's local mission draft with a simple flight: take off to 20 metres above the reported home, hold over home for 10 seconds, then return home. Use timed loiter, not unlimited loiter. If home is unavailable, ask me to wait. Explain the resulting steps. Do not upload, arm or start the vehicle.",
    },
    {
      title: "Point inspection",
      detail: "Visit a location, hold and return.",
      prompt:
        "Help me plan a point inspection for this copter. Ask me for the inspection coordinates, altitude above home and hold duration before editing. The mission should take off, visit that point, hold for the requested duration and return home. This is positioning for an inspection; do not assume camera capture or obstacle clearance.",
    },
    {
      title: "Waypoint route",
      detail: "Turn a few locations into a mission.",
      prompt:
        "Help me create a local waypoint mission for this copter. Ask me for the route coordinates, altitude above home and how the mission should finish before editing. Do not invent locations. Explain the route in plain language.",
    },
  ];
}
