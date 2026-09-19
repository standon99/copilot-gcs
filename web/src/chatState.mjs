// A local pending message belongs only to the vehicles selected at send time.
export function chatState(vehicleId, run, messages = [], request = null) {
  const local = request?.targets.includes(vehicleId) ? request : null;
  const freshRun = local && run?.id && run.id !== local.previousRuns[vehicleId];
  const running = run?.status === "running";
  const waiting = running || Boolean(local && !freshRun);
  const acknowledged =
    local &&
    messages.some(
      (m) =>
        m.role === "user" &&
        m.text === local.text &&
        m.ts >= local.startedAt - 2,
    );
  const last = messages.at(-1);
  const latest =
    waiting &&
    last?.role === "user" &&
    (!local || (last.text === local.text && last.ts >= local.startedAt - 2))
      ? last
      : null;
  return {
    waiting,
    run: running ? run : null,
    local,
    messages: latest ? messages.slice(0, -1) : messages,
    outgoing:
      latest ||
      (waiting && local && !acknowledged
        ? { role: "user", text: local.text, ts: local.startedAt, pending: true }
        : null),
  };
}
