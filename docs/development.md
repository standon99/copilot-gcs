# Development and data

[Project overview](../README.md)

## Development and verification

From the repository root, with Node 22+ on PATH:

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend tests scripts
.venv/bin/ruff format --check backend tests scripts
(cd web && npm test && npm run build)
git diff --check
```

The current suite contains **109 Python tests** and **8 frontend workflow tests**. The [validation record](validation.md) covers native Copter/Plane/Rover operations, real cloud inference, protocol readbacks, blind trial results and browser checks. Build success is not a substitute for flight or detection validation.

For an isolated runtime during development, use
`COPILOT_RUNTIME_DIR="$PWD/runtime/test-session" COPILOT_PORT=8091 ./start.sh`.
Settings, audit and sessions then stay separate from the normal installation.
The inference sandbox also denies that runtime directory. Use a directory under
ignored `runtime/`; do not commit runtime data. New runtimes use configured
defaults, including automatic monitoring, so save the intended test settings
before launching vehicles. Test runners below still need their base URL changed
when using a different port.

For explicit live tests, start the app in another terminal first. These scripts currently target **port 8080**:

```sh
# Disarmed parameter/mission/mode/log-list protocol checks:
.venv/bin/python scripts/integration.py

# Repeated trials on owned sessions; uses the configured inference provider:
.venv/bin/python scripts/benchmark.py --profiles copter plane rover \
  --scenarios nominal gps_loss --seeds 11 --duration 60

# These intentionally arm app-owned simulators:
.venv/bin/python scripts/flight-smoke.py
.venv/bin/python scripts/airborne-trial.py

# Local response stub: settings, scheduler, injection/cancel and pause:
.venv/bin/python scripts/settings-smoke.py
```

Reports and private experimental artifacts go to ignored `runtime/copilot/`. Read each runner before launching it: flight tests control their owned sessions, and model benchmarks consume inference requests. The older `requirements-installed.txt` is a historical terminal/SITL environment snapshot; use `requirements.txt`, `requirements-dev.txt` and `requirements-sitl.txt` for this application.

For frontend changes, rebuild `web/dist` and reload the page. Use the production same-origin server for normal verification; the Vite development server is not the documented authenticated application entry point. Vite may report a large MapLibre bundle warning even when the build succeeds.

## Data, credentials and repository layout

`.env` is local-only and ignored. Git hooks check staged files and local history for environment files and the configured credential. Enable them after cloning with `git config core.hooksPath .githooks`; they do not replace checking other secrets, recordings or screenshots before publication.

```sh
.venv/bin/python scripts/check-secrets.py --staged
.venv/bin/python scripts/check-secrets.py --all
```

| Path | Purpose |
| --- | --- |
| `backend/` | FastAPI, MAVLink gateways, telemetry, planning, inference, persistence and lab |
| `web/` | React/TypeScript UI, MapLibre map and flight instruments |
| `tests/`, `scripts/` | Automated checks, setup/build tools and live experiment runners |
| `examples/` | Checked example mission drafts for the three profiles |
| `docs/` | Design, feasibility, operating boundaries, evaluation, validation and real UI screenshots |
| `runtime/copilot/` | Ignored settings, SQLite audit, simulator state, recordings, predictions and private trial truth |
| `runtime/metadata/` | Ignored parameter metadata regenerated from the pinned source |
| `ardupilot/`, `.venv/`, `.tools/`, `web/dist/`, `node_modules/` | Ignored source/build/runtime dependencies |
| `CLAUDE.md` | Development rules: commit every completed iteration and keep README/docs current |

Runtime logs and recordings remain on this computer until you deliberately export/share them. Inference sends the selected context to the configured endpoint; cloud inference therefore sends that permitted context to the cloud provider. The backend does not send the private key to the browser or include it in prompts. Saved prompts/preferences persist; pending proposals and active live sessions are not restored as executable work after restart. Avoid deleting the runtime tree if you want to preserve settings or experiment evidence.

## Contributing and iteration discipline

Read [CLAUDE.md](../CLAUDE.md). Every completed iteration must be committed, with relevant README/docs updates in the same commit. Setup instructions, limitations, validation claims and affected screenshots must continue to match the implementation. Run appropriate checks, inspect staged content and keep credentials/runtime data out of Git. Push only when authorized.
