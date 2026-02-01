/* eslint-disable react/no-array-index-key */
"use client";

import { useState, useRef } from "react";

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

type Message = {
  id: string;
  role: "user" | "bot";
  content: string;
  fileId?: string;
  fileName?: string;
  extractedData?: {
    awb?: string;
    origin?: string;
    destination?: string;
  };
};

const CONVERSATION_ID = "demo-conversation";

export default function HomePage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<AgentType>("tracking");
  const [uploadedFileId, setUploadedFileId] = useState<string | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("conversationId", CONVERSATION_ID);

      const response = await fetch("http://localhost:3001/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const data = await response.json();
      
      if (data.success) {
        setUploadedFileId(data.object_key);
        setUploadedFileName(file.name);
        
        // Show upload success message
        const uploadMessage: Message = {
          id: Date.now().toString(),
          role: "user",
          content: `📎 Uploaded: ${file.name}`,
          fileId: data.object_key,
          fileName: file.name,
          extractedData: data.extracted_data,
        };
        setMessages((prev) => [...prev, uploadMessage]);

        // If AWB was extracted, show tracking details automatically
        if (data.extracted_data?.awb) {
          if (data.tracking_details) {
            // Show automatic tracking details
            const trackingMessage: Message = {
              id: (Date.now() + 1).toString(),
              role: "bot",
              content: data.tracking_details,
            };
            setMessages((prev) => [...prev, trackingMessage]);
          } else {
            // Fallback if auto-tracking didn't work
            const awbMessage: Message = {
              id: (Date.now() + 1).toString(),
              role: "bot",
              content: `✅ AWB extracted: ${data.extracted_data.awb}. You can now ask me to track it!`,
            };
            setMessages((prev) => [...prev, awbMessage]);
          }
        }
      }
    } catch (error) {
      console.error("Upload error:", error);
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: "bot",
        content: `❌ Upload failed: ${error instanceof Error ? error.message : "Unknown error"}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsUploading(false);
    }
  };

  const send = async () => {
    if (!input.trim() && !uploadedFileId) return;
    if (isSending) return;
    setIsSending(true);

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input || (uploadedFileId ? "Track this" : ""),
      fileId: uploadedFileId || undefined,
      fileName: uploadedFileName || undefined,
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const response = await fetch(
        `http://localhost:3001/api/messages/${encodeURIComponent(
          CONVERSATION_ID
        )}/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            message: input || (uploadedFileId ? "Track this" : ""),
            selectedAgent: selectedAgent,
            fileId: uploadedFileId || undefined,
            fileUrl: uploadedFileId ? undefined : undefined, // Can be set if we have URL
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
          // Update or create bot message
          setMessages((prev) => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.role === "bot" && lastMessage.id.startsWith("bot-")) {
              // Update existing bot message
              return prev.map((msg, idx) => 
                idx === prev.length - 1 
                  ? { ...msg, content: event.content }
                  : msg
              );
            } else {
              // Create new bot message
              return [...prev, {
                id: `bot-${Date.now()}`,
                role: "bot" as const,
                content: event.content,
              }];
            }
          });
        }
        if (event.type === "error") {
          const errorMessage: Message = {
            id: Date.now().toString(),
            role: "bot",
            content: `❌ Error: ${event.content}`,
          };
          setMessages((prev) => [...prev, errorMessage]);
        }
      }
    }

    setInput("");
    setUploadedFileId(null);
    setUploadedFileName(null);
    setIsSending(false);
    } catch (error) {
      console.error("Fetch error:", error);
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: "bot",
        content: `❌ Error: ${error instanceof Error 
          ? error.message 
          : "Failed to connect to gateway. Make sure the gateway is running on http://localhost:3001"}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
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
                {selectedAgent === "tracking" && "Hi, I can help you track your SMSA shipment. Share your AWB number or upload a waybill image to see the latest status."}
                {selectedAgent === "rates" && "Hi, I can help you get shipping rates. Tell me the origin, destination, weight, and number of pieces."}
                {selectedAgent === "retail" && "Hi, I can help you find SMSA retail centers. Tell me the city or area you're looking for."}
                {selectedAgent === "faq" && "Hi, I can answer your questions about SMSA services. What would you like to know?"}
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={`chat-message ${m.role}`}
              >
                {m.fileId && (
                  <div style={{ 
                    marginBottom: "4px", 
                    fontSize: "11px", 
                    opacity: 0.8,
                    display: "flex",
                    alignItems: "center",
                    gap: "4px"
                  }}>
                    📎 {m.fileName || "Uploaded file"}
                    {m.extractedData?.awb && (
                      <span style={{ marginLeft: "8px", color: "#10b981" }}>
                        (AWB: {m.extractedData.awb})
                      </span>
                    )}
                  </div>
                )}
                <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
              </div>
            ))}
          </div>
        </div>

        <footer className="chat-footer">
          {/* File Upload Section */}
          <div style={{ 
            marginBottom: "8px", 
            display: "flex", 
            alignItems: "center", 
            gap: "8px",
            fontSize: "12px"
          }}>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  handleFileUpload(file);
                }
                // Reset input
                if (fileInputRef.current) {
                  fileInputRef.current.value = "";
                }
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              style={{
                padding: "6px 12px",
                borderRadius: "6px",
                border: "1px solid rgba(55, 65, 81, 0.9)",
                background: "rgba(15, 23, 42, 0.9)",
                color: "#e5e7eb",
                fontSize: "12px",
                cursor: isUploading ? "not-allowed" : "pointer",
                opacity: isUploading ? 0.6 : 1,
                display: "flex",
                alignItems: "center",
                gap: "4px",
              }}
            >
              {isUploading ? "⏳ Uploading..." : "📎 Upload"}
            </button>
            {uploadedFileId && (
              <span style={{ 
                color: "#10b981", 
                fontSize: "11px",
                display: "flex",
                alignItems: "center",
                gap: "4px"
              }}>
                ✓ {uploadedFileName}
                <button
                  type="button"
                  onClick={() => {
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#ef4444",
                    cursor: "pointer",
                    fontSize: "12px",
                    padding: "0 4px",
                  }}
                >
                 
                </button>
              </span>
            )}
          </div>

          <div className="chat-input-row">
            <input
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={
                uploadedFileId 
                  ? "Ask about the uploaded file or type a message..."
                  : selectedAgent === "tracking" 
                    ? "Enter AWB, e.g. 227047923763 or upload waybill image" 
                    : selectedAgent === "rates" 
                      ? "e.g. Rate from Riyadh to Jeddah, 5kg" 
                      : selectedAgent === "retail" 
                        ? "e.g. Find centers in Riyadh" 
                        : "Ask your question..."
              }
            />
            <button
              type="button"
              onClick={send}
              disabled={isSending || (!input.trim() && !uploadedFileId)}
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

