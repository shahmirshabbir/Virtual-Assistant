# Progress

_Last updated: 2026-11-18. Update this file after each meaningful piece of work._

## Done
- Learned and built tool calling by hand (Gemini, then Groq): `legacy/milestone0_*`, `milestone1_*`.
- LangGraph rebuild with `MemorySaver` and deterministic order-id capture: `legacy/milestone2_agent_langgraph.py`.
- Process-first design: process map, 17 intents, tool list (`docs/planning/`).
- MVP scope defined: menu, billing, location and info questions plus all order intents.
- POS integration: 12 thin HTTP-client tools in `tools.py` against the POS API.
- `yavar_agent.py`: POS-backed agent with startup settings fetch, per-turn system prompt, state capture node, CLI.
- Production-readiness audit (`docs/production_readiness_audit.md`) and target architecture (`docs/production_architecture.md`).
- Intro README and this project scaffold for VS Code / Claude Code.

## Not verified
- The POS-backed agent has never been run end to end against the live POS.
- Tool selection across 12 tools is untested, including the add/update/remove item split.
- Pydantic validation path for `create_order` untested against real inputs.
- State isolation between `thread_id`s not tested.
- Whether the POS accepts `Idempotency-Key`, and how confirm behaves, is assumed from `ENDPOINTS.md`.

## Known gaps, by severity
1. **No guardrails:** can be pulled off-topic, may guess on allergy questions, no escalation path. (Deferred by MVP scope; add once the MVP is verified.)
2. **No confirmation gate:** `create_order` relies on the LLM asking the customer to confirm first. Fix: interrupt before the tool runs.
3. **No concurrency model:** single-process CLI, not a service.
4. **No persistence:** `MemorySaver` loses everything on restart.
5. **No observability:** `print` only.
6. **No automated tests.**
7. **Idempotency keys only on `create_order`**, not on the other four write tools.
8. **`check_delivery_availability`** matches the area name against zones; fragile. Needs a POS endpoint that checks an address.
9. **Auto-confirm on create** is assumed; remove the confirm call if staff review is wanted.

## Next up (suggested order)
1. Write a scripted smoke/regression test against the live POS (menu question, full order, add/update/remove item, cancel, status, out-of-stock item, closed restaurant).
2. Confirmation gate (LangGraph `interrupt` before `create_order`).
3. Guardrails: scope, escalation, allergy safety, payment honesty, enforced in code as well as prompt.
4. FastAPI service wrapper so concurrent conversations work.
5. Postgres checkpointer.
6. Structured logging / tracing, pytest suite, CI.
7. Router + branches once guardrails justify it.
8. Docker and deployment.
9. Voice channel (Twilio/STT/TTS), only if time allows.

## Open questions
- Which to do first after verification: confirmation gate or FastAPI service layer? (Suggested: confirmation gate.)
- Should orders auto-confirm, or wait for staff?
- Will the POS get an address-deliverability endpoint?
