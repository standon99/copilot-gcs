<p align="center"><img src="web/public/icon.svg" width="88" height="88" alt="Copilot GCS icon" /></p>

# ArduPilot Safety Copilot

A web ground station for **Copter, Plane and Rover**, with an LLM copilot for planning missions, reviewing telemetry and testing failures in SITL.

![Actual Copter SITL flight workspace](docs/screenshots/flight.jpg)

## Features

- **Multiple vehicles:** up to six sessions, including multiple copters, on a satellite map.
- **Mission planning:** place waypoints, set altitude, configure a geofence, review and upload plans.
- **LLM interaction:** select a vehicle, describe changes, and let the copilot edit drafts or propose parameter updates.
- **Live monitoring:** mission-intent checks, configurable AI assessments, flight instruments and navigation cues.
- **Parameters and logs:** search/edit parameters, download logs and replay telemetry.
- **Failure testing:** simulate GPS, battery, RC, wind, sensor and motor faults without revealing the scenario to the monitor.
- **Flexible inference:** Ollama cloud or a local compatible endpoint; saved model, frequency and prompt settings.

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
2. **Launch SITL:** choose a vehicle and count. Wait for GPS and telemetry.
3. **Mission:** add waypoints and set altitude/reference, or enable **LLM interaction mode** and describe the plan.
4. **Claim control**, review, then upload. Arm and start separately. Use **Diagnostics / tests** for failure simulations.

## More

[Usage guide](docs/usage.md) · [Screenshots](docs/screenshots/README.md) · [Development](docs/development.md) · [Validation](docs/validation.md) · [Design](docs/design.md)

[MIT licensed](LICENSE). ArduPilot and other dependencies retain their own licenses. [Contribution rules](CLAUDE.md).
