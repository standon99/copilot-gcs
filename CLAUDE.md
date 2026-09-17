# Project instructions

These instructions apply to work in this repository. Read the README and the
relevant design, implementation and validation documents before making changes.

## Product direction

- The product is **Copilot GCS**, an AI-enabled ground control station that makes
  everyday drone tasks easy. Lead with waypoint flights, point inspections and
  conversational planning. AI is part of the main workflow.
- Use one **Flight** workspace: vehicle selection, live map/mission editor,
  instruments and contextual flight controls. Keep Chat, Alerts and Watch rules
  distinct. Simulation and diagnostics support this workflow.
- Keep interface copy plain and functional. Do not add branding taglines,
  motivational phrases, repeated AI slogans or a separate four-step flow strip.
- Keep the distinction between current simulator control/external telemetry and
  future validated physical-vehicle operation explicit. Product copy must not
  imply that camera capture, survey coverage or autonomous connection setup is
  implemented when it is not.

## Every iteration must be committed

- Finish each completed iteration with a descriptive Git commit. Include all
  changes belonging to that iteration, including its documentation and assets.
- Run checks appropriate to the change before committing. Record what passed,
  what was not tested and any remaining limitation; never claim an unrun check.
- Inspect the staged diff and run `.venv/bin/python scripts/check-secrets.py
  --staged` before committing. Keep the repository hooks enabled.
- Do not include unrelated user changes, rewrite shared history, force-push, or
  push without the user's authorization. A request to commit is not a request
  to publish; an explicit request to push authorizes the corresponding push.
- If an iteration cannot be completed, retain the work and report the concrete
  blocker. Do not describe incomplete work as a completed iteration.

## README and documentation must always be current

- Review `README.md` and the affected files under `docs/` in **every iteration**.
  Update them in the same commit whenever behavior, setup, dependencies,
  configuration, supported vehicles, commands, API contracts, security
  boundaries, tests, screenshots, or limitations change.
- The README is the public entry point: it must describe what is implemented,
  key features and the shortest useful setup/run path. Keep it concise; put
  detailed setup, operating instructions and troubleshooting in `docs/`. Do not
  add research-question or roadmap/build-next sections to the README. Preserve
  the distinction between shipped behavior and design goals in the design docs.
- Keep `docs/implementation.md` aligned with the code and `docs/validation.md`
  aligned with actual evidence. Label older validation records and design
  baselines as historical; do not silently rewrite experimental results.
- Recheck documented commands and relative links. Update test counts and
  version requirements when they change. Do not keep installation-specific
  paths, active-server claims or remote-status claims as universal instructions.
- Update affected screenshots when visible UI changes make them misleading.
  Capture the actual running application, inspect every image, preserve map
  attribution, and document capture conditions in `docs/screenshots/README.md`.
  Never substitute generated mockups or fabricate successful model responses.
- If a document needs no change, state that it was checked and remains accurate
  in the iteration report. Keeping documentation current is mandatory; cosmetic
  edits that obscure useful history are not.

## Credentials and runtime boundaries

- Never print, commit, push or embed the private `.env` file or its credential.
  `.env.example` may contain variable names and empty/sample values only.
- Keep `.env`, `runtime/`, `ardupilot/`, `.venv/`, `.tools/`, `node_modules/`,
  recordings, private trial truth and build output ignored. Inspect screenshots
  and exported artifacts for secrets before staging them.
- Run `.venv/bin/python scripts/check-secrets.py --all` before any authorized
  push; the pre-push hook checks all local Git history for the configured key.
- Never weaken vehicle targeting, operator approval, stale-data checks,
  control leases, parameter readback or blinded-evaluation isolation to make
  a test or screenshot succeed.
- Use only app-owned SITL vehicles for write/flight tests. Preserve saved user
  settings, keep inference usage bounded, and stop test servers and simulators
  after verification unless the user requested they remain running.

## Useful checks

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check backend tests scripts
.venv/bin/ruff format --check backend tests scripts
(cd web && npm test && npm run build)
git diff --check
.venv/bin/python scripts/check-secrets.py --staged
```

Use Node 22+ for frontend commands. See `docs/setup.md` for the optional local Node
installation and the separate native SITL prerequisites. Documentation-only
changes need link/command/image checks; do not launch paid benchmark campaigns
for them. The MIT license applies to this repository's original code; preserve
upstream and dependency licenses.
