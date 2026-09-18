# Engineering feasibility: Copilot GCS

Draft for review · 2026-09-17 · Initial scope: Copter, conventional Plane, and Rover

**Product direction:** [Copilot GCS](product.md) is an AI-enabled ground control station for simple waypoint flights and inspections. This document retains the earlier engineering assessment, not the product positioning.

**Implementation update:** the local application, all three simulator builds, real Ollama integration, and initial blinded trials are now implemented. This analysis preserves the pre-implementation assessment below; its workspace inventory and unmeasured items describe that earlier point in time. Consult [implementation.md](implementation.md) and [validation.md](validation.md) for the current capabilities and measured results. The original engineering estimates include substantial hardening and validation beyond this initial implementation.

**Recommendation: proceed with a staged prototype.** A browser ground station with parameters, satellite imagery, telemetry, logs, mission controls, and an LLM panel is technically feasible. Before upload, the LLM can help create, inspect, and edit a shared local mission draft through conversation. During execution, combine continuous deterministic monitoring with advisory LLM assessments, then measure whether the LLM adds useful detection or explanation on blinded SITL trials.

The unresolved validation question is the LLM's reliability, not whether it can be connected to ArduPilot. Do not promise detection of every fault, guaranteed response times from an inference API, or reliable identification of a physical cause from ambiguous telemetry.

The user requires multiple vehicle types from the start. This draft uses Copter, conventional fixed-wing Plane, and ground Rover as the initial profiles; all three are release requirements. Sub, boats, helicopters, and QuadPlane need additional profiles. The proposed implementation is specified in [design.md](design.md). The experiment protocol is in [sitl-evaluation.md](sitl-evaluation.md).

## What is already available

The inventory and cost example below are historical planning assumptions. The
current release has a shared automatic request cap (default one per 60 seconds,
operator-configurable with a 10-second minimum), plus separately bounded chat
tool loops; see [usage](usage.md) and [measured validation](validation.md).

This workspace contains a native Apple Silicon ArduCopter **4.7.1** build at commit `dbe792162d06cab66c3475fd5556bf7a120f119e`, a Python environment with `pymavlink 2.4.49` and `MAVProxy 1.8.74`, and launchers for TCP `127.0.0.1:5760` or MAVProxy forwarding to UDP `14550`. The existing [verification record](../verification.json) reports disarmed heartbeat, attitude, and position checks. The revision and clean source checkout were inspected during this analysis; that earlier smoke test was not rerun.

There is currently no application frontend, backend, LLM integration, or failure-detection benchmark here. Only the Copter binary is built. Plane and Rover sources and autotests are present, and their version headers also say 4.7.1, but their builds and runtime behavior were not verified. Firmware sources, recorded parameters, and existing autotests provide implementation evidence; they do not establish that the proposed application or its failure scenarios work.

