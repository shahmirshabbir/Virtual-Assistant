"""
yavar_agent.py

Yavar MVP agent (formerly "Bella Cucina"). This is the deliberately-scoped MVP build — no
router, no guardrails, no cross-call memory beyond what the POS itself
provides via lookup_customer_by_phone.

UPDATED to use the POS-backed tools.py (12 tools, thin HTTP clients
over the real restaurant POS) instead of the earlier mock/in-memory
version. Key differences from the previous version of this file:

  - No more restaurant_knowledge_base.json / RESTAURANT_INFO import —
    the POS owns that data now. Static system-prompt content (business
    name, hours, delivery fee, tax rate) is fetched ONCE at startup via
    GET /settings and GET /settings/status, not re-fetched every turn
    (same "static vs tool-backed" reasoning as before — this data
    rarely changes within a single conversation).
  - update_order is gone — replaced by add_order_items,
    update_order_item, remove_order_item, matching the POS's
    item-level endpoints.
  - New tools available: list_zones, check_delivery_availability,
    lookup_customer_by_phone.
  - state_capture_node is UNCHANGED — create_order still returns
    {"order_id": ..., "display_text": ...} JSON, so deterministic
    extraction still works exactly as before.

Setup:
  pip install langchain langchain-groq langgraph pydantic python-dotenv requests
  .env: GROQ_API_KEY=..., POS_BASE_URL=..., POS_API_TOKEN=...
  tools.py in the same folder.
"""

import json
import os
import uuid
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from tools import TOOLS, _pos_request

load_dotenv()


# ---------------------------------------------------------------------------
# AgentState — unchanged from before.
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    current_order_id: str | None


# ---------------------------------------------------------------------------
# Fetch static restaurant info ONCE at startup from the POS, instead of
# a local knowledge base file. Same principle as before: rarely-changing
# facts go in the prompt, not re-fetched via tool call every turn.
# ---------------------------------------------------------------------------

def fetch_restaurant_static_info() -> dict:
    settings = _pos_request("GET", "/settings")
    status = _pos_request("GET", "/settings/status")
    if isinstance(settings, str):
        settings = {}
    if isinstance(status, str):
        status = {}
    return {**settings, **status}


# ---------------------------------------------------------------------------
# System prompt — rebuilt from POS settings instead of a local JSON file.
# Still one f-string for MVP scope (guardrail-driven 8-file composition
# is deferred, per the earlier architecture decision).
# ---------------------------------------------------------------------------

def build_system_prompt(static_info: dict, current_order_id: str | None) -> str:
    business_name = static_info.get("business_name", "the restaurant")
    currency = static_info.get("currency", "")
    tax_rate = static_info.get("tax_rate")
    delivery_fee = static_info.get("default_delivery_fee")
    open_time = static_info.get("open_time")
    close_time = static_info.get("close_time")
    accepting_orders = static_info.get("accepting_orders")
    open_now = static_info.get("open_now")

    hours_line = f"Hours: {open_time} - {close_time}." if open_time and close_time else ""
    status_line = (
        f"The restaurant is currently {'OPEN and accepting orders' if accepting_orders and open_now else 'CLOSED or not currently accepting orders'}."
    )
    fee_line = f"Default delivery fee: {delivery_fee} {currency}." if delivery_fee is not None else ""
    tax_line = f"Tax rate: {tax_rate}%." if tax_rate is not None else ""

    order_context = (
        f"\nThe customer's current order in this call is {current_order_id}. "
        f"Use this order_id for add_order_items/update_order_item/"
        f"remove_order_item/cancel_order/check_order_status requests "
        f"without asking the customer to repeat it."
        if current_order_id else ""
    )

    return f"""You are the ordering assistant for {business_name}.

{hours_line}
{status_line}
{fee_line}
{tax_line}

Tool-usage rules:
- NEVER state a menu price, item availability, zone/delivery fee, or
  order status from memory — always use the corresponding tool, since
  this data lives in the POS and can change.
- Before creating an order, resolve item names to menu_item_id via
  search_menu, and confirm availability via check_inventory.
- Before confirming a delivery order, check the customer's area via
  check_delivery_availability.
- create_order requires the customer's name, phone, delivery address,
  and payment_method ('cash' or 'online') — collect all of these
  before calling it.
- To change an order already placed: use add_order_items to add new
  items, update_order_item to change quantity/note on an existing
  line, remove_order_item to delete a line. There is no single
  "replace the whole order" tool — use the one matching what the
  customer actually wants changed.
- If a customer gives their phone number, you can call
  lookup_customer_by_phone to check if they're a returning customer
  with a saved address.
- Be concise and friendly, like a real restaurant staff member.{order_context}
"""


# ---------------------------------------------------------------------------
# Nodes.
# ---------------------------------------------------------------------------

def _build_llm():
    return ChatGroq(model="openai/gpt-oss-120b", api_key=os.environ["GROQ_API_KEY"]).bind_tools(TOOLS)


def make_agent_node(static_info: dict):
    """Returns an agent_node closure carrying the static_info fetched
    once at startup, so we don't re-call GET /settings every turn."""

    def agent_node(state: AgentState) -> AgentState:
        llm = _build_llm()
        system_msg = {
            "role": "system",
            "content": build_system_prompt(static_info, state.get("current_order_id")),
        }
        messages_for_llm = [system_msg] + [m for m in state["messages"] if m.type != "system"]
        response = llm.invoke(messages_for_llm)
        return {"messages": [response]}

    return agent_node


def state_capture_node(state: AgentState) -> AgentState:
    """Unchanged from before: deterministically extracts order_id from
    create_order's structured JSON result — no LLM involvement."""
    updates: dict = {}
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            break
        if msg.name == "create_order":
            try:
                parsed = json.loads(msg.content)
                if "order_id" in parsed:
                    updates["current_order_id"] = parsed["order_id"]
            except (json.JSONDecodeError, TypeError):
                pass
    return updates


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


# ---------------------------------------------------------------------------
# Graph assembly.
# ---------------------------------------------------------------------------

def build_graph(static_info: dict):
    graph = StateGraph(AgentState)
    graph.add_node("agent", make_agent_node(static_info))
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_node("state_capture", state_capture_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "state_capture")
    graph.add_edge("state_capture", "agent")

    return graph.compile(checkpointer=MemorySaver())


# ---------------------------------------------------------------------------
# Runner.
# ---------------------------------------------------------------------------

def main():
    static_info = fetch_restaurant_static_info()
    app = build_graph(static_info)
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    business_name = static_info.get("business_name", "Restaurant")
    print(f"{business_name} agent (MVP, POS-backed) ready. Type 'quit' to exit.\n")

    first_turn = True
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        new_messages: list = [{"role": "user", "content": user_input}]
        if first_turn:
            new_messages = [
                {"role": "system", "content": build_system_prompt(static_info, None)}
            ] + new_messages
            first_turn = False

        for event in app.stream({"messages": new_messages}, config, stream_mode="values"):
            last_message = event["messages"][-1]
            if getattr(last_message, "tool_calls", None):
                for tc in last_message.tool_calls:
                    print(f"  [tool call] {tc['name']}({tc['args']})")

        reply = event["messages"][-1].content
        try:
            parsed = json.loads(reply)
            if isinstance(parsed, dict) and "display_text" in parsed:
                reply = parsed["display_text"]
        except (json.JSONDecodeError, TypeError):
            pass
        print(f"Agent: {reply}\n")


if __name__ == "__main__":
    main()
