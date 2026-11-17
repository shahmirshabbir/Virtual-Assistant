# Yavar (restaurant agent)

An AI agent that takes restaurant customer requests (menu questions, order placement, order changes, order tracking) and carries them out against a real restaurant POS, instead of only answering in chat.

**Status: working MVP, not production-ready.** The core agent loop is built. The safety, persistence, testing and deployment layers are not. See [Current status](#current-status) for the exact list.

---

## Why this project exists

Restaurants lose orders when nobody can answer the phone, when staff re-key orders by hand, and when staff spend time on repetitive questions (hours, prices, delivery fee, "is X available?").

The goal is an agent that handles routine requests end to end and hands off to a human when it cannot. It differs from a chatbot in that it can choose tools, remember the current order across turns, and change real state in the POS.

---

## What the agent does today (MVP scope)

**Information requests**
- Menu questions: items, prices, categories
- Availability of an item
- Business info: hours, open/closed status, default delivery fee, tax rate
- Delivery zones and fees
- Looking up a returning customer by phone number

**Order requests**
- Place an order (collects name, phone, address, payment method)
- Add items to an existing order
- Change the quantity or note on one line item
- Remove an item
- Cancel an order
- Check order status

**Deliberately deferred (not in the MVP)**
- Escalation to a human
- Off-topic / scope guardrail
- Allergy and dietary safety rules
- Payment-question handling rules
- Item recommendations ("something spicy")
- Reservations, payment processing
- Voice (Twilio, speech-to-text, text-to-speech) and the admin dashboard

---

## How it works

```
user message
    |
    v
agent_node ----------------------> final reply (when no tool calls)
 (LLM + system prompt + 12 tools)
    |  tool calls requested
    v
ToolNode  (runs the real Python tool)
    |
    v
state_capture_node  (no LLM: parses tool output, saves current_order_id)
    |
    +--> back to agent_node
```

A checkpointer saves state after every node, keyed by `thread_id`. One `thread_id` is one conversation.

### Key design decisions

| Decision | Reasoning |
|---|---|
| **Raw loop first, then LangGraph** | The tool-calling loop was built by hand before adopting LangGraph, so every LangGraph piece maps to code that was already understood. |
| **Single agent, no router** | 12 tools is within reliable tool-selection range, and info and order requests share conversation state. A router is a later refactor, once guardrails return. |
| **Tools are thin HTTP clients** | The POS owns orders, menu, customers and zones. Tools describe themselves to the LLM and forward calls. No business logic lives in the agent. |
| **Deterministic state capture** | `current_order_id` is parsed from the `create_order` result in code. The LLM is never asked to recall an ID the system generated. |
| **Static info in the prompt, dynamic data behind tools** | Hours, fees and tax rate are fetched once at startup from `/settings`. Prices, availability and order status are always looked up live. |
| **Tool errors return text, not exceptions** | A POS failure becomes something the agent can read and respond to, instead of crashing the graph. |
| **Auto-confirm on create** | `create_order` creates the order, then confirms it immediately, matching the "no human for routine requests" goal. Remove the confirm call if staff review is wanted instead. |
| **Update split into three tools** | The POS works at line-item level, so `add_order_items`, `update_order_item` and `remove_order_item` mirror it rather than faking a "replace the whole order" call. |
| **No summarization or windowing** | A phone-order conversation is short enough that the full message list is fine. |

---

## The 12 tools

| Tool | POS endpoint | Type |
|---|---|---|
| `search_menu` | `GET /menu/items?q=` | read |
| `list_menu` | `GET /menu`, `GET /categories` | read |
| `check_inventory` | `GET /menu/items/{id}` | read |
| `check_order_status` | `GET /orders/{id}` | read |
| `list_zones` | `GET /zones` | read |
| `check_delivery_availability` | `GET /zones` (matched by area name) | read |
| `lookup_customer_by_phone` | `GET /customers/lookup` | read |
| `create_order` | `POST /orders`, `POST /orders/{id}/confirm` | write |
| `add_order_items` | `POST /orders/{id}/items` | write |
| `update_order_item` | `PATCH /orders/{id}/items/{item_id}` | write |
| `remove_order_item` | `DELETE /orders/{id}/items/{item_id}` | write |
| `cancel_order` | `POST /orders/{id}/cancel` | write |

Known gap: the POS has no endpoint that checks whether an address is deliverable. `check_delivery_availability` matches the area name against the zone list, which is fragile for misspelled or ambiguous names. A dedicated POS endpoint would be more reliable.

---

## Tech stack

- **Orchestration:** LangGraph, LangChain
- **LLM:** `openai/gpt-oss-120b` on Groq (free tier, OpenAI-compatible tool calling)
- **Backend it talks to:** the restaurant POS (FastAPI)
- **Validation:** Pydantic
- **Config:** `.env` via python-dotenv

---

## Project files

| File | Purpose |
|---|---|
| `yavar_agent.py` | The agent graph and CLI runner |
| `tools.py` | The 12 POS-backed tools |
| `processes_for_agent.txt` | Process map of how a human takes a phone order, with exceptions and success criteria |
| `intents_for_agent.txt` | 17 intents derived from the process map |
| `final_tool_list.txt` | Tool inventory mapped to intents |
| `production_architecture.md` | Target architecture (router, guardrails, branches) |
| `production_readiness_audit.md` | Audit of the MVP against production attributes |

---

## Running it

```bash
pip install langchain langchain-groq langgraph pydantic python-dotenv requests
```

Create a `.env` next to the scripts:

```
GROQ_API_KEY=...
POS_BASE_URL=http://localhost:8000
POS_API_TOKEN=...
POS_ACTION_PIN=...        # optional, sent on cancel_order if set
```

The POS must be running and reachable first. Then:

```bash
python yavar_agent.py
```

First smoke test: ask "are you open right now?". It confirms the settings fetch and prompt construction work before any order data is touched.

---

## Current status

**Built**
- Agent graph with tool calling, multi-turn memory and deterministic order-ID capture
- 12 POS-backed tools
- Process map, intent taxonomy, tool list and architecture docs

**Not yet verified**
- The POS-backed version has not been run end to end against the live POS.
- Tool selection across 12 tools, and the new three-way item-edit split, is untested.

**Known gaps (see `production_readiness_audit.md`), roughly by severity**
1. No guardrails: the agent can be talked off-topic, may guess on allergy questions, and has no escalation path.
2. No code-level confirmation gate: `create_order` relies on the LLM choosing to confirm with the customer first.
3. No concurrency model: it is a single-process CLI, not a service.
4. No persistence: `MemorySaver` is in-process, so a restart loses all conversations.
5. No observability: `print` statements only, no structured logs or tracing.
6. No automated tests.
7. Idempotency keys exist on `create_order` only, not on the four other write tools.

---

## Roadmap

1. **Verify the MVP** against the live POS with a written test script.
2. **Confirmation gate:** a human-in-the-loop interrupt before `create_order` runs.
3. **Guardrails:** scope, escalation, allergy safety and payment honesty, with code-level enforcement as well as prompt rules.
4. **Service layer:** wrap the graph in FastAPI so concurrent conversations are possible.
5. **Persistence:** a Postgres-backed checkpointer.
6. **Observability and tests:** structured logging, tracing, a pytest suite and CI.
7. **Router and branches** once guardrails and scale justify them.
8. **Containerization and deployment.**
9. **Voice channel**, if time allows.
