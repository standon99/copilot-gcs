const toolProgress = {
  get_vehicle_state: "Reading vehicle state…",
  get_spatial_context: "Reading map context…",
  get_map_features: "Finding nearby roads and airstrips…",
  trace_map_feature: "Tracing the map feature…",
  update_spatial_brief: "Updating the map requirements…",
  build_metric_geofence: "Building the boundary…",
  get_geofence_proposal: "Reading the proposed boundary…",
  render_spatial_preview: "Rendering the boundary preview…",
  get_mission: "Reading the mission…",
  update_waypoint: "Editing the waypoint…",
  edit_waypoints: "Editing waypoints…",
  validate_mission: "Checking the mission…",
  search_parameters: "Looking up parameters…",
  propose_parameters: "Preparing parameter changes…",
  propose_geofence: "Preparing a boundary proposal…",
  get_watch_rules: "Reading watch rules…",
  manage_watch: "Updating watch rules…",
  get_monitoring: "Reading monitoring settings…",
  configure_monitoring: "Configuring monitoring…",
};

export function chatProgress(run, stopping = false) {
  if (stopping) return "Stopping…";
  if (run?.phase === "tool")
    return toolProgress[run.active_tool] || "Running a tool…";
  return (
    {
      queued: "Waiting to start…",
      waiting: "Waiting for the model…",
      thinking: "Thinking…",
      responding: "Writing reply…",
      receiving_tools: "Preparing the next step…",
      checking: "Checking the response…",
    }[run?.phase] || "Waiting for reply…"
  );
}
