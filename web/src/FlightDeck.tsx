import React, { useState } from "react";
import { AttitudeIndicator } from "./AttitudeIndicator";
import { flightAction } from "./missionFlow.mjs";

export function FlightDeck({
  vehicle: v,
  workspace,
  control,
  busy,
  modes,
  onControl,
  onAction,
  onPlan,
  alertCount,
  onAlerts,
}: any) {
  const [mode, setMode] = useState("");
  const [alt, setAlt] = useState(20);
  const next = flightAction(workspace, v, control);
  const perform = () => {
    if (next.action === "control") onControl();
    else if (next.action === "plan") onPlan();
    else if (next.action) onAction(next.action, next.args);
  };
  return (
    <aside className="flight-deck" aria-label="Flight instruments and controls">
      <AttitudeIndicator vehicle={v} />
      <section className="flight-actions">
        <div className="section-title">
          <h2>Flight controls</h2>
          <span>{v.armed ? "ARMED" : "DISARMED"}</span>
        </div>
        <p>{next.help}</p>
        <button
          className="primary wide"
          disabled={busy || !next.action}
          onClick={perform}
        >
          {next.label}
        </button>
        <small>
          {control
            ? "Controls enabled for this browser"
            : "Vehicle actions need control access"}{" "}
          · {v.mode || "Waiting for mode"}
        </small>
        <div className="flight-recovery">
          <button
            disabled={!control || busy}
            onClick={() =>
              onAction("mode", { mode: v.profile === "rover" ? "HOLD" : "RTL" })
            }
          >
            {v.profile === "rover" ? "Hold position" : "Return home"}
          </button>
          {v.armed && (
            <button
              disabled={!control || busy}
              onClick={() => onAction("arm", { armed: false })}
            >
              Disarm
            </button>
          )}
        </div>
        <details className="manual-controls">
          <summary>Manual controls</summary>
          {!control && (
            <button disabled={busy || !v.owned} onClick={onControl}>
              Enable vehicle controls
            </button>
          )}
          <label>
            Flight mode
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">Choose mode</option>
              {modes.map((m: string) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
          <button
            disabled={!mode || !control || busy}
            onClick={() => onAction("mode", { mode })}
          >
            Set selected mode
          </button>
          {!v.armed && (
            <button
              disabled={!control || busy}
              onClick={() => onAction("arm", { armed: true })}
            >
              Arm vehicle
            </button>
          )}
          {v.profile === "copter" && (
            <>
              <label>
                Takeoff altitude above home (m)
                <input
                  type="number"
                  min="1"
                  max="120"
                  value={alt}
                  onChange={(e) => setAlt(+e.target.value)}
                />
              </label>
              <button
                disabled={!control || !v.armed || v.mode !== "GUIDED" || busy}
                onClick={() => onAction("takeoff", { alt })}
              >
                Take off to {alt} m
              </button>
            </>
          )}
        </details>
      </section>
      <button
        className={"flight-alert-summary" + (alertCount ? " has-alert" : "")}
        onClick={onAlerts}
      >
        <strong>
          {alertCount
            ? `${alertCount} alerts need attention`
            : "No active warning alerts"}
        </strong>
        <span>Open alerts & AI advice →</span>
      </button>
    </aside>
  );
}
