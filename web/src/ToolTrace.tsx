import React from "react";

export function ToolTrace({ steps, running = false, round, maxRounds }: any) {
  if (!steps?.length && !round && !running) return null;
  return (
    <details className="tool-trace">
      <summary>{running ? "Activity details" : "Reply details"}</summary>
      <p className="request-count">
        {round
          ? `${round} model request${round === 1 ? "" : "s"} used`
          : "Preparing request"}
        {maxRounds ? ` · ${maxRounds} maximum` : ""}
      </p>
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
    </details>
  );
}
