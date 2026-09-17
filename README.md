# ArduPilot Safety Copilot

A local web ground station for **Copter, Plane and Rover**, with conversational mission planning, continuous Ollama assessments and a SITL failure laboratory.

## Open the app

```sh
cd /Users/stan/Documents/ardupilot_llm_copilot
./start.sh
```

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)**. The frontend, Python environment and three native simulator binaries are installed in this workspace.

1. Select a vehicle profile, choose a count (for example **copter → 2×**), and click **Launch SITL**. Up to six independent sessions can run together, including multiple copters. New sessions start at separate nearby positions. The selected vehicle is teal; other vehicles are amber. Use **Locate vehicle** or **Fit all** on the map.
2. In **Flight**, click **Claim control** to enable operator commands. Wait for GPS/estimator initialization before arming.
3. In **Mission**, click the map to add waypoints, drag them, or edit the table. Set **Altitude m** and choose **Relative home** or **AMSL**; press Enter or leave the field to save. Alternatively, enable **Allow requested draft edits** in chat and describe a route using coordinates or the current home.
4. Add an optional mission statement and numerical constraints. **Interpret statement with copilot** proposes constraints for your review; accepting them revises the draft.
5. **Check plan** runs numerical checks and requests a real model review. Resolve blockers, then use **Upload reviewed revision** in the copilot panel. Upload verifies readback and does not arm or launch.
6. Arm and start separately. Copter supports GUIDED takeoff; Plane uses a properly constructed takeoff mission; Rover has no aerial commands.
7. Use **Parameters** for staged writes, **Logs** for recordings/replay, and **Diagnostics / tests** for nominal/fault trials. Claim control, choose a failure and duration, then run the trial. Trials preserve the current vehicle phase; cancellation restores injected parameters where possible. Automatic assessments must be enabled to run a monitored trial, and the pane warns if the assessment interval exceeds the observation window.

## LLM interaction mode and flight instruments

Turn on **LLM interaction mode** in the main bar, check the allowed vehicle targets, then use the copilot chat. Include the copter's displayed ID when different vehicles need different instructions. For example: “For copter ab12cd, add a waypoint at -35.3623, 149.16523 at 30 m above home and set LOG_DISARMED to 1. Leave copter ef34ab unchanged.”

Waypoint requests revise local drafts and retain before/after inspection and undo. Parameter requests produce cards with exact vehicle, old/new value and reason; **Claim control → Apply to [ID]** sends the reviewed values to a disarmed owned simulator and verifies readback. Proposals expire after five minutes and are invalid after a reboot or conflicting parameter change. Failed batches stop and preserve the journal of earlier writes; they do not promise automatic rollback. An ambiguous request should prompt a question. Always inspect the actual command/units in the draft: a model's prose can disagree with its structured edit.

The interaction toggle starts off on each page load. Its target checkboxes remain explicit when switching vehicle tabs. **Settings → System prompt → Multi-vehicle interaction** edits its persisted prompt independently of ordinary review chat and automatic monitoring. Mission upload, arming, takeoff and mission start remain separate controls.

**Flight** includes an artificial horizon with roll/pitch, heading, altitude above home and AMSL, ground/air speed, and climb rate. Missing or stale readings are blanked; attitude becomes unavailable after three seconds without fresh data. The instrument follows the selected vehicle.

While navigating, the map shows a gold stick and target ring from fresh autopilot position-target telemetry, falling back to the verified uploaded mission item in AUTO. The orange diamond is a **projected navigation-bearing cue**, placed 5–50 m ahead for readability; it is not a claim to display the autopilot's internal look-ahead point. Freshness, arming and navigation-mode checks hide unavailable cues. Both work without LLM requests. Telemetry fields follow the [MAVLink common message definitions](https://mavlink.io/en/messages/common.html#POSITION_TARGET_GLOBAL_INT).

## Geofence

In **Mission → Onboard geofence**, claim control while disarmed, select **Enable onboard fence**, enter the circle radius and (for aerial vehicles) maximum altitude above home, choose the breach action, then **Apply onboard fence**. Each setting is independently read back. The saved enabled circle appears as an amber dashed boundary; zoom out if necessary. The ceiling datum is explicitly set to above home in the firmware.

