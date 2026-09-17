import React, { useEffect, useState } from "react";
import { api } from "./api";

export function FencePanel({ vehicle, control, onChanged, onClaim }: any) {
  const [loaded, setLoaded] = useState<any>(null),
    [form, setForm] = useState<any>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const load = (data: any) => {
    setLoaded(data);
    setForm({
      enabled: data.enabled,
      radius: data.radius ?? 300,
      margin: data.values.FENCE_MARGIN ?? 2,
      action: data.values.FENCE_ACTION ?? 1,
      ceiling: vehicle.profile !== "rover" && data.max_alt !== null,
      max_alt: data.values.FENCE_ALT_MAX ?? 100,
    });
  };
  const reload = async () => {
    try {
      setError("");
      load(await api(`/vehicles/${vehicle.id}/fence`));
    } catch (e: any) {
      setError(e.message);
    }
  };
  useEffect(() => {
    void reload();
  }, [vehicle.id]);
  const change = (patch: any) => setForm({ ...form, ...patch });
  return (
    <section className="fence-editor">
      <div className="section-title">
        <h2>Onboard geofence</h2>
        <button disabled={busy} onClick={reload}>
          Reload fence
        </button>
      </div>
      <p>
        A circle centred on the vehicle's reported home, with an optional
        ceiling above home. These settings are written to ArduPilot separately
        from the mission upload.
      </p>
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}
      {message && <div className="banner notice">{message}</div>}
      {!loaded?.available ? (
        <p>
          Waiting for fence parameters. Once telemetry is ready, use Reload
          fence.
        </p>
      ) : (
        <>
          <div className="intent-fields">
            <label className="check-row">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => change({ enabled: e.target.checked })}
              />
              Enable onboard fence
            </label>
            <label>
              Radius from home (m)
              <input
                type="number"
                min="30"
                max="10000"
                value={form.radius}
                onChange={(e) => change({ radius: +e.target.value })}
              />
            </label>
            <label>
              Margin (m)
              <input
                type="number"
                min="1"
                max="10"
                value={form.margin}
                onChange={(e) => change({ margin: +e.target.value })}
              />
            </label>
            <label>
              Breach action
              <select
                value={form.action}
                onChange={(e) => change({ action: +e.target.value })}
              >
                {Object.entries(loaded.actions).map(([k, v]: any) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            {vehicle.profile !== "rover" && (
              <>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={form.ceiling}
                    onChange={(e) => change({ ceiling: e.target.checked })}
                  />
                  Limit altitude above home
                </label>
                <label>
                  Maximum altitude above home (m)
                  <input
                    type="number"
                    min="10"
                    max="1000"
                    disabled={!form.ceiling}
                    value={form.max_alt}
                    onChange={(e) => change({ max_alt: +e.target.value })}
                  />
                </label>
              </>
            )}
          </div>
          <p>
            This editor selects the circle
            {vehicle.profile !== "rover"
              ? " and optional maximum-altitude"
              : ""}{" "}
            fence types and disables automatic enable-on-flight behavior.
            Existing polygon/minimum-altitude type selections will be replaced.
            Report Only records a breach without a recovery action.
          </p>
          <p>
            {vehicle.home
              ? `Reported home: ${vehicle.home.lat.toFixed(6)}, ${vehicle.home.lon.toFixed(6)}`
              : "Waiting for reported home; circle will appear when home is known."}{" "}
            The amber circle shows the saved onboard configuration.
          </p>
          <button
            className="primary"
            disabled={busy || !control || vehicle.armed || !vehicle.owned}
            onClick={async () => {
              setBusy(true);
              setError("");
              setMessage("");
              try {
                const result = await api(
                  `/vehicles/${vehicle.id}/fence`,
                  "PUT",
                  {
                    enabled: form.enabled,
                    radius: form.radius,
                    margin: form.margin,
                    action: form.action,
                    max_alt:
                      form.ceiling && vehicle.profile !== "rover"
                        ? form.max_alt
                        : null,
                    expected: loaded.values,
                  },
                );
                load(result);
                setMessage("Onboard fence saved and independently read back.");
                onChanged();
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Writing & verifying…" : "Apply onboard fence"}
          </button>
          {!control && (
            <button onClick={onClaim}>Claim control for fence</button>
          )}
          {(!control || vehicle.armed) && (
            <p>Claim control and disarm to apply fence changes.</p>
          )}
        </>
      )}
    </section>
  );
}
