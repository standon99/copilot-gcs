#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; chmod 600 .env; fi
if [ -d ardupilot/Tools/autotest/param_metadata ]; then .venv/bin/python scripts/generate-metadata.py; fi
# Prefer a suitable existing Node; this installation also has a repo-local Node 22.
if [ -x .tools/node_modules/node/bin/node ]; then PATH="$PWD/.tools/node_modules/node/bin:/usr/local/bin:$PATH"; export PATH; fi
node -e 'if(Number(process.versions.node.split(".")[0])<22)throw Error("Node 22+ is required to build. Install it or run npm install --prefix .tools node@22 first.")'
cd web
npm ci
npm run build
