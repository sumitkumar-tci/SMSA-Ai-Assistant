# SMSA Express AI Assistant

Enterprise-grade AI assistant for SMSA Express, providing intelligent customer service for shipment tracking, rate inquiries, retail center locations, and FAQ support.

## System Architecture

### High-Level Overview

```
┌─────────────────┐
│   Web Client    │  Next.js (Port 3000)
│  (Next.js/React)│
└────────┬────────┘
         │ HTTPS/SSE
         ▼
┌─────────────────┐
│  API Gateway    │  Express.js (Port 3001)
│  (Node.js)      │  - Request Routing
│                 │  - SSE Streaming
│                 │  - File Upload Proxy
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   AI Engine     │  FastAPI (Port 8000)
│   (Python)      │  - LangGraph Orchestration
│                 │  - Intent Classification
│                 │  - Multi-Agent System
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    ▼         ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Tracking│ │ Rates  │ │ Retail │ │  FAQ   │
│ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │
└───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
    │          │          │          │
    ▼          ▼          ▼          ▼
┌─────────────────────────────────────────┐
│      External Services                  │
│  - SMSA APIs (SOAP/REST)                │
│  - Qwen LLM (Text & Vision)             │
│  - Huawei OBS (File Storage)            │
└─────────────────────────────────────────┘
```

### Data Flow

**Tracking Request Example:**
1. User types "track AWB 227047923763" in web UI
2. Web app sends POST to Gateway `/api/messages/:conversationId/stream`
3. Gateway forwards to AI Engine `/orchestrator/chat` with SSE streaming
4. Orchestrator classifies intent (TRACKING) and routes to Tracking Agent
5. Tracking Agent calls SMSA SOAP API for real-time shipment data
6. Agent formats response using Qwen LLM for user-friendly output
7. Response streams back through Gateway to Web UI in real-time

**File Upload Flow:**
1. User uploads waybill image via web UI
2. Gateway receives file and forwards to AI Engine `/upload`
3. AI Engine uploads file to Huawei OBS (Object Storage)
4. Vision API (Qwen-VL) extracts AWB and shipment details from image
5. If AWB detected, automatically triggers tracking
6. Returns extracted data and tracking results to frontend

## Technology Stack

### Frontend
- **Framework:** Next.js 14 (React)
- **Styling:** Tailwind CSS
- **Communication:** Server-Sent Events (SSE) for streaming

### API Gateway
- **Runtime:** Node.js with Express.js
- **Features:** Request routing, SSE proxying, file upload handling

### AI Engine
- **Framework:** FastAPI (Python)
- **Orchestration:** LangGraph for stateful agent workflows
- **LLM:** Qwen3-32B (Text) + Qwen3-VL-32B (Vision) via Huawei ModelArts
- **Storage:** Huawei OBS (Object Storage Service)

### External Integrations
- **SMSA Tracking API:** SOAP endpoint for real-time shipment tracking
- **SMSA Rates API:** REST endpoint for shipping rate inquiries
- **SMSA Retail Centers API:** SOAP endpoint for service center locations
- **Huawei ModelArts:** Qwen LLM and Vision model APIs
- **Huawei OBS:** S3-compatible object storage for files and context

## Implementation Phases

### Phase 0: Foundation ✅ **Complete**
- Monorepo structure (web, gateway, ai-engine)
- Tracking Agent with real SMSA SOAP API integration
- Rates Agent with real SMSA REST API integration
- Basic UI with agent selector and SSE streaming
- Orchestrator with LangGraph workflow
- Intent classification (keyword-based with LLM fallback)

### Phase 2: Specialized Agents ✅ **Complete**
- **Tracking Agent:** Real-time shipment tracking via SMSA SOAP API
  - AWB extraction from text and images
  - Status mapping (PENDING, IN_TRANSIT, DELIVERED, etc.)
  - LLM-generated user-friendly responses
- **Rates Agent:** Shipping rate inquiries via SMSA REST API
  - City, weight, and pieces extraction
  - LLM-generated response formatting
- **Retail Centers Agent:** Service center lookup via SMSA SOAP API
  - City-based search
  - LLM-generated location responses
- **FAQ Agent:** Knowledge base queries with Qwen LLM
  - FAQ data context from JSONL files
  - LLM-generated answers (Vector DB pending)

### Phase 3: LLM Integration ✅ **Complete**
- Qwen LLM Client for text generation
- All agents use LLM for response formatting
- Intent classifier with LLM fallback for ambiguous queries
- Vision Client (Qwen-VL) for image analysis and OCR

