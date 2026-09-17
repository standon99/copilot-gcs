import React from "react";

export function AlertsPanel({ vehicle: v, onWatches, onEvidence }: any) {
  const watches = (v.watches?.rules || []).filter(
    (r: any) => r.latched || r.state === "triggered",
  );
  return (
    <section className="alerts-pane" aria-label="Alerts and AI advice">
      <h2>Alerts & AI advice</h2>
      <p>
        Live checks and watch triggers for the selected vehicle. You choose all
        vehicle actions.
      </p>
      {v.recording_error && (
        <div className="persistent-alert critical">{v.recording_error}</div>
      )}
      {watches.map((r: any) => (
        <article className="watch-card triggered" key={r.id}>
          <strong>{r.spec.label}</strong>
          <p>
            {r.spec.metric} {r.spec.operator === "lt" ? "<" : ">"}{" "}
            {r.spec.threshold} · {r.latched ? "Unacknowledged" : "Triggered"}
          </p>
          <small>{r.ai_status}</small>
          <button onClick={onWatches}>Inspect / acknowledge rule</button>
        </article>
      ))}
      {v.rules.map((r: any) => (
        <div key={r.code} className={"rule " + r.severity}>
          <strong>{r.code.replaceAll("_", " ")}</strong>
          <p>{r.text}</p>
        </div>
      ))}
      {!v.rules.length && !watches.length && (
        <p>
          No current deterministic alerts. This covers configured checks only.
        </p>
      )}
      <h3>Latest AI assessment</h3>
      {v.assessment ? (
        <div
          className={
            "assessment " +
            (v.assessment_stale ? "insufficient_data" : v.assessment.status)
          }
        >
          <div className="card-kicker">
            {v.assessment_stale ? "STALE · NOT CURRENT" : "ADVISORY"}
            <span>
              {new Date(v.assessment.completed_at * 1000).toLocaleTimeString()}
            </span>
          </div>
          <p>{v.assessment.summary}</p>
          {v.assessment.incidents.map((i: any, n: number) => (
            <div className={"incident " + i.severity} key={n}>
              <strong>{i.summary}</strong>
              <p>{i.recommendation}</p>
              <div className="evidence-links">
                {i.evidence.map((id: string, k: number) => (
                  <button key={id} onClick={() => onEvidence(id)}>
                    Evidence {k + 1}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p>
          {v.monitor_effective
            ? "Waiting for an assessment."
            : "Automatic AI advice is paused. Local checks continue."}
        </p>
      )}
    </section>
  );
}
