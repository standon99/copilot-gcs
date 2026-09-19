import React from "react";

export function ThinkingTrace({ responses = [] }: any) {
  const thoughts = responses.filter((response: any) => response.thinking);
  if (!thoughts.length) return null;
  return (
    <details className="thinking-trace">
      <summary>Thinking</summary>
      <div className="thinking-content">
        {thoughts.map((response: any) => (
          <section key={response.round}>
            {thoughts.length > 1 && <small>Request {response.round}</small>}
            <p>{response.thinking}</p>
          </section>
        ))}
      </div>
    </details>
  );
}

export function ToolTrace({
  steps,
  responses = [],
  running = false,
  round,
  maxRounds,
}: any) {
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
      {responses
        .filter(
          (response: any) =>
            response.content && !["running", "final"].includes(response.status),
        )
        .map((response: any) => (
          <details className="tool-step" key={`response-${response.round}`}>
            <summary>
              {response.status === "interrupted"
                ? "Unfinished response"
                : "Intermediate response"}
              <small>Request {response.round}</small>
            </summary>
            <p className="message-plain">{response.content}</p>
          </details>
        ))}
    </details>
  );
}
