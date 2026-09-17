import {
  Check,
  MessageSquare,
  ClipboardCheck,
  Upload,
  Navigation,
} from "lucide-react";
import { missionProgress } from "./missionFlow.mjs";

export function MissionWorkflow({
  workspace,
  vehicle,
  control,
  busy,
  onDescribe,
  onReview,
  onUpload,
  onOperate,
  onClaimControl,
  onRefreshChecks,
}: any) {
  const progress = missionProgress(workspace, vehicle);
  const canUpload =
    progress.reviewed && vehicle.owned && !vehicle.armed && control && !busy;
  const steps = [
    {
      title: "Describe",
      icon: MessageSquare,
      action: onDescribe,
      disabled: busy,
    },
    {
      title: "Review",
      icon: ClipboardCheck,
      action: onReview,
      disabled: !progress.hasDraft || busy,
    },
    {
      title: "Upload",
      icon: Upload,
      action: onUpload,
      disabled: !canUpload || progress.uploaded,
    },
    { title: "Operate", icon: Navigation, action: onOperate, disabled: false },
  ];
  let next = "Describe your task to Copilot, or add waypoints on the map.";
  if (progress.stage === 1)
    next = "Review this draft, then resolve any blocking issues.";
  if (progress.stage === 2)
    next = !vehicle.owned
      ? "This connection supports telemetry only. Vehicle writes are available in simulation."
      : vehicle.armed
        ? "Disarm before uploading a replacement mission."
        : !control
          ? "Claim control of this vehicle, then upload the reviewed mission."
          : "Upload this reviewed draft. Arming and starting are separate steps.";
  if (progress.stage === 3)
    next =
      vehicle.armed && vehicle.mode === "AUTO"
        ? "Mission running. Follow progress in Operate and ask Copilot about live telemetry."
        : "Mission uploaded and verified. Open Operate for arming and mission controls.";
  return (
    <section className="mission-workflow" aria-label="Mission workflow">
      <div className="workflow-steps">
        {steps.map(({ title, icon: Icon, action, disabled }, index) => (
          <button
            key={title}
            disabled={disabled}
            onClick={action}
            className={
              index === progress.stage
                ? "current"
                : index < progress.stage
                  ? "complete"
                  : ""
            }
            aria-current={index === progress.stage ? "step" : undefined}
          >
            {index < progress.stage ? <Check size={16} /> : <Icon size={16} />}
            <span>
              {index + 1}. {title}
            </span>
          </button>
        ))}
      </div>
      <div className="workflow-next">
        <span>{next}</span>
        {progress.hasDraft && !progress.uploaded && (
          <button
            disabled={busy}
            onClick={onRefreshChecks}
            title="Refresh numerical checks for the latest vehicle state without an AI request"
          >
            Refresh checks
          </button>
        )}
        {progress.stage === 2 &&
          vehicle.owned &&
          !vehicle.armed &&
          !control && (
            <button disabled={busy} onClick={onClaimControl}>
              Claim control
            </button>
          )}
        {workspace?.active && !progress.uploaded && (
          <small>
            Onboard: r{workspace.active.revision} · Editing a separate draft
          </small>
        )}
      </div>
    </section>
  );
}
