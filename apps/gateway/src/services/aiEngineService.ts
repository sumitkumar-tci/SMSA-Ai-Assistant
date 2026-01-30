import axios from "axios";
import { logger } from "../logger";

type ChatMessageRequest = {
  conversationId: string;
  userId?: string;
  message: string;
  explicitIntent?: "TRACKING" | "RATES" | "LOCATIONS" | "FAQ";
  selectedAgent?: "tracking" | "rates" | "retail" | "faq";
};

type TrackingSseEventType = "token" | "done" | "error";

type TrackingSseMetadata = {
  agent: "tracking" | "rates" | "retail" | "faq" | "system";
  timestamp: string;
  conversationId: string;
};

type TrackingSseEvent = {
  type: TrackingSseEventType;
  content: string;
  metadata: TrackingSseMetadata;
};

const AI_ENGINE_URL =
  process.env.AI_ENGINE_URL ?? "http://localhost:8000/orchestrator/chat";

export async function openTrackingStream(
  body: ChatMessageRequest,
  onEvent: (event: TrackingSseEvent) => void
): Promise<void> {
  logger.info("Calling AI engine", { url: AI_ENGINE_URL });

  const response = await axios.post(AI_ENGINE_URL, body, {
    responseType: "stream",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
  });

  const stream = response.data as NodeJS.ReadableStream;

  stream.on("data", (chunk: Buffer) => {
    const text = chunk.toString("utf-8");
    const blocks = text.split("\n\n");

    for (const block of blocks) {
      if (!block.startsWith("data:")) continue;
      const json = block.slice(5).trim();
      if (!json) continue;

      try {
        const event = JSON.parse(json) as TrackingSseEvent;
        onEvent(event);
      } catch (err) {
        logger.error("Failed to parse SSE event from AI engine", err);
      }
    }
  });

  stream.on("error", (err: Error) => {
    logger.error("Error in AI engine SSE stream", err);
  });
}

