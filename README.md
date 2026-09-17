# ArduPilot SITL on this Mac

Native Apple Silicon installation of ArduCopter **4.7.1** (tag `Copter-4.7.1`,
commit `dbe792162d06cab66c3475fd5556bf7a120f119e`).

## Web ground station and LLM copilot design

Draft planning documents for a browser ground station with conversational mission
drafting/review, continuous LLM monitoring, optional mission-intent/operator-error
checks, and blind SITL failure evaluation, supporting Copter, Plane, and Rover
from the first release:

- [Feasibility, tradeoffs, and effort estimate](docs/feasibility.md)
- [System design](docs/design.md)
- [SITL scenarios and blind evaluation protocol](docs/sitl-evaluation.md)

These documents describe proposed work. The installation below currently builds
and verifies only Copter; the web application and LLM benchmark are not yet built.

## Start

In a Terminal:

```bash
cd /Users/stan/Documents/ardupilot_llm_copilot
./start-sitl.sh
```

SITL waits for a ground station connection. In a second Terminal:

```bash
cd /Users/stan/Documents/ardupilot_llm_copilot
./start-mavproxy.sh
```

MAVProxy provides a text command prompt. Type `status` to inspect telemetry.
Press **Ctrl+C** in each Terminal to stop its process. If MAVProxy keeps its
prompt open, type `set requireexit True` and then `exit`.

The default vehicle is a simulated quadcopter at ArduPilot's Canberra test
location. This setup does not connect to a physical flight controller.

SITL listens on TCP port **5760**. MAVProxy connects through `127.0.0.1` and
forwards telemetry to UDP **14550** on this Mac for a compatible ground station.
Alternatively, a ground station can connect directly to TCP `127.0.0.1:5760`
instead of running MAVProxy. SITL's TCP listener uses all network interfaces.
If a port is already in use, stop only the instance you started; these launchers
do not stop other programs for you.

The graphical MAVProxy map/console (wxPython), Gazebo, and a separate graphical
ground station are not included. The terminal ground station is installed.
The optional terrain downloader is not loaded automatically because its remote
file-list download failed during setup; basic SITL operation works without it.

## Files and isolation

- `ardupilot/`: shallow source checkout, required SITL submodules and native build.
- `.venv/`: this installation's Python packages.
- `runtime/sitl/`: simulator parameters, logs and state, preserved between runs.
- `runtime/mavproxy/`: ground station telemetry logs.
- `runtime/.mavproxy/`: local MAVProxy configuration/cache.
- `requirements-installed.txt`: installed Python package versions.
- `configure.log`, `build.log`: build output.

No global packages, Homebrew packages or shell startup files were changed.
The launchers execute only this installation's programs. They do not use
`sim_vehicle.py`'s cleanup routine, which can terminate other simulator processes.
MAVProxy's launcher omits HOME only for that child process and supplies a local
LOCALAPPDATA path so MAVProxy uses local configuration instead of your home
directory's configuration.

## Rebuild

```bash
cd /Users/stan/Documents/ardupilot_llm_copilot
source .venv/bin/activate
cd ardupilot
CCACHE_DISABLE=1 ./waf configure --board sitl --no-submodule-update --disable-networking
CCACHE_DISABLE=1 ./waf copter -j 4
```

The supported `--disable-networking` option avoids an optional embedded lwIP
networking build problem with this macOS/Clang setup. Normal SITL MAVLink TCP/UDP
connections remain available. The simulator's source code was not modified.
Hardware cross-compilers and submodules unrelated to this SITL build were omitted.

## Verification

On 2026-09-17, the native arm64 build completed successfully and the final launch
scripts passed a live startup check: MAVProxy connected to SITL over TCP and
forwarded heartbeat, attitude and position messages over UDP. The simulated
vehicle stayed disarmed. Both test processes were stopped afterward.
See `verification.json`, `verify-sitl-final.log` and `verify-mavproxy-final.log`.
Python's `pip check` also passed, and the upstream source checkout is unchanged.

The installation occupied approximately 1.3 GB (1.2 GiB) after verification.

Official references: [macOS setup](https://ardupilot.org/dev/docs/building-setup-mac.html)
and [SITL usage](https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html).
