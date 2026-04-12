# MindCX

The most frustrating part of customer support is having to explain your problem all over again.

MindCX is a multi-agent support system that actually remembers its users. It uses three layers of memory to keep track of past conversations, user preferences, and previous fixes. 

---

## The Problem It Solves

Even in the era of autonomous agents, most support systems struggle to survive real-world production. They suffer from three specific architectural flaws:

* **Context Rot:** 
Without tiered memory, agents either forget the past or bloat their context window with irrelevant history. This "noise" degrades reasoning, forcing users to re-explain their problems every time they return.

* **Unchecked Autonomy:** 
Single-agent systems often experience silent drift. Without a supervisor node to audit decisions, an agent may confidently execute incorrect technical steps or trigger unauthorized billing actions.

* **The Persistence Gap:** 
Most frameworks handle the "current turn" well but fail to recall user-specific facts across different sessions. This lack of long-term episodic memory leads to a fragmented and impersonal customer experience.

MindCX replaces the single all-purpose agent with a coordinated team of specialists governed by a Quality Lead. This ensures every decision is grounded in persistent, verified context that spans days, not just minutes.

## Screenshots

**Customer Chat — Billing & Tech Specialists in action**
![Customer Chat](docs/screenshots/chat.png)

**Agent Portal — Escalation queue with human takeover**
![Agent Portal](docs/screenshots/agent.png)

---

## Core Infrastructure

The hardest engineering challenges in MindCX aren't the LLM prompts—they are the underlying state management and orchestration mechanics:

**Three-Tier Memory Architecture:**
* **The Conversation (Short-Term)**
Handles the "right now." It keeps the agents focused on the current conversation thread so they don't lose their place between messages.
* **The Session (Mid-Term)**
Handles the "today." If a user leaves and returns an hour later, the system uses a Redis-backed summary to pick up exactly where they left off without needing a full recap.
* **The History (Long-Term)**
Handles the "forever." Using Vector Search, the system remembers past issues and preferences from weeks or months ago. If a user says, "It’s happening again," the agents can recall exactly how it was fixed last time.

**Self-Correcting Quality Loop:** 
Every specialist response must pass a "Quality Lead" supervisor node before reaching the user. If the specialist hallucinates or diverges from the user's exact question, the Quality Lead issues a `RETRY` and the graph loops back. A hard cap of 2 retries prevents runaway token burn.

**Taint-and-Suppress Context Isolation:**
If an AI session fails and escalates to a human, we "taint" the cross-session state note with an `[ESCALATED]` prefix. On the user's next visit, the system detects this prefix and suppresses the context, preventing a degraded or confusing previous session from poisoning the new LLM context window.

**Two-Layer Caching:**
Tool calls (like pulling billing history) are cached in the `GraphState` (turn-local) and in Redis `SessionData` (cross-turn). By caching tool results both locally in the turn and globally in Redis, we prevent expensive redundant API calls and save the LLM from burning tokens regenerating the same data if a Retry loop is triggered.

**Performance & Cost Optimization**
* **Regex Fast-Pass:** Trivial inputs (greetings or acknowledgments) are intercepted by a lightweight heuristic. This bypasses the LLM entirely, saving a round-trip on approximately 40% of message exchanges.
* **Token Budgeting:** Large tool payloads, such as extensive billing histories, pass through a budget filter. If a payload exceeds the threshold, it is automatically truncated to prevent context window bloat and runaway token costs.
* **Model Tiering:** Tasks are routed to the most cost-effective model possible. Lightweight models handle initial triage, while premium reasoning models are reserved exclusively for the Quality Lead supervisor.

**LLM Observability**
* **Granular Tracing:** Every node in the graph is instrumented via Langfuse. We trace every LLM generation, tool execution, and routing decision in real-time.
* **Metric Attribution:** Every trace captures token consumption, latency, and cost. Data is tagged by user tier and session ID to eliminate production blind spots and allow for precise cost-per-user analysis.

---

## The Architecture DAG

The system backbone is compiled via `StateGraph` and executed as an async streaming pipeline. Every LLM invocation, tool call, and routing decision flows back to the React client as granular WebSocket events.

```
User ──WebSocket──▶ Concierge ──intent──▶ Billing Specialist
                                    └────▶ Tech Specialist
                                                │
                                          Quality Lead
                                         ╱     │      ╲
                                      PASS   RETRY   ESCALATE
                                       │       │        │
                                      END    re-run   FIFO Queue ──▶ Human Agent
```

---

## Project Structure

```
backend/
├── agent/
│   ├── graph.py          # LangGraph DAG: concierge → specialists → quality lead
│   ├── memory.py         # Embedding-based semantic memory (search + add + prune)
│   ├── summarization.py  # Cross-session state note generation with conflict reconciliation
│   └── context.py        # Builds the 5-section context window for every LLM call
├── api/
│   ├── websocket.py      # WebSocket endpoint with astream_events, Langfuse tracing
│   └── escalation.py     # HITL queue, takeover, agent messaging, session resolution
├── llm/
│   └── client_factory.py # Provider-agnostic LLM initialization (Gemini/OpenAI/Anthropic)
├── session/
│   └── manager.py        # Redis session CRUD, state note taint/suppress, stale ID pruning
└── db/
    └── models.py         # SQLAlchemy models: Account, Billing, Outage, Memory (embeddings)

frontend/                  # React + TypeScript (Vite MPA)
├── src/
│   ├── App.tsx            # Customer portal entry
│   ├── AgentApp.tsx       # Agent portal entry (RBAC-gated)
│   ├── pages/
│   │   ├── ChatView.tsx   # Real-time chat with live observability sidebar + trace export
│   │   ├── EscalationDashboard.tsx  # FIFO queue viewer, takeover controls, agent reply
│   │   └── LogsView.tsx   # Session browser with routing trace + full transcript replay
```

---

## Stack

| Layer | Tech |
|---|---|
| Orchestration | LangGraph `StateGraph`, LangChain Core |
| LLMs | Gemini (default), OpenAI, Anthropic — hot-swappable via YAML config |
| Embeddings | `gemini-embedding-001` / OpenAI embeddings |
| Backend | FastAPI, WebSockets, Pydantic v2 |
| State | Redis (sessions, locks, escalation queue, state notes) |
| Storage | SQLite + SQLAlchemy (accounts, vector memories) |
| Observability | Langfuse (Graph tracing, token usage, latency metrics) |
| Frontend | React 18, TypeScript, Vite MPA |

---

## Running It

```bash
cp backend/config/.env.example backend/config/.env
# Add your GEMINI_API_KEY (or OPENAI_API_KEY)

docker-compose up --build
```

**Access Points:**
*   Customer chat: `http://localhost:5173`
*   Agent portal:  `http://localhost:5173/agent.html`

Test Accounts:
*  `admin@mindcx.ai` / `mindcx2026` (agent)
*  `jonny@startup.inc` / `mindcx2026` (customer)
