# CLAUDE.md — Yavar (restaurant AI agent)

Read this first. Then read `docs/architecture.md`, `docs/progress.md` and `docs/decisions.md` before making design changes.

## What this project is
Yavar is a production-oriented, text-based AI agent for a single online-only restaurant. It answers customer questions and takes order actions (create, add/update/remove items, cancel, track) by calling a restaurant POS (FastAPI) over HTTP. Voice and other channels come later. The owner (Shahmir) builds it as an AI Engineer at Nextlogixs and it is also his flagship interview project for LLM/agentic-AI production roles. It was formerly called "Bella Cucina"; older docs and `data/restaurant_knowledge_base.json` still use that name.

## Stack
- Python, LangGraph + LangChain, `ChatGroq(model="openai/gpt-oss-120b")`
- Pydantic for input validation, `requests` for POS calls, `python-dotenv` for config
- POS: separate FastAPI service (81 endpoints; the agent uses ~12). Tools are thin HTTP clients, no business logic in the agent.

## Layout
```
yavar_agent.py        graph + CLI runner (agent_node -> ToolNode -> state_capture_node)
tools.py              12 POS-backed tools; exports TOOLS
docs/                 architecture.md, ENDPOINTS.md, progress.md, decisions.md, readiness audit
docs/planning/        process map, 17 intents, tool list, 30-day plan v2, test doc
docs/legacy/          superseded plans and mock-era docs (reference only)
legacy/               milestone 0-2 scripts (Gemini/Groq/mock KB) — do not extend
data/                 old mock knowledge base (superseded by the POS); knowledgeBase.json is an older copy
tests/                pytest suite (empty — to be built)
```
Stray root-level files, not part of Yavar: `ML1.py`, `milestone0.py`, `milestone1_agent_groq.py`, `milestone2.py` (older copies of the `legacy/` scripts; they hardcode an absolute local path to the old KB), an empty `tools/` dir, and `ai_work/` (local venv, git-ignored). Do not extend them; candidates to delete or move into `legacy/`.

## Run
```
pip install -r requirements.txt
cp .env.example .env     # fill GROQ_API_KEY, POS_BASE_URL, POS_API_TOKEN (POS_ACTION_PIN optional)
python yavar_agent.py
```
The POS must be running. First smoke test: "are you open right now?".

## Conventions (follow these)
- Tools never raise. `_pos_request` returns parsed JSON or an error string the LLM can read.
- Write tools validate with Pydantic before calling the POS. `create_order` sends an `Idempotency-Key`.
- System-generated IDs (e.g. `order_id`) are captured in code by `state_capture_node`, never recalled by the LLM.
- Static business info (hours, fees, tax) is fetched once at startup and put in the system prompt; prices, availability and order status are always looked up live through tools.
- The system prompt is rebuilt every turn (stored system messages are filtered out).
- Keep secrets in `.env`, never commit it.
- Tool docstrings are the contract the LLM sees. Change them deliberately and re-test tool selection.

## Working with the owner
- When asked to modify code, give only the modified/updated files, not the whole project.
- He has ML/DL background and learns fast; explain the *why* behind agentic-AI choices, skip basics.
- Scope is MVP: info questions plus all order intents. Deferred on purpose: escalation, guardrails, allergy rules, recommendations, voice, admin dashboard. Do not add them unless asked.
- Update `docs/progress.md` after meaningful work and `docs/decisions.md` when a design decision is made.

## Known gaps (details in docs/progress.md)
Never run end to end against the live POS; no confirmation gate before `create_order`; no guardrails/escalation; `MemorySaver` is in-process only; no logging or tests; `check_delivery_availability` matches zone names (POS has no address-check endpoint).

## Git state (as of 2026-11-19, details in docs/progress.md)
Local `main` and `origin/main` have unrelated histories (local: 2 commits from Aug 2026; remote: `0ad2ae5` with the Yavar files). Local history tracks `.env` (secrets committed), and `.gitignore` only lists `ai_work/`. Do not push, force-push or commit until this is reconciled and `.env` / `apis.txt` are ignored.

## Next step
Verify the MVP against the live POS with a scripted test, then add the confirmation gate (human-in-the-loop interrupt before `create_order`).
