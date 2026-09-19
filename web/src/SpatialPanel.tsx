import React from "react";

export function SpatialPanel({
  spatial,
  busy,
  error,
  trace,
  onLoad,
  onSelect,
  onTrace,
  onSave,
  onCancel,
  onUndo,
  onClose,
}: any) {
  return (
    <section className="spatial-panel" aria-label="Map features">
      <div className="spatial-panel-title">
        <strong>Map features</strong>
        <button onClick={onClose}>Close</button>
      </div>
      <div className="spatial-panel-actions">
        <button onClick={onLoad} disabled={busy || !!trace}>
          {busy ? "Loading…" : "Load nearby"}
        </button>
        <button onClick={() => onTrace("road")} disabled={busy || !!trace}>
          Trace road
        </button>
        <button onClick={() => onTrace("airstrip")} disabled={busy || !!trace}>
          Trace airstrip
        </button>
      </div>
      {trace ? (
        <div className="feature-tracing">
          <span>
            {trace.kind === "road"
              ? "Click along the road"
              : "Click around the airstrip"}{" "}
            · {trace.points.length} points
          </span>
          <button onClick={onUndo} disabled={!trace.points.length}>
            Undo point
          </button>
          <button
            onClick={onSave}
            disabled={
              busy || trace.points.length < (trace.kind === "road" ? 2 : 3)
            }
          >
            Save trace
          </button>
          <button onClick={onCancel}>Cancel</button>
        </div>
      ) : (
        <small>
          Select a feature here or click its line on the map to reference it in
          chat.
        </small>
      )}
      {error && <p role="alert">{error}</p>}
      <div className="spatial-feature-list">
        {(spatial?.features || []).map((f: any) => (
          <label key={f.id}>
            <input
              type="checkbox"
              checked={spatial.selected_ids.includes(f.id)}
              disabled={busy || !!trace}
              onChange={() => onSelect(f.id)}
            />
            <span>
              <strong>{f.label}</strong>{" "}
              <small>
                {f.kind} · {f.id}
              </small>
              <small>
                {f.source} · {f.uncertainty}
              </small>
            </span>
          </label>
        ))}
      </div>
      {!!spatial?.features?.length && (
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          Map data © OpenStreetMap contributors
        </a>
      )}
    </section>
  );
}
