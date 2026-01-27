## SMSA AI Assistant – Project Overview & Milestones

This repository implements the SMSA Express AI Assistant as described in:

- `reference/cursor_BUILD_PROMPT.md` – enterprise build requirements
- `reference/smsa_ai_architecture-v8 (1).md` – system architecture

It is a monorepo with three main apps:

- `apps/web` – Next.js chat UI (web client)
- `apps/gateway` – Node/Express API gateway (SSE, security, routing)
- `apps/ai-engine` – Python/FastAPI AI engine (orchestrator + agents)

The goal is to build an **enterprise-grade, multi-agent AI assistant** with tracking, rates, service centers, FAQ/RAG, file upload, and integrations with SMSA + Deepseek.

---

## Phase 0 – Foundation & Tracking Agent (DONE)

**Objective:** Get one agent (Tracking) working end-to-end with real SMSA data, on top of the correct architecture skeleton.

- **Monorepo setup**
  - `package.json`, `pnpm-workspace.yaml`, `turbo.json`
  - `apps/web`, `apps/gateway`, `apps/ai-engine`, `packages/types`
- **Tracking Agent (Agent 1)**
  - `apps/ai-engine/src/agents/tracking.py` – `TrackingAgent` (extends `BaseAgent`)
  - `apps/ai-engine/src/services/smsa_apis.py` – real SOAP client for:
    - `getSMSATrackingDetails` at `http://smsaweb.cloudapp.net:8080/track.svc`
    - Parses `TrackRslt` events (`EventDesc`, `Office`, `EventTime`, `StatusCode`)
  - `TrackingResult` model with:
    - Enum status: `PENDING | IN_TRANSIT | OUT_FOR_DELIVERY | DELIVERED | EXCEPTION | UNKNOWN`
    - `currentLocation`, `checkpoints`, `rawResponse`, `errorCode`, `errorMessage`
  - Rich output:
    - Current status + location
    - Last update timestamp
    - Recent shipment history (events)
- **AI Engine**
  - `orchestrator/intent_classifier.py` – `Intent` enum + `IntentClassifier`
  - `orchestrator/router.py` – `AIOrchestrator` + `route_message(context)`
  - `services/response_generator.py` – tracking response formatting
  - `config/settings.py` – config skeleton (env-driven settings)
  - `logging_config.py` – structlog for structured logging
- **Gateway**
  - `src/index.ts` – Express app (`/api` namespace, CORS, helmet)
  - `src/routes/chat.ts` – `POST /api/messages/:conversationId/stream` (SSE)
  - `src/services/aiEngineService.ts` – streams SSE from AI engine
- **Web App**
  - `app/page.tsx` – minimal but modern chat UI:
    - Shows conversation, “Tracking agent • Online”
    - Calls gateway SSE endpoint and renders streaming responses
- **Docs & Tests**
  - `docs/tracking-agent.md` – architecture + flow for tracking
  - Basic tests for tracking agent, gateway route, and web page

Result:  
From the web UI you can send `track AWB 227047923763` or `track AWB 291567798859` and see **live SMSA tracking status + history** end-to-end.

---

## Phase 1 – Hardening Tracking & Config

**Objective:** Make the tracking flow production-ready while keeping scope to one agent.

**Milestones:**

1. **Error handling / UX**
   - Map SMSA errors to user-friendly messages:
     - AWB not found, auth failures, timeouts, parse errors.
   - Ensure chat never shows raw stack traces or cryptic messages.

2. **Config & secrets**
   - Move all SMSA config to `settings.py` + `.env`:
     - `SMSA_TRACKING_BASE_URL`, `SMSA_TRACKING_USERNAME`, `SMSA_TRACKING_PASSWORD`
     - Timeouts and retry policy
   - No hardcoded secrets in code.

3. **Logging**
   - Log at least:
     - `agent`, `intent`, `awb`, `conversation_id`, `status`, `latency_ms`
   - Keep XML logging to dev/debug only (avoid full XML in prod logs).

4. **Tests**
   - Add tests for:
     - Return case (`RTS`), in-transit case (`HOP/HIP/AF`)
     - Error cases (simulated SOAP faults, network errors)

---

## Phase 2 – Specialized Agents Skeletons (Rates, Retail, FAQ)

**Objective:** Create clean, well-named skeletons for all agents and their service clients, without full business logic.

**Milestones:**

1. **Rates Agent**
   - `agents/rates.py` – `RatesAgent(BaseAgent)` with a documented `run(context)` stub.
   - `services/smsa_apis.py` – `SMSARatesClient` stub:
     - Points to `https://mobileapi.smsaexpress.com/SmsaMobileWebServiceRestApi/api/RateInquiry/inquiry`
     - Uses passkey `riai$ervice` (from env).

