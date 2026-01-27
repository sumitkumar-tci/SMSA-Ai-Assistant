export type TrackingIntent = "TRACKING";

export interface ChatMessageRequest {
  conversationId: string;
  userId?: string;
  message: string;
  explicitIntent?: TrackingIntent;
}

export interface TrackingRequestPayload {
  awbs: string[];
  language?: "en" | "ar";
}

export interface TrackingCheckpoint {
  timestamp: string;
  location: string;
  description: string;
  statusCode?: string;
}

export type TrackingStatus =
  | "PENDING"
  | "IN_TRANSIT"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "EXCEPTION"
  | "UNKNOWN";

export interface TrackingResult {
  awb: string;
  status: TrackingStatus;
  currentLocation?: string;
  eta?: string;
  checkpoints: TrackingCheckpoint[];
  rawResponse?: unknown;
  errorCode?: string;
  errorMessage?: string;
}

export type SseEventType = "token" | "done" | "error";

export interface TrackingSseMetadata {
  agent: "tracking";
  timestamp: string;
  conversationId: string;
}

export interface TrackingSseEvent {
  type: SseEventType;
  content: string;
  metadata: TrackingSseMetadata;
}

