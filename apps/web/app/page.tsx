/* eslint-disable react/no-array-index-key */
"use client";

import { useState, useRef } from "react";

// Clean up any reasoning/thinking content from LLM responses
function cleanReasoningContent(content: string): string {
  if (!content) return content;
  
  // Remove tagged reasoning
  let cleaned = content.replace(/<think>.*?<\/think>/gis, '');
  cleaned = cleaned.replace(/<reasoning>.*?<\/reasoning>/gis, '');
  cleaned = cleaned.replace(/<think>.*?<\/redacted_reasoning>/gis, '');
  cleaned = cleaned.replace(/<\/?think>/gi, '');
  cleaned = cleaned.replace(/<\/?reasoning>/gi, '');
  
  // Remove plain text reasoning patterns (LLM showing its thinking)
  // Split by sentences and filter out reasoning sentences
  const sentences = cleaned.split(/([.!?]\s+)/);
  const cleanedSentences: string[] = [];
  
  for (let i = 0; i < sentences.length; i += 2) {
    const sentence = sentences[i] || '';
    const punctuation = sentences[i + 1] || '';
    const sentenceLower = sentence.toLowerCase().trim();
    
    // Skip sentences that start with reasoning patterns
    const reasoningStarters = [
      'okay', 'i need to', 'let me', 'first', 'i should', 'maybe',
      'also', 'the rules', 'the example', 'let me check', 'let me see',
      'since', 'i should make sure', 'let me structure', 'wts is this',
      'i have to', 'let me check the', 'the user', 'i need to respond'
    ];
    
    const isReasoning = reasoningStarters.some(starter => sentenceLower.startsWith(starter));
    
    // Also skip if sentence is too long and contains reasoning keywords
    if (!isReasoning && sentence.length > 100) {
      const hasReasoningKeywords = ['guidelines', 'check', 'structure', 'need to', 'should', 'rules say'].some(
        keyword => sentenceLower.includes(keyword)
      );
      if (hasReasoningKeywords) continue;
    }
    
    if (!isReasoning) {
      cleanedSentences.push(sentence + punctuation);
    }
  }
  
  cleaned = cleanedSentences.join('');
  
  // Clean up extra whitespace
  cleaned = cleaned.replace(/\n\s*\n\s*\n+/g, '\n\n');
  cleaned = cleaned.replace(/\s+/g, ' ');
  
  return cleaned.trim();
}

// Function to render markdown-like content (convert **bold** to <strong>, etc.)
function renderMarkdown(text: string): string {
  if (!text) return text;
  
  // Convert **bold** to <strong>
  let html = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Convert *italic* to <em> (but not if it's part of **bold**)
  html = html.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, '<em>$1</em>');
  // Convert line breaks
  html = html.replace(/\n/g, '<br />');
  
  return html;
}