2. **Retail Centers Agent**
   - `agents/retail.py` – `RetailCentersAgent(BaseAgent)` stub.
   - `services/smsa_apis.py` – `SMSAServiceCenterClient` stub:
     - Points to `https://mobileapi.smsaexpress.com/smsamobilepro/retailcenter.asmx`
     - Uses passkey `rcai$ervice` (from env).

3. **FAQ Agent / RAG Skeleton**
   - `agents/faq.py` – stub that returns “FAQ agent not implemented yet; will answer from knowledge base.”
   - `services/vector_db.py` – `VectorDBClient` stub with `upsert_documents` + `search_similar`.

4. **Prompts & Instructions**
   - `prompts/rates_agent_prompt.txt`
   - `prompts/retail_agent_prompt.txt`
   - `prompts/faq_agent_prompt.txt`
   - Each describes role, limitations, tone, and expected output shape.

At the end of this phase you can walk through **all agents** in code and show where each will be implemented, even if only tracking is live.

---

## Phase 3 – Smarter Orchestration & Deepseek Intent

**Objective:** Move from keyword-only intent classification to a Deepseek-backed router and central context assembly.

**Milestones:**

1. **Deepseek Intent Client**
   - `services/deepseek_intent.py`:
     - `class DeepseekIntentClient`
     - Methods:
       - `classify_intent(message: str) -> Intent`
       - (Later) `route_to_llm(...)` for complex reasoning.

2. **IntentClassifier integration**
   - Update `IntentClassifier` to:
     - Use heuristics for simple messages.
     - Call `DeepseekIntentClient` for ambiguous/complex cases (Phase 2).

3. **Context assembly**
   - Centralize conversation + file context building in `AIOrchestrator.handle`:
     - `context["conversation"] = { id, messages, ... }`
     - `context["files"] = { uploaded, extracted_data }`

---

## Phase 4 – File Upload & Vision Pipeline (Skeleton)

**Objective:** Put the file pipeline in place so images/SAWB docs can be used as context (even before Vision is wired).

**Milestones:**

1. **Gateway upload route**
   - `POST /api/upload`:
     - Accepts file, validates type/size.
     - For now, stores locally or in a simple stub.
     - Returns `{ fileId, filename, mimetype }`.

2. **Storage service**
   - `services/storage.py`:
     - `store_file_metadata`, `get_file_metadata`, with docstrings describing S3/MinIO usage.

3. **Vision skeleton**
   - `services/deepseek_vision.py` stub:
     - `analyze_image(file_url, prompt)` for future Vision integration.

4. **Context wiring**
   - Ensure orchestrator adds file metadata into `context["files"]` for agents that need it.

---

## Phase 5 – Security, Auth & Rate Limiting (Baseline)

**Objective:** Add the essential security hooks to the gateway and engine.

**Milestones:**

1. **Gateway**
   - CORS configured for allowed origins (e.g. `ai.smsaexpress.com`).
   - Basic IP rate limiting (even in-memory) to prevent abuse.
   - `authMiddleware` stub:
     - For now, sets a demo `req.user = { id: "demo" }`.
     - Later, validate JWT / cookies.

2. **AI Engine**
   - Ensure no sensitive data is logged.
   - Add simple health endpoint (`/health`) for liveness checks.

---

## Phase 6 – Memory Layer & RAG (Minimum Viable)

**Objective:** Introduce MongoDB + vector DB to support conversation history and FAQ/RAG.

**Milestones:**

1. **MongoDB integration (skeleton)**
   - `services/db.py`:
     - `create_conversation(user_id) -> conversation_id`
     - `save_message(conversation_id, message)`
     - `get_conversation_history(conversation_id, limit) -> list[dict]`
   - Orchestrator uses `get_conversation_history` to populate context for agents.

2. **Vector DB (Qdrant) skeleton**
   - `VectorDBClient` wired to env config for Qdrant URL/API key.
   - FAQ agent uses `VectorDBClient.search_similar` for semantic recall (with stubbed data until embeddings are generated).

---

## Phase 7 – Frontend Experience & Multi-Language

**Objective:** Bring the web UI closer to the design in the build prompt: chatGPT-like, multi-language, mobile-first.

**Milestones:**

1. **Conversation management**
   - Add a sidebar with:
     - Conversation list
     - New conversation, rename, delete
   - Pass `conversationId` consistently from UI → gateway → AI engine.

2. **Multi-language / RTL**
   - Integrate a basic i18n framework.
   - Support English now, prepare structure for Arabic + RTL.

3. **UI polish**
   - Replace basic components with Tailwind + shadcn/Radix UI.
   - Ensure layout matches “independent page like ChatGPT” requirement.

---

## How to Work With These Phases

- Treat each phase as a **milestone** you can show to the client.
- Never break the existing tracking flow; build new capabilities **around** the stable Agent 1.
- Use `docs/` to keep short, high-level explanations of:
  - What’s implemented.
  - What’s stubbed.
  - What’s coming next.

This README is your roadmap from **working tracking demo** to the **full enterprise AI assistant** described in the reference documents.

