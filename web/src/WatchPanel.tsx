import React, { useState } from "react";
import { api } from "./api";

const emptyRule = {
  label: "",
  metric: "agl_m",
  operator: "lt",
  threshold: 10,
  scope: "armed",
  dwell_s: 0,
  hysteresis: 0,
  cooldown_s: 60,
  severity: "warning",
  reason: "",
  window_s: 10,
  request_ai: true,
  ai_prompt: "",
};
const scopeNames: any = {
  always: "Always",
  armed: "While armed (includes ground)",
  airborne: "Airborne (includes takeoff / landing)",
};

export function WatchPanel({
  vehicle,
  metrics,
  onSaved,
  onAsk,
  onSettings,
  expanded = false,
}: any) {
  const book = vehicle.watches || { revision: 0, notes: "", rules: [] };
  const [form, setForm] = useState<any>(null),
    [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [notes, setNotes] = useState<string | null>(null);
  const fired = book.rules.filter(
    (r: any) => r.latched || r.state === "triggered",
  ).length;
  const mutate = async (operation: string, extra: any = {}) => {
    setBusy(true);
    setError("");
    try {
      const result = await api(`/vehicles/${vehicle.id}/watches`, "POST", {
        expected_revision: book.revision,
        operation,
        ...extra,
      });
      onSaved(result);
      if (operation === "add" || operation === "update") {
        setForm(null);
        setEditing(null);
      }
      if (operation === "notes") setNotes(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className={"watch-panel" + (fired ? " has-alert" : "")}
      aria-label="Watch rules"
    >
      <details open={expanded}>
        <summary>
          <strong>Watch rules</strong>
          <span>
            {fired
              ? `${fired} ALERT${fired > 1 ? "S" : ""}`
              : `${book.rules.filter((r: any) => r.enabled).length} enabled`}{" "}
            · {book.rules.length} total
          </span>
        </summary>
        <div className="watch-content">
          <p>
            Local checks alert immediately. AI advice never sends vehicle
            commands.
          </p>
          <p className="watch-ai-state">
            {vehicle.watch_inference}{" "}
            <button onClick={onSettings}>Settings</button>
          </p>
          <div className="watch-monitoring">
            <strong>
              Periodic monitoring:{" "}
              {vehicle.monitoring?.periodic_effective
                ? `every ${vehicle.monitoring.effective_interval_s}s`
                : "off"}
            </strong>
            {vehicle.monitoring?.focus && <p>{vehicle.monitoring.focus}</p>}
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  await api(`/vehicles/${vehicle.id}/monitor`, "POST", {
                    watch_advice_enabled:
                      !vehicle.monitoring?.watch_advice_enabled,
                  });
                } catch (e: any) {
                  setError(e.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {vehicle.monitoring?.watch_advice_enabled
                ? "Pause watch AI advice"
                : "Enable watch AI advice"}
            </button>
          </div>
          <div className="button-row">
            <button
              onClick={() => {
                setForm({ ...emptyRule });
                setEditing(null);
              }}
            >
              Add a rule
            </button>
            <button onClick={onAsk}>Ask Copilot for watches</button>
          </div>
          <label>
            Operator concerns (unverified context for AI)
            <textarea
              aria-label="Operator watch concerns"
              value={notes ?? book.notes}
              maxLength={2000}
              placeholder="For example: suspected prop damage; look for propulsion symptoms."
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          {notes !== null && (
            <button disabled={busy} onClick={() => mutate("notes", { notes })}>
              Save concerns
            </button>
          )}
          {error && (
            <p className="red" role="alert">
              {error}
            </p>
          )}
          {form && (
            <form
              className="watch-editor"
              onSubmit={(e) => {
                e.preventDefault();
                void mutate(editing ? "update" : "add", {
                  id: editing,
                  rule: form,
                });
              }}
            >
              <h4>
                {editing
                  ? "Edit rule · saving disables it"
                  : "New rule · review before enabling"}
              </h4>
              <label>
                Rule name
                <input
                  required
                  maxLength={120}
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                />
              </label>
              <label>
                Measurement
                <select
                  value={form.metric}
                  onChange={(e) => setForm({ ...form, metric: e.target.value })}
                >
                  {Object.entries(metrics || {}).map(([id, m]: any) => (
                    <option key={id} value={id}>
                      {m.label} ({m.unit})
                    </option>
                  ))}
                </select>
              </label>
              <small>{metrics?.[form.metric]?.source}</small>
              <div className="watch-fields">
                <label>
                  Condition
                  <select
                    value={form.operator}
                    onChange={(e) =>
                      setForm({ ...form, operator: e.target.value })
                    }
                  >
                    <option value="lt">Below</option>
                    <option value="gt">Above</option>
                  </select>
                </label>
                <label>
                  Threshold ({metrics?.[form.metric]?.unit})
                  <input
                    required
                    type="number"
                    step="any"
                    min={-100000}
                    max={100000}
                    value={form.threshold}
                    onChange={(e) =>
                      setForm({ ...form, threshold: +e.target.value })
                    }
                  />
                </label>
              </div>
              {form.metric === "relative_alt_change_m" && (
                <label>
                  Change window (seconds)
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={form.window_s}
                    onChange={(e) =>
                      setForm({ ...form, window_s: +e.target.value })
                    }
                  />
                </label>
              )}
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={form.request_ai ?? true}
                  onChange={(e) =>
                    setForm({ ...form, request_ai: e.target.checked })
                  }
                />
                Request AI advice on trigger
              </label>
              {form.request_ai !== false && (
                <label>
                  Question for AI when triggered (optional)
                  <textarea
                    value={form.ai_prompt || ""}
                    maxLength={1000}
                    onChange={(e) =>
                      setForm({ ...form, ai_prompt: e.target.value })
                    }
                  />
                </label>
              )}
              <label>
                When to check
                <select
                  value={form.scope}
                  onChange={(e) => setForm({ ...form, scope: e.target.value })}
                >
                  {Object.entries(scopeNames).map(([v, label]: any) => (
                    <option key={v} value={v}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <small>
                Airborne needs fresh flight-phase telemetry. A minimum height
                while armed also alerts on the ground and during takeoff /
                landing.
              </small>
              <div className="watch-fields">
                {[
                  ["dwell_s", "Continuous breach (s)", 0, 60],
                  ["hysteresis", "Clearance to reset (same units)", 0, 10000],
                  ["cooldown_s", "Repeat cooldown (s)", 10, 3600],
                ].map(([key, label, min, max]: any) => (
                  <label key={key}>
                    {label}
                    <input
                      required
                      type="number"
                      step={key === "cooldown_s" ? 1 : "any"}
                      min={min}
                      max={max}
                      value={form[key]}
                      onChange={(e) =>
                        setForm({ ...form, [key]: +e.target.value })
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                Severity
                <select
                  value={form.severity}
                  onChange={(e) =>
                    setForm({ ...form, severity: e.target.value })
                  }
                >
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label>
                Reason
                <textarea
                  maxLength={1000}
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                />
              </label>
              <button type="submit" disabled={busy}>
                Save disabled rule
              </button>{" "}
              <button type="button" onClick={() => setForm(null)}>
                Cancel
              </button>
            </form>
          )}
          {book.rules.length === 0 && (
            <small>
              No custom rules yet. Describe concerns with your mission in AI
              planning, or add a numerical rule here.
            </small>
          )}
        </div>
      </details>
      <div className="watch-cards">
        {book.rules
          .slice()
          .sort(
            (a: any, b: any) =>
              Number(b.latched || b.state === "triggered") -
              Number(a.latched || a.state === "triggered"),
          )
          .map((r: any) => (
            <article
              key={r.id}
              className={
                "watch-card " +
                (r.latched || r.state === "triggered" ? "triggered" : r.state)
              }
            >
              <div className="watch-card-title">
                <strong>{r.spec.label}</strong>
                <b>
                  {r.state === "unknown"
                    ? "UNAVAILABLE"
                    : r.state.toUpperCase()}
                </b>
              </div>
              <div>
                {metrics?.[r.spec.metric]?.label || r.spec.metric}{" "}
                {r.spec.operator === "lt" ? "<" : ">"} {r.spec.threshold}{" "}
                {metrics?.[r.spec.metric]?.unit}
              </div>
              <p>
                <strong>
                  {r.reading
                    ? `${r.reading.value} ${metrics?.[r.spec.metric]?.unit || ""}`
                    : "No fresh valid reading"}
                </strong>{" "}
                · {scopeNames[r.spec.scope]}
              </p>
              {r.latched && (
                <small className="watch-latched">
                  Unacknowledged alert ·{" "}
                  {new Date(r.last_trigger * 1000).toLocaleTimeString()} ·{" "}
                  {r.count} trigger(s)
                </small>
              )}
              <small>{r.ai_status}</small>
              <details>
                <summary>Rule details · {r.origin}</summary>
                <small>
                  {r.spec.dwell_s}s continuous · {r.spec.cooldown_s}s repeat
                  cooldown · reset margin {r.spec.hysteresis} ·{" "}
                  {r.spec.severity}
                </small>
                <small>
                  {r.reading?.source || metrics?.[r.spec.metric]?.source}
                </small>

                <p>{r.spec.reason}</p>
                <p>
                  {r.spec.request_ai === false
                    ? "Local alert only"
                    : "Requests AI advice on trigger"}
                  {r.spec.metric === "relative_alt_change_m"
                    ? ` · ${r.spec.window_s}s window`
                    : ""}
                </p>
                {r.spec.ai_prompt && <p>On trigger: {r.spec.ai_prompt}</p>}
                <pre>{JSON.stringify(r.spec, null, 2)}</pre>
                {r.reading?.evidence?.map((id: string) => (
                  <small key={id}>{id}</small>
                ))}
              </details>
              <div className="button-row">
                <button
                  disabled={busy}
                  onClick={() =>
                    mutate(r.enabled ? "disable" : "enable", { id: r.id })
                  }
                >
                  {r.enabled ? "Disable" : "Enable rule"}
                </button>
                {r.latched && (
                  <button
                    disabled={busy}
                    onClick={() => mutate("acknowledge", { id: r.id })}
                  >
                    Acknowledge
                  </button>
                )}
                <button
                  disabled={busy}
                  onClick={() => {
                    setEditing(r.id);
                    setForm({ ...r.spec });
                    const el = document.querySelector(
                      ".watch-panel > details",
                    ) as HTMLDetailsElement;
                    if (el) el.open = true;
                  }}
                >
                  Edit
                </button>
                <button
                  disabled={busy}
                  onClick={() => mutate("remove", { id: r.id })}
                >
                  Remove
                </button>
              </div>
            </article>
          ))}
      </div>
    </section>
  );
}