ArduPilot exposes parameters, commands, missions, telemetry, and log transfer through MAVLink. This supports building the requested application without modifying flight-control firmware. [ArduPilot MAVLink interface](https://ardupilot.org/dev/docs/mavlink-commands.html)

## Feasibility by capability

| Capability | Assessment | Main qualification |
| --- | --- | --- |
| Browser instruments and satellite map | High | A local backend bridges MAVLink TCP/UDP/serial to browser HTTP/WebSocket traffic. Imagery requires a suitable tile source. |
| Full parameter browser and edits | High, with protocol work | Fetch the connected vehicle's parameters; verify writes by subsequent reads and handle incomplete transfers, reconnects, and firmware-specific metadata. |
| Live logs, recording, plots, replay | High | Ground-station telemetry logs and onboard DataFlash logs are different products with different completeness and download behavior. |
| Missions, arm/disarm, modes, movement, return/recovery | High for bounded vehicle profiles | Each type needs its own commands, validity checks, and state verification. Plane recovery is not Copter landing; Rover has no takeoff. |
| Multiple vehicle types and sessions | High, with additional validation | Profile-specific semantics and strict per-vehicle state isolation must exist from the first implementation. |
| Complete replacement for a mature GCS | Substantial scope | Calibration, firmware flashing, every mission command, peripherals, multiple vehicles, and transport edge cases require separate implementation and validation. |
| Ollama API integration | High | API access is documented; actual model, account limits, latency, and response reliability remain unmeasured. |
| Continuous LLM supervision | Feasible as advisory support | Use bounded periodic observations and event-driven reviews. Fast alerts and onboard failsafes must remain independent of inference. |
| Mission intent and operator-error review | High for explicit measurable constraints; semantic interpretation requires validation | Preserve the operator's brief separately from the loaded plan. Review units, altitude datum, phase exceptions, and ambiguity before activating numerical checks. |
| Conversational mission creation and iteration | High for a bounded mission-command set | Chat and map editing share one versioned draft. The model edits validated local data; the operator uploads an exact reviewed version through a separate vehicle-write path. |
| Identifying slow degradation and explaining incidents | Plausible, unproven | Requires sufficient sensor evidence and comparison with rules-only baselines. |
| Identifying every root cause or preventing a rapid crash | Unsupported | Sparse downlinked telemetry can be ambiguous; a model response may arrive after the event is over. |
| Blinded SITL failure evaluation | High for selected cases | Ground truth must be isolated in code, including simulator parameters, logs, tool results, and evaluation metadata. |

For the map, MapLibre provides a browser renderer for satellite raster layers; it does not itself supply a high-resolution imagery subscription. Choose the provider separately and retain attribution and permitted caching behavior. [MapLibre satellite example](https://maplibre.org/maplibre-gl-js/docs/examples/display-a-satellite-map/)

## Recommended approach and alternatives

**Build a focused application around a Python MAVLink gateway and a browser frontend.** This fits the existing Python/SITL installation and gives explicit control over command verification, the LLM's accessible data, and evaluation isolation. It also makes the application responsible for implementing the GCS features it advertises.

| Option | Benefit | Cost or limitation | Decision |
| --- | --- | --- | --- |
| Focused custom web GCS | Direct fit for monitoring, evidence display, and blind experiments | More GCS protocol/UI implementation | Recommended for the initial implementation |
| Extend Blue Robotics Cockpit | Existing browser GCS, widgets, telemetry, and mission UI | Copter coverage and integration with the command and observation boundaries need a spike | Reconsider before expanding to broad GCS parity |
| Existing desktop GCS plus a web copilot | Fastest way to test LLM value alongside mature controls | Does not satisfy the eventual single-webpage workflow | Useful development reference and comparison tool |

Cockpit is a credible reuse candidate. Its maintainers describe regular testing on ArduSub/ArduRover, initial aerial support, and limitations in advanced mission commands. Those statements make it unsuitable to assume complete aerial coverage without checking the required workflows. This is a documentation assessment, not a hands-on evaluation of Cockpit. [Cockpit project](https://github.com/bluerobotics/cockpit)

## Findings that change the design

1. **The browser needs a bridge.** Ordinary browser networking is not a general MAVLink UDP/TCP socket interface. Run the gateway next to SITL now, and next to a telemetry/serial connection later. A remotely hosted webpage would still need a reachable, authenticated gateway.
2. **An API-compatible endpoint does not guarantee every capability.** Ollama documents direct cloud access at `https://ollama.com/v1` with a bearer API key. Its structured-output documentation currently says cloud structured outputs are unsupported. The design therefore validates model-produced JSON itself and treats malformed responses as failed assessments. [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility), [authentication](https://docs.ollama.com/api/authentication), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
3. **Generic SITL examples can name obsolete parameters.** This checkout and recorded vehicle parameters expose `SIM_GPS1_ENABLE`, `SIM_GPS1_GLTCH_X`, and `SIM_ACC1_RND`. Use version-specific adapters, not copied assumptions such as `SIM_GPS_DISABLE` or `SIM_ACC_RND`. See the [scenario source evidence](sitl-evaluation.md#source-evidence).
4. **The answer can leak outside the prompt.** A parameter snapshot containing `SIM_ENGINE_FAIL`, a log filename containing `gps_loss`, or a tool result containing injector output can reveal the fault. A neutral system prompt alone is insufficient.
5. **Native warnings and independent discovery are different measurements.** An LLM repeating an autopilot battery warning can still help the operator, but does not demonstrate independent anomaly detection. Score operational usefulness and telemetry-only inference separately.
6. **Loss of telemetry limits knowledge.** The system can detect loss of visibility. It cannot report what the aircraft is doing during a complete outage without another observation path.
7. **Correct execution can still violate intent.** An incorrectly entered mission can be flown accurately. The system should compare reviewed intent, loaded plan/configuration, and actual behavior. Use the LLM for interpreting/explaining intent and deterministic checks for supported measurable constraints. Assess additional benefits such as energy prediction or payload verification only when their required models/data are present.

## Work estimate and decision gates

These are planning estimates for one experienced full-stack engineer familiar with MAVLink, assuming three vehicle profiles, local operation, and no firmware changes. They are not measured delivery commitments; vehicle-domain review is additional.

| Stage | Estimated engineering effort | Exit evidence |
| --- | --- | --- |
| Connectivity and observability spike | 2–3 weeks | All three SITL builds, measured streams, parameter write/readback, log capture, API latency, reproducible fault traces |
| Browser GCS core | 4–6 weeks | Map, instruments, parameters, shared versioned mission editor, vehicle-specific controls, logs/replay, concurrent session isolation |
| Continuous monitoring and chat | 3–5 weeks | Profile-specific rules, observation builder, validated LLM responses, evidence links, degraded behavior |
| Mission intent, conversational planning, and operator-error checks | 2–4 weeks | Reuse the mission editor for chat draft edits/reviews; reviewed constraints, plan/live comparisons, ambiguity handling, and dedicated evaluation |
| Blinded benchmark and hardening | 5–8 weeks | Three scenario suites, isolation tests, negative controls, held-out trials, comparative metrics, reconnect/failure tests |
| **Initial implementation total with mission intent** | **16–26 engineer-weeks** | A useful multi-vehicle application with measured limitations |

This provisional estimate assumes conversational planning reuses the same versioned editor, validators, and supported waypoint/mission operations as the map UI. A spike must validate that assumption; unrestricted mission generation or route optimization would require re-estimation. Broad GCS feature parity, calibrated mission-energy prediction, payload-specific verification, cross-vehicle coordination, and physical-aircraft readiness are additional work. Reassess build versus extension after the connectivity spike rather than treating the MVP estimate as the cost of replacing every Mission Planner feature.

The gates are: (1) prove required telemetry is available, (2) prove operator writes and fault injections have the intended effect, (3) prove the monitor cannot access ground truth, (4) meet the operational latency/false-alarm targets defined in the experiment plan, and (5) show useful improvement over native alerts and rules. If the LLM does not add value in detection, retain it for evidence-grounded explanations and postflight review.

## Costs and unresolved inputs

No model-hosting work is required for this phase. At a five-second monitoring interval, one vehicle generates up to **720 scheduled calls/hour**, before event reviews and chat. With a planning budget of 2,000–4,000 input tokens and 150–400 output tokens per call, that is **1.44–2.88 million input tokens/hour** and **108,000–288,000 output tokens/hour**. Actual tokenizer counts, rate limits, subscription constraints, and pricing must be measured for the selected account/model. Dollar costs are deliberately not estimated without those inputs.

The remaining choices do not block this design: exact Ollama model and endpoint, imagery provider, target airframes/sensors within each vehicle class, supported mission commands, retention limits, and any additional vehicle classes. Multiply the monitoring call budget by the number of concurrently monitored vehicles and reserve capacity per session. The API key is only needed for the implementation spike and belongs in backend secret configuration.

**Evidence boundary:** this is a source- and documentation-based feasibility analysis. No new flights, fault-injection runs, inference calls, or accuracy/latency benchmarks were performed for it.
