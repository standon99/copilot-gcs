import React, { useEffect, useState } from "react";
import { api } from "./api";

export function SettingsPanel({
  config,
  vehicles,
  current,
  onSaved,
  onConnected,
  onStopped,
}: any) {
  const [form, setForm] = useState<any>(null),
    [saved, setSaved] = useState<any>(null);
  const [defaults, setDefaults] = useState<any>({}),
    [models, setModels] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("monitor"),
    [busy, setBusy] = useState("");
  const [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const [endpoint, setEndpoint] = useState("tcp:127.0.0.1:5760"),
    [profile, setProfile] = useState("copter");
  const load = (data: any) => {
    setForm(data.preferences);
    setSaved(data.preferences);
    setDefaults(data.defaults);
  };
  const run = async (label: string, work: () => Promise<void>) => {
    setBusy(label);
    setError("");
    setMessage("");
    try {
      await work();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };
  useEffect(() => {
    void run("load", async () => load(await api("/settings")));
  }, []);
  if (!form)
    return (
      <div className="page">
        <h1>Settings</h1>
        <p>{error || "Loading saved preferences…"}</p>
      </div>
    );
  const change = (patch: any) => setForm({ ...form, ...patch });
  const dirty = JSON.stringify(saved) !== JSON.stringify(form);
  const activeCount = vehicles.filter((v: any) => v.monitor_enabled).length;
  return (
    <div className="page settings-page">
      <span className="eyebrow">INSTALLATION PREFERENCES</span>
      <h1>Inference & connections</h1>
      <p>
        Saved settings apply immediately and survive server restarts and
        application rebuilds.
      </p>
      {error && (
        <div className="banner error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="banner notice" role="status">
          {message}
        </div>
      )}
      <div className="settings-grid">
        <section>
          <h2>Automatic assessments</h2>
          <label className="check-row">
            <input
              type="checkbox"
              checked={form.monitor_enabled}
              onChange={(e) => change({ monitor_enabled: e.target.checked })}
            />
            Enable continuous assessments for all sessions
          </label>
          <label>
            Wait between completed assessments (seconds)
            <input
              type="number"
              min="10"
              max="86400"
              value={form.monitor_interval}
              onChange={(e) =>
                change({ monitor_interval: Number(e.target.value) })
              }
            />
          </label>
          <div className="button-row">
            {[30, 60, 300, 900].map((n) => (
              <button key={n} onClick={() => change({ monitor_interval: n })}>
                {n < 60 ? `${n}s` : `${n / 60} min`}
              </button>
            ))}
          </div>
          <p>
            {form.monitor_enabled
              ? `At most about ${Math.ceil(3600 / Math.max(10, form.monitor_interval))} assessments per hour per enabled vehicle; ${activeCount} currently enabled sessions. Each assessment can use one repair request.`
              : "Automatic model calls will be paused globally. Chat and connection tests remain available when you request them."}{" "}
            Numerical telemetry checks continue.
          </p>
          <label>
            Inference timeout (seconds)
            <input
              type="number"
              min="10"
              max="120"
              value={form.inference_timeout}
              onChange={(e) =>
                change({ inference_timeout: Number(e.target.value) })
              }
            />
          </label>
        </section>
        <section>
          <h2>Model & endpoint</h2>
          <div className="button-row">
            <button
              onClick={() => {
                change({ base_url: "https://ollama.com/v1" });
                setModels([]);
              }}
            >
              Ollama cloud
            </button>
            <button
              onClick={() => {
                change({ base_url: "http://localhost:11434/v1" });
                setModels([]);
              }}
            >
              Local Ollama
            </button>
          </div>
          <label>
            OpenAI-compatible API base URL
            <input
              type="url"
              value={form.base_url}
              onChange={(e) => {
                change({ base_url: e.target.value });
                setModels([]);
              }}
              placeholder="http://localhost:11434/v1"
            />
          </label>
          <label>
            Model ID
            <input
              list="available-models"
              value={form.model}
              onChange={(e) => change({ model: e.target.value })}
              placeholder="Model installed on your endpoint"
            />
          </label>
          <datalist id="available-models">
            {models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
          {models.length > 0 && (
            <label>
              Available models
              <select
                value={models.includes(form.model) ? form.model : ""}
                onChange={(e) => change({ model: e.target.value })}
              >
                <option value="" disabled>
                  Select a model
                </option>
                {models.map((m) => (
                  <option key={m}>{m}</option>
                ))}
              </select>
            </label>
          )}
          <div className="button-row">
            <button
              disabled={!!busy}
              onClick={() =>
                run("models", async () => {
                  const data = await api("/settings/models", "POST", form);
                  setModels(data.models);
                  setMessage(
                    `Found ${data.models.length} models at this endpoint.`,
                  );
                })
              }
            >
              {busy === "models" ? "Loading…" : "Load models"}
            </button>
            <button
              disabled={!!busy}
              onClick={() =>
                run("test", async () => {
                  const r = await api("/settings/test", "POST", form);
                  setMessage(
                    `Connection passed: ${r.model} responded in ${r.latency_s}s. This tested the form values; save to use them.`,
                  );
                })
              }
            >
              {busy === "test" ? "Testing…" : "Test connection (1 request)"}
            </button>
          </div>
          <p>
            The cloud key stays in the backend .env and is sent only to its
            configured HTTPS provider. Local and other endpoints receive no
            cloud key. Local Ollama needs no key; include /v1 in the URL. The
            application does not start or download local models.
          </p>
        </section>
      </div>
      <section className="prompt-editor">
        <h2>System prompts</h2>
        <label>
          Prompt to edit
          <select value={prompt} onChange={(e) => setPrompt(e.target.value)}>
            <option value="monitor">Continuous assessment</option>
            <option value="planner">Mission planning & review</option>
            <option value="intent">Mission statement interpretation</option>
            <option value="interaction">Multi-vehicle interaction</option>
          </select>
        </label>
        <p>
          Keep the JSON response contract and evidence requirements. Validation
          and vehicle-write restrictions remain enforced by the application. For
          blinded tests, avoid scenario names or expected answers in your
          prompts.
        </p>
        <textarea
          aria-label="System prompt"
          spellCheck={false}
          value={form.prompts[prompt]}
          onChange={(e) =>
            change({ prompts: { ...form.prompts, [prompt]: e.target.value } })
          }
        />
        <button
          onClick={() =>
            change({ prompts: { ...form.prompts, [prompt]: defaults[prompt] } })
          }
        >
          Restore this prompt to default
        </button>
      </section>
      <div className="settings-save">
        <span>
          {dirty ? "Unsaved changes" : `Saved revision ${form.revision}`}
        </span>
        <button
          disabled={!!busy}
          onClick={() =>
            run("reload", async () => load(await api("/settings")))
          }
        >
          Reload saved
        </button>
        <button
          className="primary"
          disabled={!!busy || !dirty}
          onClick={() =>
            run("save", async () => {
              load(await api("/settings", "PUT", form));
              await onSaved();
              setMessage(
                "Settings saved on this installation. New assessments use these preferences.",
              );
            })
          }
        >
          {busy === "save" ? "Saving…" : "Save settings"}
        </button>
      </div>
      <div className="settings-grid">
        <section>
          <h2>Read-only MAVLink connection</h2>
          <label>
            Endpoint
            <input
              value={endpoint}
              onChange={(e) => setEndpoint(e.target.value)}
            />
          </label>
          <label>
            Profile
            <select
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
            >
              {Object.keys(config.profiles).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <button
            disabled={!!busy}
            onClick={() =>
              run("connect", async () =>
                onConnected(
                  await api("/connections", "POST", { profile, endpoint }),
                ),
              )
            }
          >
            Connect local transport
          </button>
        </section>
        <section>
          <h2>Selected session</h2>
          {current ? (
            <>
              <p>
                {current.name} · {current.endpoint}
              </p>
              <p>
                {current.armed ? "Armed" : "Disarmed"} ·{" "}
                {current.recording ? "Recording" : "Recording stopped"}
              </p>
              <button
                className="danger"
                disabled={!!busy}
                onClick={() =>
                  run("stop", async () => {
                    await api(`/vehicles/${current.id}`, "DELETE");
                    onStopped();
                  })
                }
              >
                Stop & disconnect {current.profile}
              </button>
            </>
          ) : (
            <p>
              No vehicle selected. Inference settings can be edited before
              launching a simulator.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
