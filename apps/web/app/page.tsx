/* eslint-disable react/no-array-index-key */
"use client";

import { useState } from "react";

type TrackingSseEventType = "token" | "done" | "error";

type TrackingSseMetadata = {
  agent: "tracking" | "rates" | "retail" | "faq" | "system";
  timestamp: string;
  conversationId: string;
};

type AgentType = "tracking" | "rates" | "retail" | "faq";

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
  const [selectedAgent, setSelectedAgent] = useState<AgentType>("tracking");

  const send = async () => {
    if (!input.trim()) return;
    if (isSending) return;
    setIsSending(true);
    setMessages((prev) => [...prev, `You: ${input}`]);

    try {
      const response = await fetch(
        `http://localhost:3001/api/messages/${encodeURIComponent(
          CONVERSATION_ID
        )}/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            message: input,
            selectedAgent: selectedAgent,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Gateway error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setIsSending(false);
        setMessages((prev) => [...prev, `Bot: Error: No response stream available. Is the gateway running?`]);
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
        if (event.type === "error") {
          setMessages((prev) => [...prev, `Bot: Error: ${event.content}`]);
        }
      }
    }

    setInput("");
    setIsSending(false);
    } catch (error) {
      console.error("Fetch error:", error);
      const errorMessage = error instanceof Error 
        ? error.message 
        : "Failed to connect to gateway. Make sure the gateway is running on http://localhost:3001";
      setMessages((prev) => [...prev, `Bot: Error: ${errorMessage}`]);
      setIsSending(false);
    }
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
          <span className="chat-badge">
            {selectedAgent === "tracking" && "Tracking agent • Online"}
            {selectedAgent === "rates" && "Rates agent • Online"}
            {selectedAgent === "retail" && "Retail centers agent • Online"}
            {selectedAgent === "faq" && "FAQ agent • Online"}
          </span>
        </header>

        <div className="chat-body">
          {/* Agent Selection */}
          <div className="agent-selector" style={{ 
            marginBottom: "1rem", 
            padding: "0.75rem",
            background: "rgba(255, 255, 255, 0.05)",
            borderRadius: "8px",
            display: "flex",
            gap: "0.5rem",
            flexWrap: "wrap"
          }}>
            <label style={{ color: "#fff", fontSize: "0.875rem", alignSelf: "center" }}>
              Select Agent:
            </label>
            <button
              type="button"
              onClick={() => setSelectedAgent("tracking")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: selectedAgent === "tracking" ? "#10b981" : "rgba(255, 255, 255, 0.1)",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.875rem",
                fontWeight: selectedAgent === "tracking" ? "600" : "400",
              }}
            >
              📦 Tracking
            </button>
            <button
              type="button"
              onClick={() => setSelectedAgent("rates")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: selectedAgent === "rates" ? "#10b981" : "rgba(255, 255, 255, 0.1)",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.875rem",
                fontWeight: selectedAgent === "rates" ? "600" : "400",
              }}
            >
              💰 Rates
            </button>
            <button
              type="button"
              onClick={() => setSelectedAgent("retail")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: selectedAgent === "retail" ? "#10b981" : "rgba(255, 255, 255, 0.1)",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.875rem",
                fontWeight: selectedAgent === "retail" ? "600" : "400",
              }}
            >
              📍 Retail Centers
            </button>
            <button
              type="button"
              onClick={() => setSelectedAgent("faq")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: selectedAgent === "faq" ? "#10b981" : "rgba(255, 255, 255, 0.1)",
                color: "#fff",
                cursor: "pointer",
                fontSize: "0.875rem",
                fontWeight: selectedAgent === "faq" ? "600" : "400",
              }}
            >
              ❓ FAQ
            </button>
          </div>

          <p className="chat-hint">
            {selectedAgent === "tracking" && (
              <>Try: <strong>track AWB 227047923763</strong> or paste any valid AWB number.</>
            )}
            {selectedAgent === "rates" && (
              <>Try: <strong>What's the rate from Riyadh to Jeddah for 5kg?</strong></>
            )}
            {selectedAgent === "retail" && (
              <>Try: <strong>Find retail centers in Riyadh</strong></>
            )}
            {selectedAgent === "faq" && (
              <>Ask: <strong>How do I track my shipment?</strong></>
            )}
          </p>

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-message bot">
                {selectedAgent === "tracking" && "Hi, I can help you track your SMSA shipment. Share your AWB number to see the latest status."}
                {selectedAgent === "rates" && "Hi, I can help you get shipping rates. Tell me the origin, destination, weight, and number of pieces."}
                {selectedAgent === "retail" && "Hi, I can help you find SMSA retail centers. Tell me the city or area you're looking for."}
                {selectedAgent === "faq" && "Hi, I can answer your questions about SMSA services. What would you like to know?"}
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
              placeholder={
                selectedAgent === "tracking" ? "Enter AWB, e.g. 227047923763" :
                selectedAgent === "rates" ? "e.g. Rate from Riyadh to Jeddah, 5kg" :
                selectedAgent === "retail" ? "e.g. Find centers in Riyadh" :
                "Ask your question..."
              }
            />
            <button
              type="button"
              onClick={send}
              disabled={isSending}
              className="chat-send-btn"
            >
              <span>{isSending ? "Sending..." : "Send"}</span>
              <span className="chat-send-icon">➤</span>
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

