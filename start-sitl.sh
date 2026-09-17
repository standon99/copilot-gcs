#!/bin/bash
set -euo pipefail
SITL_ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SITL_ROOT/runtime/sitl"
cd "$SITL_ROOT/runtime/sitl"
exec "$SITL_ROOT/ardupilot/build/sitl/bin/arducopter" \
  --model + --speedup 1 --home=-35.363261,149.165230,584,353 \
  --defaults "$SITL_ROOT/ardupilot/Tools/autotest/default_params/copter.parm" \
  --serial0 tcp:5760:wait "$@"
