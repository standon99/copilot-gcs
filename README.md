<p align="center"><img src="web/public/icon.svg" width="88" height="88" alt="Copilot GCS icon" /></p>

# Copilot GCS

**An AI-enabled ground control station for everyday drone tasks.** Describe a waypoint flight or inspection, refine the mission with Copilot, review it on the map, then upload and operate it. Built for ArduPilot **Copter, Plane and Rover**.

![Copilot GCS mission planning with a real simulated vehicle](docs/screenshots/mission-planning.jpg)

## Features

- **AI planning:** describe waypoint flights or point inspections; refine drafts and propose parameter changes through conversation.
- **Guided workflow:** describe → review → upload → operate, with explicit vehicle actions.
- **Flight workspace:** satellite map, waypoint altitudes, geofences, live instruments, parameters, logs and replay.
- **Multiple vehicles:** select Copilot's targets and run up to six simulations together.
- **Your model and usage:** Ollama cloud or a local endpoint; saved model, prompts and assessment frequency.
- **Live insights and diagnostics:** check telemetry against mission intent and rehearse failure scenarios in simulation.

Vehicle writes currently support **app-owned SITL only**. Uploads, parameter application and flight commands require explicit operator actions.

## Setup

Tested on macOS Apple Silicon. Requires **Python 3.13, Node 22+, Git and a C/C++ compiler**. On macOS, install Xcode Command Line Tools and Homebrew first. [Full setup and troubleshooting](docs/setup.md).

```sh
brew install git python@3.13 node@22 gawk
export PATH="$(brew --prefix node@22)/bin:$PATH"

git clone https://github.com/standon99/copilot-gcs.git
cd copilot-gcs

git clone --branch Copter-4.7.1 --depth 1 \
  https://github.com/ArduPilot/ardupilot.git ardupilot
git -C ardupilot checkout --detach dbe792162d06cab66c3475fd5556bf7a120f119e
git -C ardupilot submodule update --init --recursive

python3.13 -m venv .venv
./scripts/setup.sh
./scripts/build-sitl.sh
git config core.hooksPath .githooks
```

Setup creates an ignored `.env`. Add your cloud key there, or configure a running local model in **Settings**:

```dotenv
OLLAMA_API_KEY=your-key
OLLAMA_BASE_URL=https://ollama.com/v1
OLLAMA_MODEL=gpt-oss:120b
MONITOR_INTERVAL=300
```

Keep the key out of Git. For local Ollama, use `http://localhost:11434/v1` and an installed model ID; no cloud key is sent to local endpoints.

## Run

```sh
./start.sh
```

Open **http://127.0.0.1:8080**. For another port: `COPILOT_PORT=8091 ./start.sh`. Stop with **Ctrl+C**.

1. **Settings:** choose the model, assessment interval and automatic-monitoring state; save.
2. Describe a task on the start page, choose a vehicle and **Continue in simulation**. Wait for home and telemetry.
3. Send the brief to **Copilot**, or add waypoints in **Plan**. Refine and review the draft.
4. **Claim control**, upload, then open **Operate** to arm and start separately. **Diagnostics** contains failure simulations.

## More

[Usage guide](docs/usage.md) · [Screenshots](docs/screenshots/README.md) · [Development](docs/development.md) · [Validation](docs/validation.md) · [Product](docs/product.md)

[MIT licensed](LICENSE). ArduPilot and other dependencies retain their own licenses. [Contribution rules](CLAUDE.md).
