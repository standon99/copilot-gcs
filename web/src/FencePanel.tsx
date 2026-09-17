import React, { useEffect, useState } from "react";
import { api } from "./api";

export function FencePanel({
  vehicle,
  draft,
  control,
  onChanged,
  onClaim,
}: any) {
  const [loaded, setLoaded] = useState<any>(null),
    [form, setForm] = useState<any>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const load = (data: any) => {
    setLoaded(data);
    setForm({
      enabled: data.enabled,
      circle: data.circle,
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
        Draw red exclusion areas on the map, then upload them here. Fences are
        separate from mission upload. Route crossings block mission upload;
        onboard breaches use the chosen action, without automatic route
        planning.
      </p>
      <div className="polygon-upload">
        <strong>
          {draft?.intent?.exclusions?.length || 0} draft exclusion areas ·{" "}
          {(draft?.intent?.exclusions || []).reduce(
            (n: number, ring: any[]) => n + ring.length,
            0,
          )}
          /70 onboard vertices
        </strong>
        <p>
          {loaded?.bank
            ? `${loaded.bank.polygons.length} onboard areas read at ${new Date(loaded.bank.loaded_at * 1000).toLocaleTimeString()}. ${loaded.polygon && loaded.enabled ? "Polygon fence enabled." : "Polygon fence not enabled."}`
            : "Read the onboard areas before replacing them."}
        </p>
        {loaded?.bank?.error && <p className="error">{loaded.bank.error}</p>}
        <div className="button-row">
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                load(await api(`/vehicles/${vehicle.id}/fence/polygons`));
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Read onboard areas
          </button>
          <button
            className="primary"
            disabled={
              busy ||
              !control ||
              vehicle.armed ||
              !vehicle.owned ||
              !loaded?.bank ||
              !!loaded.bank.error
            }
            onClick={async () => {
              setBusy(true);
              setError("");
              setMessage("");
              try {
                const result = await api(
                  `/vehicles/${vehicle.id}/fence/polygons`,
                  "POST",
                  {
                    expected_revision: draft.revision,
                    expected_items: loaded.bank.items,
                    expected: loaded.values,
                    action: form.action,
                  },
                );
                load(result);
                setMessage(
                  "Exclusion areas uploaded and independently read back. Fence enable state verified.",
                );
                onChanged();
              } catch (e: any) {
                setError(e.message);
                setLoaded((old: any) => old && { ...old, bank: null });
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy
              ? "Working…"
              : draft?.intent?.exclusions?.length
                ? "Upload & enable areas"
                : "Clear onboard areas"}
          </button>
        </div>
        <p>
          This replaces the onboard exclusion bank with these draft areas,
          preserving circle/altitude settings. Reducing or clearing areas takes
          effect only when uploaded. Unsupported onboard fence types are
          protected from replacement.
        </p>
      </div>
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
              <span className="check-row">
                <input
                  type="checkbox"
                  checked={form.circle}
                  onChange={(e) => change({ circle: e.target.checked })}
                />
                Limit radius from home
              </span>
              Radius from home (m)
              <input
                type="number"
                min="30"
                max="10000"
                value={form.radius}
                disabled={!form.circle}
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
            Circle/ceiling edits preserve polygon and minimum-altitude
            selections and disable automatic enable-on-flight behavior. Report
            Only records a breach without a recovery action.
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
                    circle: form.circle,
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
            <button onClick={onClaim}>Enable vehicle controls for fence</button>
          )}
          {(!control || vehicle.armed) && (
            <p>Enable vehicle controls and disarm to apply fence changes.</p>
          )}
        </>
      )}
    </section>
  );
}
