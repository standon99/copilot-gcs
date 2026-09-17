# ArduPilot Safety Copilot

A local web ground station for **Copter, Plane and Rover**, with conversational mission planning, continuous Ollama assessments and a SITL failure laboratory.

## Open the app

```sh
cd /Users/stan/Documents/ardupilot_llm_copilot
./start.sh
```

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)**. The frontend, Python environment and three native simulator binaries are installed in this workspace.

1. Select a vehicle profile and click **Launch SITL**. Multiple profiles can run together.
2. In **Flight**, click **Claim control** to enable operator commands. Wait for GPS/estimator initialization before arming.
3. In **Mission**, click the map to add waypoints, drag them, or edit the table. Alternatively, enable **Allow requested draft edits** in chat and describe a route using coordinates or the current home.
4. Add an optional mission statement and numerical constraints. **Interpret statement with copilot** proposes constraints for your review; accepting them revises the draft.
5. **Check plan** runs numerical checks and requests a real model review. Resolve blockers, then use **Upload reviewed revision** in the copilot panel. Upload verifies readback and does not arm or launch.
6. Arm and start separately. Copter supports GUIDED takeoff; Plane uses a properly constructed takeoff mission; Rover has no aerial commands.
7. Use **Parameters** for staged writes, **Logs** for recordings/replay, and **SITL lab** for nominal/fault trials. Trials preserve the current vehicle phase.

The `examples/` folder contains checked rectangle missions for all three profiles at the Canberra SITL site; import one through the Mission workspace.

The model can edit a local draft when authorized. It cannot upload, arm, change a vehicle parameter or inject a failure. Deterministic checks and vehicle controls remain available during provider outages.

## Credentials and Git

Git was initialized before creating `.env`. The local key is in `.env`, ignored by Git, with permissions `0600`. `.env.example` contains placeholders only. Local commit/push hooks reject private environment files and the configured credential. The browser receives provider/model names and a configured/not-configured flag, never the key. No remote is configured and nothing has been pushed.

```sh
git check-ignore .env      # should print .env
git ls-files .env          # should print nothing
```

Provider configuration is read on server start:

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
