import { missionProgress, uploadReason } from "./missionFlow.mjs";

export function MissionWorkflow({
  workspace,
  vehicle,
  control,
  busy,
  onUpload,
  onRefreshChecks,
  onClaimControl,
  view,
  onView,
}: any) {
  const progress = missionProgress(workspace, vehicle);
  return (
    <section className="mission-status-bar" aria-label="Mission status">
      <div className="workspace-view-switch" aria-label="Map workspace view">
        <button
          className={view === "flight" ? "active" : ""}
          onClick={() => onView("flight")}
        >
          Live map
        </button>
        <button
          className={view === "plan" ? "active" : ""}
          onClick={() => onView("plan")}
        >
          Plan mission
        </button>
      </div>
      <div className="mission-status-copy">
        <strong>
          {progress.uploaded
            ? `Onboard · version ${workspace.active.revision}`
            : progress.hasDraft
              ? `Draft · version ${workspace.draft.revision}`
              : "No mission yet"}
        </strong>
        <span>
          {progress.hasDraft
            ? uploadReason(workspace, vehicle, control, busy)
            : "Chat with Copilot or open Plan mission to add waypoints."}
        </span>
      </div>
      {progress.hasDraft && !progress.uploaded && (
        <div className="button-row">
          <button disabled={busy} onClick={onRefreshChecks}>
            {progress.reviewed ? "Recheck" : "Check draft"}
          </button>
          {progress.reviewed && !control && vehicle.owned && (
            <button disabled={busy} onClick={onClaimControl}>
              Enable controls
            </button>
          )}
          <button
            className="primary"
            disabled={
              !progress.reviewed ||
              !control ||
              !vehicle.owned ||
              vehicle.armed ||
              busy
            }
            onClick={onUpload}
          >
            Upload mission
          </button>
        </div>
      )}
    </section>
  );
}
