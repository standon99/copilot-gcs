#!/bin/sh
set -eu
cd "$(dirname "$0")/../ardupilot"
export CCACHE_DISABLE=1
../.venv/bin/python ./waf configure --board sitl --no-submodule-update --disable-networking
../.venv/bin/python ./waf copter plane rover -j 4
