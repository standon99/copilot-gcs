# Setup and troubleshooting

[Project overview](../README.md)

## Setup from a fresh clone

### Requirements and platform support

- **Validated host:** macOS on Apple Silicon, Python **3.13**, Node.js **22+**, npm and a current browser with WebGL support.
- **Native tools:** Git and a working C/C++ compiler. On macOS, install Xcode Command Line Tools and Homebrew. The web GCS does not require MAVProxy.
- **SITL:** build the three native binaries from the pinned ArduPilot checkout below. The source checkout and binaries are not included in this Git repository.
- **Inference:** an Ollama cloud account/key, or an already-running local OpenAI-compatible model endpoint. You can use the GCS without inference; chat and automatic assessments require a working provider.
- **Network/storage:** initial dependency/source downloads, build space, and network access to the selected imagery and inference providers. Runtime recordings consume additional disk space.

Linux is a portability path, not a platform validated by this repository's current evidence. Install a Python 3.13 interpreter and Node 22+, follow [ArduPilot's Linux prerequisites](https://ardupilot.org/dev/docs/building-setup-linux.html), then use the common clone/build steps below. Native Windows is not supported by these shell scripts; a WSL2/Linux setup requires separate validation. See also [ArduPilot's macOS setup reference](https://ardupilot.org/dev/docs/building-setup-mac.html).

### 1. Install host tools on macOS

Install Xcode Command Line Tools if they are not already present, and complete the installer:

```sh
xcode-select --install
```

With [Homebrew](https://brew.sh/) installed:

```sh
brew install git python@3.13 node@22 gawk
export PATH="$(brew --prefix node@22)/bin:$PATH"
python3.13 --version
node --version
npm --version
```

Keep Node 22+ on your PATH in subsequent terminals. If you already have suitable tools, use those instead.

### 2. Clone the app and the pinned simulator source

```sh
git clone https://github.com/standon99/copilot-gcs.git
cd copilot-gcs

git clone --branch Copter-4.7.1 --depth 1 \
  https://github.com/ArduPilot/ardupilot.git ardupilot
git -C ardupilot checkout --detach dbe792162d06cab66c3475fd5556bf7a120f119e
git -C ardupilot submodule update --init --recursive
git -C ardupilot rev-parse HEAD
```

The final command must report `dbe792162d06cab66c3475fd5556bf7a120f119e`. This commit supplies all three profiles; the native binaries report 4.7.1. Keep the revision pinned: parameter metadata and failure adapters are tied to it. `ardupilot/` is an independent, ignored checkout, not a submodule of this application repository.

### 3. Create the Python environment and install/build the app

Run from the application repository root:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
./scripts/setup.sh
.venv/bin/python -m pip install -r requirements-dev.txt

git config core.hooksPath .githooks
```

`setup.sh` installs the pinned application dependencies. When the upstream checkout is present, it also installs `requirements-sitl.txt` and generates Copter/Plane/Rover parameter metadata. It creates a private `.env` from the empty-key example only if one does not exist, then runs `npm ci` and the production frontend build. Existing `.env` and saved settings are preserved. Development dependencies add Ruff for the documented checks.

If the machine's default Node is too old and you prefer a project-local runtime:

```sh
npm install --prefix .tools --no-save node@22
export PATH="$PWD/.tools/node_modules/node/bin:$PATH"
./scripts/setup.sh
```

The setup script automatically prefers this ignored local Node installation when present.

### 4. Build Copter, Plane and Rover SITL

```sh
./scripts/build-sitl.sh
ls ardupilot/build/sitl/bin/arducopter \
   ardupilot/build/sitl/bin/arduplane \
   ardupilot/build/sitl/bin/ardurover
```

The build wrapper uses the project virtual environment, native SITL configuration and four parallel jobs. It disables optional embedded networking to avoid the lwIP build problem encountered on the validated Mac; ordinary SITL MAVLink sockets still work. It does not download missing source/submodules. Complete step 2 first.

If metadata needs regeneration after rebuilding the same pinned source:

```sh
.venv/bin/python scripts/generate-metadata.py
```

### 5. Configure inference without exposing credentials

Edit the local `.env` in your editor. For cloud inference, enter your own key locally:

```dotenv
OLLAMA_API_KEY=your-own-key
OLLAMA_BASE_URL=https://ollama.com/v1
OLLAMA_MODEL=gpt-oss:120b
COPILOT_PORT=8080
MONITOR_INTERVAL=300
INFERENCE_TIMEOUT=45
```

The model name above was used in the recorded tests; available models depend on the provider/account. Do not put the key in Git, browser/frontend variables, shell command arguments, screenshots, issues or chat. Protect the file and check the ignore rule:

```sh
chmod 600 .env
git check-ignore .env
git ls-files .env
```

The first Git command should print `.env`; the second should print nothing. The key is loaded by the backend at startup. Saved non-secret preferences later override `.env` model, endpoint, cadence and timeout defaults.

For local Ollama, leave the key empty, use `OLLAMA_BASE_URL=http://localhost:11434/v1` and set `OLLAMA_MODEL` to an installed model ID. Alternatively, select the local endpoint later in Settings. Start Ollama separately; this application does not install, download or host models. See [Ollama's API compatibility documentation](https://docs.ollama.com/api/openai-compatibility).

### 6. Start and verify

```sh
./start.sh
```

Open **[http://127.0.0.1:8080](http://127.0.0.1:8080)**. FastAPI serves the production frontend and same-origin API; a separate frontend development server is not needed.

1. Open **Settings** before launching a vehicle. Set the model/endpoint, choose an assessment interval, and enable or pause automatic assessments. Save.
2. **Load models** checks model discovery; **Test connection (1 request)** makes an explicit inference request. Both use the values currently in the form. Save to activate them for normal requests.
3. Select **copter → 1× → Launch SITL**. Wait for heartbeat, GPS, home and parameter discovery; startup checks may take tens of seconds.
4. Confirm the teal vehicle marker, live telemetry and flight instrument appear. No arming is needed for this check.
5. Optionally repeat with Plane/Rover or use **2×** to launch two copters.

A fresh settings store enables automatic assessments by default, with the initial interval read from `.env` (20 seconds in `.env.example`). Choose the desired usage policy in Settings before launching sessions. The screenshots show one installation paused with a five-minute interval; that saved preference is not shipped in Git.

The server binds to loopback (`127.0.0.1`). `COPILOT_HOST` in the example file is not used to change that binding. To use another local port:

```sh
COPILOT_PORT=8091 ./start.sh
```

Open the matching URL. Stop with **Ctrl+C**; shutdown stops app-owned simulators and gateway processes. **Settings → Stop & disconnect** stops an individual selected session. Closing a browser tab alone does not stop the backend or its ongoing assessments.

## Troubleshooting

| Symptom | Check / resolution |
| --- | --- |
| `SITL binary missing` | Complete the upstream checkout/submodules and `./scripts/build-sitl.sh`; confirm all three binary paths above |
| Missing waf/submodule files | Run `git -C ardupilot submodule update --init --recursive` at the pinned revision |
| Missing build/metadata Python module | Install `requirements-sitl.txt` into `.venv`, then regenerate metadata; do not accidentally use a different Python environment |
| Node version or frontend build error | Put Node 22+ on PATH or use the ignored local Node option, then rerun setup |
| Blank/stale map position | Wait for position/GPS telemetry, verify heartbeat age, then use Locate/Fit all; launch slots differ from each other |
| Basemap unavailable | Check internet access to the imagery provider; coordinates, markers and draft editing do not depend on imagery |
| Arm/mode rejected | Inspect native prearm/status messages, GPS/estimator readiness and the selected profile; keep checks enabled |
| `Claim control` / conflicting lease | Select the correct vehicle and claim it; another browser may hold the renewable 30-second lease |
| Model unavailable / malformed JSON | Check model ID, endpoint and timeout; use Test connection. No inference failure should be interpreted as “all clear” |
| `.env` model changes seem ignored | Saved Settings override non-secret initial defaults; edit/save in the UI. Key changes require a server restart |
| Trial disabled / no assessments | Enable global/per-vehicle monitoring and shorten the interval relative to trial duration; inspect provider availability |
| Port already occupied | Stop the earlier server or use `COPILOT_PORT=8091 ./start.sh` and the matching URL |
| Pending proposal rejected | Check expiry, target, reboot, disarmed state and old value; request a fresh proposal instead of retrying blindly |
