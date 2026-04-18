# MindCX

The most frustrating part of customer support is having to explain your problem all over again.

MindCX is a multi-agent support system that actually remembers its users. It uses three layers of memory across the current conversation, the current session, and the full user history. 

---

## The Problem It Solves

* **Context Rot:** 
Without tiered memory, agents either forget past conversations or stuff the context window with irrelevant history, which degrades response quality and forces users to re-explain themselves on every return visit.

* **Unchecked Autonomy:** 
A single agent has no internal check on its own output. Without a supervisor, an agent can confidently execute the wrong fix or trigger billing actions it shouldn't.

* **The Persistence Gap:** 
Most frameworks handle the "current turn" well but fail to recall user-specific facts across different sessions. The result is a support experience that feels like starting from scratch every time.

Turn context, session summaries, and long-term vector memory run in parallel so the system never loses track of a user across conversations.

---

## How It Works

**Three-Tier Memory Architecture:**
* **The Conversation (Short-Term)**
It keeps the agents focused on the current conversation thread so they don't lose their place between messages.
* **The Session (Mid-Term)**
If a user leaves and returns an hour later, the system uses a Redis-backed summary to pick up exactly where they left off without needing a full recap.
* **The History (Long-Term)**
Using Vector Search, the system remembers past issues and preferences from weeks or months ago. If a user says, "It’s happening again," the agents can recall exactly how it was fixed last time.

**Self-Correcting Quality Loop:** 
Every specialist response must pass a "Quality Lead" supervisor node before reaching the user. If the response hallucinates or misses the user's actual question, the Quality Lead issues a `RETRY` and the graph loops back. A hard cap of 2 retries prevents runaway token burn.

**Taint-and-Suppress Context Isolation:**
If an AI session fails and escalates to a human, we "taint" the cross-session state note with an `[ESCALATED]` prefix. On the user's next visit, the system detects this prefix and suppresses the context, preventing a degraded or confusing previous session from poisoning the new LLM context window.

**Two-Layer Caching:**
During a retry loop, tool calls would otherwise re-execute and burn tokens on data already fetched. Caching results in both GraphState (turn-local) and Redis SessionData (cross-turn) prevents that.


**Evaluation**: Every commit is verified against a Golden Dataset of named test cases covering happy paths, edge cases, and adversarial inputs.

* **Trajectory Assertions:** The eval harness verifies not just the final outcome but the exact sequence of tools the agent called -- catching routing regressions that a simple pass/fail check would miss.
* **Side-Effect Verification:** Tool calls are asserted at the argument level. A billing lookup for the wrong account ID fails the eval, even if the response text looks correct.
* **Adversarial Coverage:** The dataset includes prompt injection attempts, tier-boundary violations (Free users requesting Pro features), cross-user data probes, and escalation hijack attempts.
* **Hybrid Eval Modes:** `EVAL_MODE=mock` runs the full suite offline with zero token cost for CI/CD regression. `EVAL_MODE=live` runs against real LLM calls with Langfuse cost attribution per trace.

**Performance & Cost Optimization**
* **Regex Fast-Pass:** Simple inputs like greetings are caught by a regex check before hitting the LLM. This bypasses the LLM entirely, saving a round-trip on approximately 40% of message exchanges.
* **Token Budgeting:** Large tool payloads, such as extensive billing histories, pass through a budget filter. If a payload is too large, it gets trimmed before reaching the LLM.
* **Model Tiering:** Tasks are routed to the most cost-effective model possible. Lightweight models handle initial triage, while premium reasoning models are reserved exclusively for the Quality Lead supervisor.

**LLM Observability**
* **Tracing:** Every LLM call, tool execution, and routing decision is traced via Langfuse.
* **Metric Attribution:** Every trace captures token consumption, latency, and cost. Traces are tagged by user tier and session ID, so cost and latency can be attributed per user.

---

## Screenshots

**Customer Chat — Billing & Tech Specialists in action**
![Customer Chat](docs/screenshots/chat.png)

**Agent Portal — Escalation queue with human takeover**
![Agent Portal](docs/screenshots/agent.png)


---

## Benchmarks

Live execution across 12 runs: P50 latency 5.18s, TTFT P50 1.52s, total cost $0.00247 per session. 
Wasted spend was $0.00023 — 9.3% of total, absorbed by the retry cap before it compounds.

The Security Probe case is the known outlier. Adversarial inputs trigger a full context rebuild 
and re-route through the Quality Lead, which pushes P95 latency to 23.4s. Every other case 
stays well under 10s. That cost is intentional — early rejection before the specialist layer 
is the next optimization target.

![LLM Agent Telemetry — Latency Distribution](docs/screenshots/benchmark_telemetry.png)

## The Architecture DAG

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
tests/                     # Deterministic Pytest suite (CI/CD regression)
evals/                     # LangChain-based LLMOps evaluation harness
├── golden_dataset.json    # Adversarial & happy-path test cases
├── run.py                 # Live vs. Mock execution runner
└── generate_report.py     # Cost & success rate ASCII/Markdown dashboard
benchmarks/                # Real-world performance telemetry wrapper
└── benchmark_replay.py    # Latency & Token-Cost analysis via astream_events

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
cp .env.example .env
# Add your LLM_API_KEY

docker-compose up --build
```

**Access Points:**
*   Customer chat: `http://localhost:5173`
*   Agent portal:  `http://localhost:5173/agent.html`