// Tracking Message Component
function TrackingMessage({ data, content }: { data: TrackingData; content: string }) {
  const [expandedEvents, setExpandedEvents] = useState(false);

  const formatTimestamp = (timestamp: string) => {
    if (!timestamp || timestamp.trim() === "") return "N/A";
    try {
      const date = new Date(timestamp);
      if (isNaN(date.getTime())) {
        // Try parsing as custom format
        return timestamp;
      }
      return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(date);
    } catch {
      return timestamp;
    }
  };

  const getStatusColor = (status: string) => {
    const statusLower = status.toLowerCase();
    if (statusLower.includes("delivered")) return "status-delivered";
    if (statusLower.includes("transit") || statusLower.includes("out for delivery")) return "status-transit";
    if (statusLower.includes("exception") || statusLower.includes("returned")) return "status-exception";
    return "status-pending";
  };

  return (
    <div className="tracking-result-card">
      {/* LLM conversational response */}
      <div 
        className="tracking-conversational-content"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
      />

      {/* Current Status - Prominent Display */}
      <div className="current-status-section">
        <div className={`status-badge ${getStatusColor(data.currentStatus)}`}>
          <span className="status-icon">📦</span>
          <span className="status-text">{data.currentStatus}</span>
        </div>
        {data.statusExplanation && (
          <p className="status-explanation">{data.statusExplanation}</p>
        )}
      </div>

      {/* AWB Info */}
      <div className="awb-info">
        <span className="label">Tracking Number:</span>
        <span className="value">{data.awb}</span>
        <button
          type="button"
          className="copy-btn"
          onClick={() => {
            navigator.clipboard.writeText(data.awb);
          }}
          title="Copy AWB"
        >
          📋
        </button>
      </div>

      {/* Route Info */}
      <div className="route-section">
        <div className="route-item">
          <span className="route-icon">📍</span>
          <div>
            <span className="label">Origin</span>
            <span className="location">{data.origin}</span>
          </div>
        </div>
        <span className="route-arrow">→</span>
        <div className="route-item">
          <span className="route-icon">📍</span>
          <div>
            <span className="label">Destination</span>
            <span className="location">{data.destination}</span>
          </div>
        </div>
      </div>

      {/* Timeline of Events */}
      {data.events && data.events.length > 0 && (
        <div className="events-timeline">
          <button
            type="button"
            className="toggle-events"
            onClick={() => setExpandedEvents(!expandedEvents)}
          >
            <span>📦</span>
            <span>Shipment Journey ({data.events.length} events)</span>
            <span className={`chevron ${expandedEvents ? "expanded" : ""}`}>▼</span>
          </button>

          {expandedEvents && (
            <div className="timeline">
              {data.events.map((event, index) => (
                <TimelineEvent
                  key={index}
                  event={event}
                  isLatest={index === 0}
                  isFirst={index === data.events.length - 1}
                  formatTimestamp={formatTimestamp}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Additional Info */}
      {(data.serviceType || data.estimatedDelivery) && (
        <div className="additional-info">
          {data.serviceType && (
            <div className="info-item">
              <span>🚚</span>
              <span>{data.serviceType}</span>
            </div>
          )}
          {data.estimatedDelivery && (
            <div className="info-item">
              <span>⏰</span>
              <span>Est. Delivery: {data.estimatedDelivery}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Timeline Event Component
function TimelineEvent({
  event,
  isLatest,
  isFirst,
  formatTimestamp,
}: {
  event: TrackingEvent;
  isLatest: boolean;
  isFirst: boolean;
  formatTimestamp: (ts: string) => string;
}) {
  return (
    <div className={`timeline-event ${isLatest ? "latest" : ""}`}>
      <div className="timeline-marker">
        <div className={`marker-dot ${isLatest ? "active" : ""}`} />
        {!isFirst && <div className="marker-line" />}
      </div>

      <div className="event-content">
        <div className="event-header">
          <span className="event-status">{event.status}</span>
          <span className="event-time">{formatTimestamp(event.timestamp)}</span>
        </div>
        <div className="event-location">
          <span>📍</span>
          <span>{event.location}</span>
        </div>
        <p className="event-description">{event.description}</p>
      </div>
    </div>
  );
}

// Retail Centers Message Component
function RetailCentersMessage({ data, content }: { data: RetailCentersData; content: string }) {
  const [expandedCenters, setExpandedCenters] = useState(false);

  return (
    <div className="retail-centers-card">
      {/* LLM conversational response */}
      <div 
        className="retail-conversational-content"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
      />

      {/* Centers List */}
      {data.centers && data.centers.length > 0 && (
        <div className="centers-list">
          <button
            type="button"
            className="toggle-centers"
            onClick={() => setExpandedCenters(!expandedCenters)}
          >
            <span>📍</span>
            <span>Service Centers ({data.centers.length})</span>
            <span className={`chevron ${expandedCenters ? "expanded" : ""}`}>▼</span>
          </button>

          {expandedCenters && (
            <div className="centers-grid">
              {data.centers.map((center, index) => (
                <div key={index} className="center-card">
                  <div className="center-header">
                    <h4>{center.name}</h4>
                    {center.distance_km !== undefined && center.distance_km !== null && (
                      <span className="distance-badge">{center.distance_km} km</span>
                    )}
                  </div>
                  
                  {center.address && center.address !== "N/A" && (
                    <div className="center-info">
                      <span className="info-icon">📍</span>
                      <span>{center.address}</span>
                    </div>
                  )}
                  
                  {center.phone && center.phone !== "N/A" && (
                    <div className="center-info">
                      <span className="info-icon">📞</span>
                      <a href={`tel:${center.phone}`}>{center.phone}</a>
                    </div>
                  )}
                  
                  {/* Working Hours */}
                  {center.working_hours ? (
                    <div className="center-info">
                      <span className="info-icon">🕐</span>
                      <div className="working-hours">
                        {Object.entries(center.working_hours).map(([day, shifts]) => {
                          if (shifts.length === 0) return null;
                          const dayNames: { [key: string]: string } = {
                            Sat: "Saturday",
                            Sun: "Sunday",
                            Mon: "Monday",
                            Tue: "Tuesday",
                            Wed: "Wednesday",
                            Thu: "Thursday",
                            Fri: "Friday",
                          };
                          return (
                            <div key={day} className="hours-day">
                              <strong>{dayNames[day] || day}:</strong> {shifts.join(", ")}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : center.hours && center.hours !== "N/A" ? (
                    <div className="center-info">
                      <span className="info-icon">🕐</span>
                      <span>{center.hours}</span>
                    </div>
                  ) : null}
                  
                  {center.city && center.city !== "N/A" && (
                    <div className="center-info">
                      <span className="info-icon">🏙️</span>
                      <span>{center.city}</span>
                    </div>
                  )}
                  
                  {/* Cold Box Indicator */}
                  {center.cold_box && (
                    <div className="center-info">
                      <span className="info-icon">❄️</span>
                      <span>Cold Storage Available</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Loading State Component
function TrackingLoadingState({ stage }: { stage: "searching" | "processing" | "formatting" }) {
  const stages = [
    { id: "searching", label: "Looking up shipment...", icon: "🔍" },
    { id: "processing", label: "Processing tracking data...", icon: "⚙️" },
    { id: "formatting", label: "Preparing results...", icon: "✨" },
  ];

  return (
    <div className="tracking-loading">
      <div className="loading-animation">
        <div className="truck-icon">🚚</div>
        <div className="road-line" />
      </div>

      <div className="loading-stages">
        {stages.map((s, idx) => {
          const isActive = s.id === stage;
          const stageIndex = stages.findIndex((st) => st.id === stage);
          const isComplete = stageIndex > idx;

          return (
            <div
              key={s.id}
              className={`stage ${isActive ? "active" : ""} ${isComplete ? "complete" : ""}`}
            >
              <span className="stage-icon">{s.icon}</span>
              <span>{s.label}</span>
              {isActive && <span className="spinner">⏳</span>}
              {isComplete && <span className="check">✓</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

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
  metadata: TrackingSseMetadata & {
    type?: string;
    raw_data?: TrackingData;
    events?: TrackingEvent[];
    current_status?: string;
    status_explanation?: string;
    centers?: RetailCenter[];
    location_info?: {
      post_code?: string;
      area_name?: string;
      city_name?: string;
      location_type?: string;
    };
    city?: string;
  };
};

type TrackingEvent = {
  timestamp: string;
  location: string;
  description: string;
  status: string;
};

type TrackingData = {
  awb: string;
  currentStatus: string;
  statusExplanation?: string;
  location: string;
  lastUpdate: string;
  origin: string;
  destination: string;
  events: TrackingEvent[];
  serviceType?: string;
  estimatedDelivery?: string;
};

type RetailCenter = {
  code?: string;
  name: string;
  address: string;
  city: string;
  country?: string;
  region?: string;
  phone: string;
  hours?: string;
  working_hours?: {
    [key: string]: string[]; // Day name -> array of shift times (e.g., "Sat": ["8:00-23:00"])
  };
  latitude?: number;
  longitude?: number;
  distance_km?: number;
  cold_box?: boolean;
  short_code?: string;
};

type RetailCentersData = {
  centers: RetailCenter[];
  location_info?: {
    post_code?: string;
    area_name?: string;
    city_name?: string;
    location_type?: string;
  };
  city?: string;
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
  trackingData?: TrackingData;
  retailCentersData?: RetailCentersData;
  messageType?: "conversational" | "tracking_result" | "retail_result" | "error";
};

type Conversation = {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: Date;
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
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentConversationId, setCurrentConversationId] = useState(CONVERSATION_ID);
  const [loadingState, setLoadingState] = useState<"idle" | "searching" | "processing" | "formatting">("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    
    // Show initial upload message
    const uploadMessageId = Date.now().toString();
    const uploadMessage: Message = {
      id: uploadMessageId,
      role: "user",
      content: `📎 Uploading: ${file.name}`,
      fileName: file.name,
    };
    setMessages((prev) => [...prev, uploadMessage]);
    
    // Show loading state
    setLoadingState("searching");
    
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("conversationId", currentConversationId);

      // Update message to show processing
      setMessages((prev) => prev.map(msg => 
        msg.id === uploadMessageId 
          ? { ...msg, content: `📎 Image uploaded. Finding AWB number...` }
          : msg
      ));
      setLoadingState("processing");

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
        
        // Update upload message with success
        setMessages((prev) => prev.map(msg => 
          msg.id === uploadMessageId 
            ? { 
                ...msg, 
                content: `📎 Uploaded: ${file.name}`,
                fileId: data.object_key,
                extractedData: data.extracted_data,
              }
            : msg
        ));

        // If AWB was extracted, show tracking details automatically with structured data
        if (data.extracted_data?.awb) {
          // Show progressive loading messages
          setLoadingState("formatting");
          
          // Update message to show AWB found
          setMessages((prev) => prev.map(msg => 
            msg.id === uploadMessageId 
              ? { ...msg, content: `📎 Uploaded: ${file.name}\n✅ AWB found: ${data.extracted_data.awb}` }
              : msg
          ));
          
          // Small delay to show "Fetching tracking data..." message
          await new Promise(resolve => setTimeout(resolve, 500));
          
          setMessages((prev) => prev.map(msg => 
            msg.id === uploadMessageId 
              ? { ...msg, content: `📎 Uploaded: ${file.name}\n✅ AWB found: ${data.extracted_data.awb}\n🔍 Fetching tracking data...` }
              : msg
          ));
          
          if (data.tracking_details) {
            // Build structured tracking data from response
            const trackingData: TrackingData | undefined = data.tracking_data ? {
              awb: data.tracking_data.awb || data.extracted_data.awb,
              currentStatus: data.tracking_data.currentStatus || data.tracking_status || "UNKNOWN",
              statusExplanation: data.tracking_data.statusExplanation || data.tracking_status_explanation,
              location: data.tracking_data.location || "N/A",
              lastUpdate: data.tracking_data.lastUpdate || "",
              origin: data.tracking_data.origin || "N/A",
              destination: data.tracking_data.destination || "N/A",
              events: data.tracking_data.events || data.tracking_events || [],
              serviceType: data.tracking_data.serviceType,
              estimatedDelivery: data.tracking_data.estimatedDelivery,
            } : undefined;
            
            // Show automatic tracking details with structured data
            const trackingMessage: Message = {
              id: (Date.now() + 1).toString(),
              role: "bot",
              content: data.tracking_details,
              trackingData: trackingData,
              messageType: data.tracking_type || (trackingData ? "tracking_result" : "conversational"),
            };
            setMessages((prev) => [...prev, trackingMessage]);
            setLoadingState("idle");
          } else {
            // Fallback if auto-tracking didn't work
            const awbMessage: Message = {
              id: (Date.now() + 1).toString(),
              role: "bot",
              content: `✅ AWB extracted: ${data.extracted_data.awb}. You can now ask me to track it!`,
            };
            setMessages((prev) => [...prev, awbMessage]);
            setLoadingState("idle");
          }
        } else {
          setLoadingState("idle");
        }
      }
    } catch (error) {
      console.error("Upload error:", error);
      setLoadingState("idle");
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: "bot",
        content: `❌ Upload failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        messageType: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsUploading(false);
    }
  };

  const send = async () => {
    // For tracking agent, allow sending with file or text
    // For other agents, require text input
    if (selectedAgent === "tracking") {
      if (!input.trim() && !uploadedFileId) return;
      
      // Check if message contains AWB to show loading states
      const awbMatch = input.match(/\b\d{10,15}\b/);
      if (awbMatch || uploadedFileId) {
        setLoadingState("searching");
        // Simulate progress updates
        setTimeout(() => setLoadingState("processing"), 1500);
        setTimeout(() => setLoadingState("formatting"), 3000);
      }
    } else {
      if (!input.trim()) return;
    }
    if (isSending) return;
    setIsSending(true);

    // Store message content and clear input IMMEDIATELY (before async operations)
    const messageContent = input || (uploadedFileId && selectedAgent === "tracking" ? "Track this" : "");
    setInput(""); // Clear input box immediately - user should see it disappear right away

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageContent,
      fileId: selectedAgent === "tracking" ? (uploadedFileId || undefined) : undefined,
      fileName: selectedAgent === "tracking" ? (uploadedFileName || undefined) : undefined,
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const response = await fetch(
        `http://localhost:3001/api/messages/${encodeURIComponent(
          currentConversationId
        )}/stream`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            message: messageContent, // Use stored message content (input is already cleared)
            selectedAgent: selectedAgent,
            fileId: selectedAgent === "tracking" ? (uploadedFileId || undefined) : undefined,
            fileUrl: selectedAgent === "tracking" && uploadedFileId ? undefined : undefined,
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Gateway error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setIsSending(false);
        const errorMessage: Message = {
          id: Date.now().toString(),
          role: "bot",
          content: `❌ Error: No response stream available. Is the gateway running?`,
          messageType: "error",
        };
        setMessages((prev) => [...prev, errorMessage]);
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
          // Check if this is a tracking result with structured data
          const hasTrackingData = event.metadata?.raw_data || event.metadata?.events;
          const hasRetailCenters = event.metadata?.centers && Array.isArray(event.metadata.centers) && event.metadata.centers.length > 0;
          
          // Build retail centers data if present
          const retailCentersData: RetailCentersData | undefined = hasRetailCenters ? {
            centers: event.metadata.centers as RetailCenter[],
            location_info: event.metadata.location_info,
            city: event.metadata.city,
          } : undefined;
          
          // Determine message type
          let messageType: "conversational" | "tracking_result" | "retail_result" | "error" = "conversational";
          if (event.metadata?.type) {
            messageType = event.metadata.type as any;
          } else if (hasTrackingData) {
            messageType = "tracking_result";
          } else if (hasRetailCenters) {
            messageType = "retail_result";
          }
          
          // Update or create bot message
          setMessages((prev) => {
            const lastMessage = prev[prev.length - 1];
            if (lastMessage && lastMessage.role === "bot" && lastMessage.id.startsWith("bot-")) {
              // Update existing bot message - APPEND new content for streaming
              const newContent = lastMessage.content + event.content;
              return prev.map((msg, idx) => 
                idx === prev.length - 1 
                  ? { 
                      ...msg, 
                      content: newContent,
                      trackingData: event.metadata?.raw_data || msg.trackingData,
                      retailCentersData: retailCentersData || msg.retailCentersData,
                      messageType: messageType,
                    }
                  : msg
              );
            } else {
              // Create new bot message
              return [...prev, {
                id: `bot-${Date.now()}`,
                role: "bot" as const,
                content: event.content,
                trackingData: event.metadata?.raw_data,
                retailCentersData: retailCentersData,
                messageType: messageType,
              }];
            }
          });
          
          // Reset loading state when we get any response
          if (loadingState !== "idle") {
            setLoadingState("idle");
          }
        }
        if (event.type === "error") {
          const errorMessage: Message = {
            id: Date.now().toString(),
            role: "bot",
            content: `❌ Error: ${event.content}`,
            messageType: "error",
          };
          setMessages((prev) => [...prev, errorMessage]);
          setLoadingState("idle");
        }
        if (event.type === "done") {
          setLoadingState("idle");
        }
      }
    }

    // Input already cleared at the start of send() function
    // Only clear file upload if it was used (tracking agent)
    if (selectedAgent === "tracking") {
      setUploadedFileId(null);
      setUploadedFileName(null);
    }
    setLoadingState("idle");
    setIsSending(false);
    } catch (error) {
      console.error("Fetch error:", error);
      const errorMessage: Message = {
        id: Date.now().toString(),
        role: "bot",
        content: `❌ Error: ${error instanceof Error 
          ? error.message 
          : "Failed to connect to gateway. Make sure the gateway is running on http://localhost:3001"}`,
        messageType: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
      setLoadingState("idle");
      setIsSending(false);
    }
  };

  const createNewConversation = () => {
    const newId = `conv-${Date.now()}`;
    setCurrentConversationId(newId);
    setMessages([]);
    setUploadedFileId(null);
    setUploadedFileName(null);
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? "open" : "closed"}`}>
        <div className="sidebar-header">
          <button
            type="button"
            onClick={createNewConversation}
            className="new-chat-btn"
          >
            <span>+</span> New Chat
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="sidebar-toggle"
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? "←" : "→"}
          </button>
        </div>
        <div className="conversations-list">
          {conversations.length === 0 ? (
            <div className="empty-conversations">
              <p>No conversations yet</p>
              <p className="hint">Start a new chat to begin</p>
            </div>
          ) : (
            conversations.map((conv) => (
              <button
                key={conv.id}
                type="button"
                className={`conversation-item ${
                  currentConversationId === conv.id ? "active" : ""
                }`}
                onClick={() => {
                  setCurrentConversationId(conv.id);
                  // Load conversation messages here
                }}
              >
                <span className="conv-title">{conv.title}</span>
                <span className="conv-time">
                  {conv.timestamp.toLocaleDateString()}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="main-header">
          <div className="header-left">
            <h1 className="logo">SMSA Express</h1>
            <span className="tagline">AI-Powered Logistics Intelligence</span>
          </div>
          <div className="header-right">
            <div className="status-indicator">
              <span className="status-dot"></span>
              <span>AI Assistant Online</span>
            </div>
          </div>
        </header>

        <div className="chat-container">
          {/* Agent Selector */}
          <div className="agent-selector-container">
            <div className="agent-tabs">
              <button
                type="button"
                className={`agent-tab ${selectedAgent === "tracking" ? "active" : ""}`}
                onClick={() => {
                  const prevAgent = selectedAgent;
                  setSelectedAgent("tracking");
                  // Clear messages and file when switching from other agents
                  if (prevAgent !== "tracking") {
                    setMessages([]);
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }
                }}
              >
                <span>📦</span> Tracking
              </button>
              <button
                type="button"
                className={`agent-tab ${selectedAgent === "rates" ? "active" : ""}`}
                onClick={() => {
                  const prevAgent = selectedAgent;
                  setSelectedAgent("rates");
                  // Clear messages and file when switching agents
                  if (prevAgent !== "rates") {
                    setMessages([]);
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }
                }}
              >
                <span>💰</span> Rates
              </button>
              <button
                type="button"
                className={`agent-tab ${selectedAgent === "retail" ? "active" : ""}`}
                onClick={() => {
                  const prevAgent = selectedAgent;
                  setSelectedAgent("retail");
                  // Clear messages and file when switching agents
                  if (prevAgent !== "retail") {
                    setMessages([]);
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }
                }}
              >
                <span>📍</span> Retail Centers
              </button>
              <button
                type="button"
                className={`agent-tab ${selectedAgent === "faq" ? "active" : ""}`}
                onClick={() => {
                  const prevAgent = selectedAgent;
                  setSelectedAgent("faq");
                  // Clear messages and file when switching agents
                  if (prevAgent !== "faq") {
                    setMessages([]);
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }
                }}
              >
                <span>❓</span> FAQ
              </button>
            </div>
          </div>

          {/* Chat Messages */}
          <div className="messages-container">
            {messages.length === 0 && (
              <div className="welcome-message">
                <div className="welcome-content">
                  {selectedAgent === "tracking" && (
                    <>
                      <h2>Track Your Shipment</h2>
                      <p>Enter AWB number or upload waybill for instant tracking</p>
                    </>
                  )}
                  {selectedAgent === "rates" && (
                    <>
                      <h2>Get Shipping Rates</h2>
                      <p>Tell me origin, destination, weight, and number of pieces</p>
                    </>
                  )}
                  {selectedAgent === "retail" && (
                    <>
                      <h2>Find Retail Centers</h2>
                      <p>Tell me the city or area you're looking for</p>
                    </>
                  )}
                  {selectedAgent === "faq" && (
                    <>
                      <h2>How Can I Help?</h2>
                      <p>Ask me anything about SMSA services</p>
                    </>
                  )}
                </div>
                <div className="example-hints">
                  {selectedAgent === "tracking" && (
                    <button
                      type="button"
                      className="example-btn"
                      onClick={() => setInput("track AWB 227047923763")}
                    >
                      track AWB 227047923763
                    </button>
                  )}
                  {selectedAgent === "rates" && (
                    <button
                      type="button"
                      className="example-btn"
                      onClick={() => setInput("What's the rate from Riyadh to Jeddah for 5kg?")}
                    >
                      Rate from Riyadh to Jeddah, 5kg
                    </button>
                  )}
                  {selectedAgent === "retail" && (
                    <button
                      type="button"
                      className="example-btn"
                      onClick={() => setInput("Find retail centers in Riyadh")}
                    >
                      Find centers in Riyadh
                    </button>
                  )}
                  {selectedAgent === "faq" && (
                    <button
                      type="button"
                      className="example-btn"
                      onClick={() => setInput("How do I track my shipment?")}
                    >
                      How do I track my shipment?
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="messages-list">
              {messages.map((m) => (
                <div key={m.id} className={`message-bubble ${m.role}`}>
                  {m.fileId && (
                    <div className="file-attachment">
                      <span>📎</span> {m.fileName || "Uploaded file"}
                      {m.extractedData?.awb && (
                        <span className="awb-badge">AWB: {m.extractedData.awb}</span>
                      )}
                    </div>
                  )}
                  {m.messageType === "tracking_result" && m.trackingData ? (
                    <TrackingMessage data={m.trackingData} content={cleanReasoningContent(m.content)} />
                  ) : m.messageType === "retail_result" && m.retailCentersData ? (
                    <RetailCentersMessage data={m.retailCentersData} content={cleanReasoningContent(m.content)} />
                  ) : (
                    <div 
                      className="message-content"
                      dangerouslySetInnerHTML={{ 
                        __html: renderMarkdown(cleanReasoningContent(m.content)) 
                      }}
                    />
                  )}
                </div>
              ))}
              {loadingState !== "idle" && selectedAgent === "tracking" && (
                <TrackingLoadingState stage={loadingState} />
              )}
            </div>
          </div>

          {/* Input Area */}
          <div className="input-area">
            {uploadedFileId && selectedAgent === "tracking" && (
              <div className="uploaded-file-info">
                <span className="file-name">✓ {uploadedFileName}</span>
                <button
                  type="button"
                  className="remove-file"
                  onClick={() => {
                    setUploadedFileId(null);
                    setUploadedFileName(null);
                  }}
                >
                  ×
                </button>
              </div>
            )}
            <div className="input-container">
              {selectedAgent === "tracking" && (
                <>
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
                      if (fileInputRef.current) {
                        fileInputRef.current.value = "";
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="upload-btn"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isUploading}
                    title="Upload waybill image"
                  >
                    {isUploading ? "⏳" : "📎"}
                  </button>
                </>
              )}
              <input
                className="message-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder={
                  uploadedFileId && selectedAgent === "tracking"
                    ? "Ask about the uploaded file..."
                    : selectedAgent === "tracking"
                    ? "Enter AWB number or upload waybill image"
                    : selectedAgent === "rates"
                    ? "e.g. Rate from Riyadh to Jeddah, 5kg"
                    : selectedAgent === "retail"
                    ? "e.g. Find centers in Riyadh"
                    : "Ask your question..."
                }
              />
              <button
                type="button"
                className="send-btn"
                onClick={send}
                disabled={isSending || (!input.trim() && (selectedAgent !== "tracking" || !uploadedFileId))}
              >
                {isSending ? "..." : "→"}
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

