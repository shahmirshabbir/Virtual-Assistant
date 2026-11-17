# Decision log

Format: decision, why, what it costs, status. Add new entries at the bottom with a date.

## D1. Learn tool calling by hand before using a framework
Built the raw loop (function -> JSON schema -> model emits tool call -> app executes -> result fed back) before LangGraph, so each LangGraph piece maps to code already understood. Later adopted LangGraph because interviewers expect it and it provides state, checkpointing, and routing.
Status: done.

## D2. LangGraph for orchestration
Gives typed state with reducers, conditional edges, `ToolNode`, checkpointing per `thread_id`, and interrupts. The engine orchestrates only; the LLM only requests tool calls.
Status: adopted.

## D3. LLM: `openai/gpt-oss-120b` on Groq
Gemini free tiers were rate-limited (20/day on one model, several deprecations); Groq free tier worked. Groq is OpenAI-compatible, so switching providers later is cheap. Note `llama-3.3-70b-versatile` was deprecated.
Status: adopted.

## D4. Process first, tools second
Order of design: process map -> intents -> tools -> prompts -> architecture. Prevents building tools nobody needs.
Status: done (`docs/planning/`).

## D5. MVP scope
In: menu/price/availability, business info, delivery zones, customer lookup, create/add/update/remove/cancel order, order status. Deferred: escalation, guardrails, allergy rules, payment-question rules, recommendations, reservations, payment processing, voice, admin dashboard.
Why: get a verified working core first, then harden.
Status: active.

## D6. Single agent, no router yet
12 tools is within the range where tool selection is reliable, and information and order requests share conversation state. A router adds a handoff cost. Revisit when guardrails and escalation land, or when tool count/prompt size makes selection unreliable. Split by cost and complexity, not by CRUD operation.
Status: active.

## D7. Tools are thin HTTP clients over the POS
The POS owns orders, menu, customers, zones. No business logic, pricing or totals in the agent. Endpoint docstrings in the POS are written for agents.
Status: adopted.

## D8. Tool errors are returned as strings, never raised
A POS failure becomes text the LLM can read and explain; the graph does not crash.
Status: adopted.

## D9. Capture system-generated IDs deterministically
`state_capture_node` parses `order_id` from the `create_order` result in code. The LLM is never asked to remember an ID the system produced.
Status: adopted.

## D10. Static info in the prompt, dynamic data behind tools
Hours, delivery fee, tax rate, open/closed are fetched once at startup and put in the system prompt. Prices, availability, order status are always live tool lookups. For a single restaurant the whole menu is small enough for the prompt, but live lookup avoids stale prices and out-of-stock errors. If the knowledge base outgrows the prompt, use retrieval (hybrid search, metadata filters) rather than a bigger prompt; structured tags (`spice_level`, `dietary_tags`) beat embeddings for "something spicy".
Status: adopted.

## D11. Memory model
Working memory = message list + `current_order_id`, checkpointed per `thread_id`. No summarization or sliding window (conversations are short). No history/phone-based personalization for text chat: order tracking requires the customer to supply the order id. Cross-conversation data lives in the POS.
Status: adopted.

## D12. Item edits split into three tools
POS works at line-item level, so `add_order_items`, `update_order_item`, `remove_order_item` mirror it instead of a fake "replace whole order" call.
Status: adopted.

## D13. Auto-confirm on create
`create_order` creates then immediately confirms, matching the "no human for routine requests" goal. Revisit if the owner wants staff review.
Status: assumed, unverified.

## D14. Idempotency
`create_order` sends an `Idempotency-Key` (uuid). Extend to the other write tools.
Status: partial.

## D15. Production hardening comes after the working MVP
Build working agent first, then add: confirmation gate (interrupt), guardrails enforced in code (defense in depth), persistence, observability, tests, deployment. Tackled in the owner's own order rather than the original timeline plan.
Status: active.

## D16. Voice and admin dashboard deprioritized
Text first. Voice (Twilio, STT/TTS) and the dashboard only if time allows.
Status: active.

## D17. Project name is Yavar
Renamed from "Bella Cucina". Old docs and the mock knowledge base still carry the old name; `yavar_agent.py` replaces `bella_cucina_agent_mvp.py`.
Status: done.
