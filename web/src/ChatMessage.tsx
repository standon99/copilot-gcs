import React, { useEffect, useState } from "react";
import Markdown from "react-markdown";
import { Square } from "lucide-react";
import { ToolTrace } from "./ToolTrace";

export function ChatMessage({ message, children, pending = false }: any) {
  const user = message.role === "user";
  const stopped =
    message.role === "error" && message.text.startsWith("Turn cancelled;");
  const role = stopped ? "stopped" : message.role;
  return (
    <article
      className={`chat-message ${role}`}
      aria-label={user ? "Your message" : "Copilot reply"}
    >
      <div className="message-meta">
        <span>
          {user
            ? "You"
            : stopped
              ? "Stopped"
              : message.role === "error"
                ? "Reply failed"
                : "Copilot"}
        </span>
        <time dateTime={new Date(message.ts * 1000).toISOString()}>
          {pending
            ? "Sending…"
            : new Date(message.ts * 1000).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
        </time>
      </div>
      <div className="message-bubble">
        {user || message.role === "error" ? (
          <p className="message-plain">{message.text}</p>
        ) : (
          <div className="message-markdown">
            <Markdown
              skipHtml
              components={{
                a: ({ node: _node, ...props }) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" />
                ),
                // Do not fetch unsolicited images included in model-generated text.
                img: ({ alt }) => <span>{alt || "Image"}</span>,
              }}
            >
              {message.text}
            </Markdown>
          </div>
        )}
      </div>
      {children}
      <ToolTrace steps={message.tool_trace} round={message.model?.rounds} />
    </article>
  );
}

export function WaitingReply({ model, startedAt, run, onStop }: any) {
  const [elapsed, setElapsed] = useState(0);
  const [stopping, setStopping] = useState(false);
  useEffect(() => {
    const tick = () =>
      setElapsed(Math.max(0, Math.floor(Date.now() / 1000 - startedAt)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [startedAt]);
  return (
    <article
      className="chat-message assistant waiting-reply"
      aria-label="Copilot is preparing a reply"
    >
      <div className="message-meta">
        <span>Copilot</span>
        <span className="reply-model" title={model}>
          {model}
        </span>
      </div>
      <div className="message-bubble waiting-bubble">
        <span className="typing-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span role="status">
          {stopping ? "Stopping…" : "Waiting for reply…"}
        </span>
      </div>
      <div className="reply-wait-actions">
        <span aria-label={`Waiting ${elapsed} seconds`}>
          {elapsed < 60
            ? `${elapsed}s`
            : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`}
        </span>
        <button
          className="stop-reply"
          disabled={!run || stopping}
          aria-label="Stop reply"
          onClick={async () => {
            setStopping(true);
            try {
              await onStop();
            } catch {
              setStopping(false);
            }
          }}
        >
          <Square size={10} fill="currentColor" /> Stop
        </button>
      </div>
      <ToolTrace
        steps={run?.steps || []}
        running
        round={run?.round}
        maxRounds={run?.max_rounds}
      />
    </article>
  );
}
