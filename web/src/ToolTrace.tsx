import React from "react";

export function ToolTrace({
  steps,
  running = false,
  round,
  maxRounds,
  onCancel,
}: any) {
  if (!steps?.length && !running) return null;
  return (
    <details className="tool-trace" open={running || undefined}>
      <summary>
        {running
          ? round
            ? `Working · model call ${round}/${maxRounds}`
            : "Preparing turn…"
          : `${steps.length} tool actions`}
      </summary>
      {steps?.map((step: any) => (
        <details key={step.id} className={`tool-step ${step.status}`}>
          <summary>
            <span>{step.name.replaceAll("_", " ")}</span>
            <small>{step.status === "ok" ? "✓" : step.status}</small>
          </summary>
          <pre>{JSON.stringify(step.arguments, null, 2)}</pre>
          <pre>
            {typeof step.result === "string"
              ? step.result
              : JSON.stringify(step.result, null, 2)}
          </pre>
        </details>
      ))}
      {running && <button onClick={onCancel}>Cancel turn</button>}
    </details>
  );
}