### Phase 4: File Upload & Vision ✅ **Complete**
- **Huawei OBS Integration:**
  - Official Huawei OBS SDK (`esdk-obs-python`)
  - File upload and retrieval
  - Conversation context storage
- **Vision API Integration:**
  - AWB extraction from SAWB document images
  - Automatic tracking when AWB is detected
  - Image processing with Qwen-VL model
- **File Context Management:**
  - Files stored in Huawei OBS
  - Extracted data linked to conversations
  - File metadata tracking

### Phase 1: Hardening 🔄 **In Progress (80%)**
- Basic error handling implemented
- Configuration management via environment variables
- Structured logging with structlog
- Production-grade error mapping (pending)
- Comprehensive test suite (pending)

### Phase 6: Memory Layer 🔄 **In Progress (30%)**
- Database manager skeleton (MongoDB/DDS)
- MongoDB connection (pending connection string)
- Vector DB integration (PostgreSQL with pgvector - pending)
- RAG pipeline for FAQ (pending vector DB)

### Phase 7: Frontend Polish 🔄 **In Progress (50%)**
- Modern chat UI implemented
- Agent selector functional
- File upload UI complete
- Multi-language support (Arabic + RTL - pending)
- Conversation management UI (pending)

### Phase 5: Security & Auth ❌ **Not Started**
- JWT authentication (pending)
- Rate limiting (pending)
- Security hardening (pending)
- API key management (pending)

## Current Status

### ✅ Working Features
- **All 4 Agents Functional:** Tracking, Rates, Retail Centers, FAQ
- **LLM Integration:** All agents use Qwen for response generation
- **File Upload:** Huawei OBS integration working
- **Vision Processing:** AWB extraction from images with auto-tracking
- **Real-time Streaming:** SSE-based response streaming
- **Multi-Agent Orchestration:** LangGraph workflow operational

### ⏳ Pending Integrations
- **MongoDB/DDS:** Waiting for connection string
- **Vector DB:** Waiting for PostgreSQL setup with pgvector
- **Security:** JWT authentication and rate limiting (Phase 5)
- **Multi-language:** Arabic language support (Phase 7)

## Project Structure

```
SMSA-Ai-Assistant/
├── apps/
│   ├── web/              # Next.js frontend
│   ├── gateway/          # Express.js API gateway
│   └── ai-engine/        # FastAPI AI engine
│       └── src/
│           ├── agents/    # Specialized agents (tracking, rates, retail, faq)
│           ├── orchestrator/  # LangGraph workflow and intent classification
│           ├── services/      # External service clients (SMSA, LLM, OBS, Vision)
│           └── config/       # Configuration management
├── packages/
│   └── types/            # Shared TypeScript types
└── data_for_faq/         # FAQ knowledge base (JSONL)
```

## Configuration

All configuration is managed via environment variables in `.env` file at project root:

- **SMSA APIs:** Tracking, Rates, Retail Centers credentials
- **Qwen LLM:** API key, endpoints, model names
- **Huawei OBS:** Access key, secret key, endpoint, bucket name
- **Database:** MongoDB connection string (pending)

## Development Setup

### Prerequisites
- Python 3.11+ (for AI Engine)
- Node.js 18+ (for Gateway and Web)
- pnpm (package manager)

### Running Locally

**Terminal 1 - AI Engine:**
```bash
cd apps/ai-engine
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 - Gateway:**
```bash
cd apps/gateway
npx ts-node-dev --respawn src/index.ts
```

**Terminal 3 - Web App:**
```bash
cd apps/web
npm run dev
```

Access the application at `http://localhost:3000`

## Key Features

1. **Multi-Agent Architecture:** Specialized agents for different domains (tracking, rates, locations, FAQ)
2. **LLM-Powered Responses:** All agents use Qwen LLM for natural, user-friendly responses
3. **Vision Processing:** Automatic AWB extraction from waybill images
4. **Real-time Streaming:** SSE-based streaming for responsive user experience
5. **Enterprise Integration:** Direct integration with SMSA APIs for real-time data
6. **File Management:** Secure file storage and processing via Huawei OBS

## Notes

- **Rates API:** Some routes may return empty arrays - this is normal SMSA API behavior for unavailable routes
- **FAQ Agent:** Currently uses keyword search with JSONL data; will upgrade to Vector DB semantic search when available
- **Vision API:** Successfully extracts AWB and automatically tracks shipments
- **Response Optimization:** LLM responses are optimized for conciseness and clarity

---

**Status:** Core functionality complete. Ready for database integration and security hardening when credentials are available.