This editor replaces fence-type selection with a home-centred circle and optional ceiling; it does not upload polygon fences. It disables automatic fence-enable behavior so the selected enabled/disabled state is explicit. Existing mission-intent exclusion polygons remain separate advisory constraints and are not onboard geofences. See [ArduPilot's fence documentation](https://ardupilot.org/copter/docs/common-geofencing-landing-page.html) for vehicle-specific behavior.

## Inference settings

**Settings** is available before connecting any vehicle. Configure the automatic assessment interval (10 seconds to 24 hours), pause automatic assessments globally, select a model, set an OpenAI-compatible API base URL, and edit the monitor/planner/intent/interaction system prompts. **Load models** queries the endpoint's model list; **Test connection** makes one inference request with the form values. **Save settings** activates and persists changes without a restart.

For a local Ollama instance, use `http://localhost:11434/v1` and the name of an installed model. Its process must already be running. The backend never sends the cloud credential to the local or alternate provider. [Ollama API compatibility](https://docs.ollama.com/api/openai-compatibility)

Preferences are stored in ignored `runtime/copilot/settings.json`, preserved by the installation/rebuild script. They override initial `.env` defaults after the first save. Prompt reset buttons restore the factory text into the editor; save to apply. Keep the JSON contracts when editing prompts. During active blinded trials, inference settings are locked to preserve the experimental configuration.

The current installation is left **paused globally with a five-minute interval** to avoid ongoing usage. Enable automatic assessments and save when ready. The interval is measured after each completed assessment; each assessment may make one bounded repair request. Manual chat/tests also consume requests. Numerical telemetry checks continue while inference is paused.

The `examples/` folder contains checked rectangle missions for all three profiles at the Canberra SITL site; import one through the Mission workspace.

The model can edit a local draft when authorized and propose parameter changes in interaction mode. Applying a parameter proposal, uploading, arming and starting remain explicit operator actions. The model cannot inject failures. Deterministic checks and vehicle controls remain available during provider outages.

## Credentials and Git

Git was initialized before creating `.env`. The local key is in `.env`, ignored by Git, with permissions `0600`. `.env.example` contains placeholders only. Local commit/push hooks reject private environment files and the configured credential. The browser receives provider/model names and a configured/not-configured flag, never the key. No remote is configured and nothing has been pushed.

```sh
git check-ignore .env      # should print .env
git ls-files .env          # should print nothing
```

Initial provider defaults and the private credential are read on server start; saved Settings preferences override the non-secret defaults:

```dotenv
OLLAMA_API_KEY=your-key
OLLAMA_BASE_URL=https://ollama.com/v1
OLLAMA_MODEL=gpt-oss:120b
MONITOR_INTERVAL=20
INFERENCE_TIMEOUT=45
```

Keep the real key exclusively in the local `.env`, never in source files, frontend environment variables, command-line arguments, screenshots or commit messages.

## Install or rebuild the application

Python 3.13 and Node 22+ are used here. This installation has a repository-local Node 22 under ignored `.tools/` because the machine's default Node is older.

```sh
./scripts/setup.sh
./start.sh
```

`setup.sh` installs the pinned Python dependencies, regenerates parameter metadata from the local firmware source, installs frontend dependencies from the lockfile, and builds the frontend. It preserves an existing `.env`.

To build just the frontend on this machine:

```sh
export PATH="$PWD/.tools/node_modules/node/bin:/usr/local/bin:$PATH"
cd web
npm ci
npm run build
```

The production frontend is served by FastAPI. Use the production build for the strict same-origin session policy. The backend is intended to stay on loopback.

## Simulator build

The independently tracked `ardupilot/` checkout is pinned to commit `dbe792162d06cab66c3475fd5556bf7a120f119e` (tag `Copter-4.7.1`). Copter, Plane and Rover report 4.7.1 at this commit. Their source is unchanged.

```sh
./scripts/build-sitl.sh
.venv/bin/python scripts/generate-metadata.py
```

The macOS build uses `--disable-networking` to avoid an optional embedded lwIP build problem; ordinary SITL MAVLink sockets still work. The existing `start-sitl.sh` and `start-mavproxy.sh` remain available for the earlier terminal-only workflow. The web app launches isolated instances and does not use `sim_vehicle.py` process cleanup.

## Tests and experiments

```sh
.venv/bin/python -m pytest -q
# Start the app in another terminal first:
.venv/bin/python scripts/integration.py
.venv/bin/python scripts/benchmark.py --scenarios nominal gps_loss --duration 45
# These intentionally arm owned SIMULATORS and stop them afterward:
.venv/bin/python scripts/flight-smoke.py
.venv/bin/python scripts/airborne-trial.py
# Local stub only: settings, scheduler, GPS injection/cancel, and pause verification:
.venv/bin/python scripts/settings-smoke.py
```

The integration script launches missing profiles and performs real parameter, mission, mode and log-list protocol checks. It does not arm by default. The benchmark operates only on owned simulator sessions and preserves their current state. Reports go to ignored `runtime/copilot/`. Use `--profiles`, `--seeds` and `--scenarios` to choose repeated tests. The CLI waits for a preceding integration process's write lease to expire.

The blind telemetry track excludes simulator parameters/messages, diagnostic strings, rule labels, injection events and scenario identity. On macOS, the inference subprocess is also denied access to private files and loopback network services. Prediction records are locked and hashed before scenario results are revealed. Scores are labeled lexical screening and require human adjudication.

## Repository

- `backend/`: FastAPI, independent MAVLink gateway processes, protocol services, planning/intent checks, inference worker, storage and lab.
- `web/`: React/TypeScript and MapLibre application.
- `tests/`, `scripts/`: tests, installation, integration and experiment runners.
- `runtime/copilot/`: simulator state, recordings, inference evidence, SQLite and private trial artifacts; ignored.
- `runtime/metadata/`: firmware-derived parameter descriptions; ignored and reproducible.
- `ardupilot/`, `.venv/`, `.tools/`: local dependencies; ignored by this repository.

Read the [implementation and operating boundaries](docs/implementation.md), [validation results](docs/validation.md), [system design](docs/design.md), [feasibility analysis](docs/feasibility.md), and [evaluation protocol](docs/sitl-evaluation.md).

This is a functional **SITL research application**. Physical flight, terrain/obstacle clearance, full GCS parity and a validated safety-detection rate are outside the evidence from these tests.
