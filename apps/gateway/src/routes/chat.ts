import express, { Request, Response } from "express";
import { openTrackingStream } from "../services/aiEngineService";
import { logger } from "../logger";

type ChatMessageRequest = {
  conversationId: string;
  userId?: string;
  message: string;
  explicitIntent?: "TRACKING";
};

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

export const router = express.Router();

router.post(
  "/messages/:conversationId/stream",
  async (req: Request, res: Response) => {
    const conversationId = req.params.conversationId;

    const body: ChatMessageRequest = {
      conversationId,
      message: req.body?.message ?? "",
    };

    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });

    try {
      await openTrackingStream(
        body,
        (event: TrackingSseEvent): void => {
          res.write(`data: ${JSON.stringify(event)}\n\n`);

          if (event.type === "done" || event.type === "error") {
            res.end();
          }
        }
      );
    } catch (err) {
      logger.error("Gateway failed to open tracking stream", err);
      const errorEvent: TrackingSseEvent = {
        type: "error",
        content: "Failed to connect to AI engine.",
        metadata: {
          agent: "tracking",
          timestamp: new Date().toISOString(),
          conversationId,
        },
      };
      res.write(`data: ${JSON.stringify(errorEvent)}\n\n`);
      res.end();
    }
  }
);

