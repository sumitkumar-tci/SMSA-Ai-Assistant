/* eslint-disable react/no-array-index-key */
"use client";

import { useState } from "react";

type TrackingSseEventType = "token" | "done" | "error";

type TrackingSseMetadata = {
  agent: "tracking";
  timestamp: string;
  conversationId: string;
};

type TrackingSseEvent = {
  type: TrackingSseEventType;
  content: string;
  metadata: TrackingSseMetadata;
};

const CONVERSATION_ID = "demo-conversation";

export default function HomePage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [isSending, setIsSending] = useState(false);

  const send = async () => {
    if (!input.trim()) return;
    if (isSending) return;
    setIsSending(true);
    setMessages((prev) => [...prev, `You: ${input}`]);

    const response = await fetch(
      `http://localhost:3001/api/messages/${encodeURIComponent(
        CONVERSATION_ID
      )}/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input }),
      }
    );

    const reader = response.body?.getReader();
    if (!reader) {
      setIsSending(false);
      return;
    }

    const decoder = new TextDecoder("utf-8");
    let partial = "";

    // Read SSE stream
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      partial += decoder.decode(value, { stream: true });
      const blocks = partial.split("\n\n");
      partial = blocks.pop() ?? "";

      for (const block of blocks) {
        if (!block.startsWith("data:")) continue;
        const json = block.slice(5).trim();
        if (!json) continue;

        let event: TrackingSseEvent;
        try {
          event = JSON.parse(json) as TrackingSseEvent;
        } catch {
          // Ignore malformed events
          // eslint-disable-next-line no-continue
          continue;
        }

        if (event.type === "token") {
          setMessages((prev) => [...prev, `Bot: ${event.content}`]);
        }
      }
    }

    setInput("");
    setIsSending(false);
  };

  return (
    <div className="app-shell">
      <section className="chat-card">
        <header className="chat-header">
          <div className="chat-title">
            <span className="chat-title-main">SMSA AI Assistant</span>
            <span className="chat-title-sub">
              Track your shipment in real time using your AWB.
            </span>
          </div>
          <span className="chat-badge">Tracking agent • Online</span>
        </header>

        <div className="chat-body">
          <p className="chat-hint">
            Try: <strong>track AWB 227047923763</strong> or paste any valid AWB
            number.
          </p>

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-message bot">
                Hi, I can help you track your SMSA shipment. Share your AWB
                number to see the latest status.
              </div>
            )}
            {messages.map((m, idx) => {
              const isUser = m.startsWith("You:");
              const content = isUser ? m.replace(/^You:\s*/, "") : m.replace(/^Bot:\s*/, "");
              return (
                <div
                  key={idx}
                  className={`chat-message ${isUser ? "user" : "bot"}`}
                >
                  {content}
                </div>
              );
            })}
          </div>
        </div>

        <footer className="chat-footer">
          <div className="chat-input-row">
            <input
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Enter AWB, e.g. 227047923763"
            />
            <button
              type="button"
              onClick={send}
              disabled={isSending}
              className="chat-send-btn"
            >
              <span>{isSending ? "Tracking..." : "Send"}</span>
              <span className="chat-send-icon">➤</span>
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

