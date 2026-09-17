#!/bin/bash
set -euo pipefail
SITL_ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SITL_ROOT/runtime/mavproxy" "$SITL_ROOT/runtime/matplotlib"
cd "$SITL_ROOT/runtime/mavproxy"
exec env -u HOME LOCALAPPDATA="$SITL_ROOT/runtime" \
  MPLCONFIGDIR="$SITL_ROOT/runtime/matplotlib" \
  "$SITL_ROOT/.venv/bin/mavproxy.py" \
  --master tcp:127.0.0.1:5760 --out udp:127.0.0.1:14550 \
  --default-modules log,signing,wp,rally,fence,ftp,param,relay,tuneopt,arm,mode,calibration,rc,auxopt,misc,cmdlong,battery,output,adsb,layout \
  --state-basedir "$SITL_ROOT/runtime/mavproxy" --aircraft copter \
  "$@"
