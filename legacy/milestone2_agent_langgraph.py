"""
Milestone 2 (LangGraph version) — Same tools, same knowledge base, now
orchestrated with LangGraph's StateGraph instead of a hand-rolled while loop.

WHY A MANUAL StateGraph (not langgraph.prebuilt.create_react_agent):
LangGraph ships a one-line create_react_agent() helper that hides the graph
entirely. That's fine for shipping fast, but for interview purposes it's
worth building the graph explicitly once — nodes, edges, state schema — so
you can actually explain what LangGraph is doing, not just that you called
a function that works. This mirrors exactly what run_agent_turn() did by
hand in milestone1_agent_groq.py — same two-step round trip, now expressed
as a graph with a conditional edge instead of a while loop.

CONCEPT MAP (raw code -> LangGraph):
  messages list you appended to manually  -> AgentState (a TypedDict/reducer)
  `if message.tool_calls: ... else: return` -> a conditional edge function
  your manual tool-dispatch for-loop        -> the prebuilt ToolNode
  the `continue` in your while loop          -> an edge back to the agent node
  in-memory ORDERS dict surviving the loop   -> a checkpointer (MemorySaver)
    giving you multi-turn memory across calls, keyed by a thread_id

Setup:
  pip install langchain langchain-groq langgraph
  export GROQ_API_KEY="your-key-here"
  Place restaurant_knowledge_base.json in the same folder as this script.
"""

import json
import os
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# 1. Knowledge base — identical to the raw Groq version.
# ---------------------------------------------------------------------------

with open("restaurant_knowledge_base.json", "r", encoding="utf-8") as f:
    KB = json.load(f)

MENU = {item["id"]: item for item in KB["menu"]}
INVENTORY = KB["inventory"]
RESTAURANT_INFO = KB["restaurant"]
ORDERS: dict[str, dict] = {}


def _calculate_order_total(items: list[dict]) -> float:
    total = 0.0
    for line in items:
        menu_item = MENU.get(line["item_id"])
        if menu_item:
            total += menu_item["price"] * line["quantity"]
    return round(total, 2)


# ---------------------------------------------------------------------------
# 2. Tools — same logic as before, now using LangChain's @tool decorator.
#    KEY DIFFERENCE: @tool auto-generates the JSON schema from the type
#    hints and docstring, same as google-genai did — LangChain gives you
#    that convenience back, on top of Groq, which the raw openai SDK
#    version didn't have (that's why you hand-wrote TOOL_SCHEMAS earlier).
#    This is a concrete, explainable example of "what the framework buys
#    you": schema generation you'd otherwise write by hand.
# ---------------------------------------------------------------------------

class OrderItemInput(BaseModel):
    item_id: str
    quantity: int = Field(gt=0, description="Must be at least 1")


class CreateOrderInput(BaseModel):
    items: list[OrderItemInput]
    delivery_type: str


@tool
def search_menu(item_name: str) -> str:
    """Search the restaurant's live menu for a specific item's price,
    category, and description. Always call this tool to answer any
    question about menu items or prices — never answer from memory,
    since the menu and prices can change at any time."""
    query = item_name.lower().strip()
    matches = [item for item in MENU.values() if query in item["name"].lower()]
    if not matches:
        return f"No menu item matching '{item_name}' was found."
    if len(matches) == 1:
        item = matches[0]
        return (
            f"{item['name']} ({item['category']}) — ${item['price']:.2f}. "
            f"{item['description']}. [id: {item['id']}]"
        )
    names = ", ".join(m["name"] for m in matches)
    return f"Multiple items matched '{item_name}': {names}. Please specify which one."


@tool
def check_inventory(item_id: str) -> str:
    """Check whether a menu item is currently in stock and how many are
    available. Always call this before confirming an order. Use the
    item's id (e.g. 'M002'), which you can get from search_menu."""
    record = INVENTORY.get(item_id)
    if record is None:
        return f"No inventory record found for item id '{item_id}'."
    if not record["in_stock"]:
        return f"Item {item_id} is currently OUT OF STOCK."
    return f"Item {item_id} is in stock — {record['quantity_available']} available."


@tool
def create_order(items: list[dict], delivery_type: str) -> str:
    """Create a new order with one or more menu items. ALWAYS call
    search_menu first to get correct item ids, and check_inventory to
    confirm stock, before calling this. items is a list of objects each
    with 'item_id' and 'quantity'. delivery_type is 'pickup' or 'delivery'."""
    try:
        validated = CreateOrderInput(items=items, delivery_type=delivery_type)
    except ValidationError as e:
        return f"Could not create order — invalid input: {e}"

    for line in validated.items:
        if line.item_id not in MENU:
            return f"Could not create order — item id '{line.item_id}' does not exist."

    order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
    items_dicts = [i.model_dump() for i in validated.items]
    total = _calculate_order_total(items_dicts)

    ORDERS[order_id] = {
        "items": items_dicts,
        "delivery_type": validated.delivery_type,
        "status": "confirmed",
        "total": total,
    }

    item_summary = ", ".join(
        f"{line['quantity']}x {MENU[line['item_id']]['name']}" for line in items_dicts
    )
    return (
        f"Order {order_id} created — {item_summary}. "
        f"Delivery type: {validated.delivery_type}. Total: ${total:.2f}."
    )


@tool
def update_order(order_id: str, items: list[dict]) -> str:
    """Update an existing order's items. This REPLACES the order's item
    list, so include ALL items the order should have after the update,
    not just the changed one. items is a list of objects each with
    'item_id' and 'quantity'."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id '{order_id}'."
    if order["status"] != "confirmed":
        return f"Order {order_id} can no longer be modified (status: {order['status']})."

    try:
        validated_items = [OrderItemInput(**i) for i in items]
    except ValidationError as e:
        return f"Could not update order — invalid input: {e}"

    for line in validated_items:
        if line.item_id not in MENU:
            return f"Could not update order — item id '{line.item_id}' does not exist."

    items_dicts = [i.model_dump() for i in validated_items]
    order["items"] = items_dicts
    order["total"] = _calculate_order_total(items_dicts)

    item_summary = ", ".join(
        f"{line['quantity']}x {MENU[line['item_id']]['name']}" for line in items_dicts
    )
    return f"Order {order_id} updated — {item_summary}. New total: ${order['total']:.2f}."


@tool
def check_order_status(order_id: str) -> str:
    """Look up an existing order's current items, status, and total."""
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id '{order_id}'."
    item_summary = ", ".join(
        f"{line['quantity']}x {MENU[line['item_id']]['name']}" for line in order["items"]
    )
    return (
        f"Order {order_id} — status: {order['status']}, "
        f"items: {item_summary}, total: ${order['total']:.2f}."
    )


@tool
def escalate_to_human(reason: str) -> str:
    """Escalate the conversation to a human staff member. Call this when
    the customer explicitly asks for a human, the request is sensitive or
    a policy exception, you are repeatedly unable to help, or you are not
    confident you understood the request correctly."""
    print(f"  [ESCALATION LOGGED] reason: {reason}")
    return "This has been escalated to a human team member, who will follow up shortly."


TOOLS = [search_menu, check_inventory, create_order, update_order, check_order_status, escalate_to_human]


# ---------------------------------------------------------------------------
# 3. Static system prompt — identical content to the raw version.
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    hours = RESTAURANT_INFO["hours"]
    delivery = RESTAURANT_INFO["delivery"]
    return f"""You are the phone/chat ordering assistant for {RESTAURANT_INFO['name']},
an {RESTAURANT_INFO['cuisine']} restaurant located at {RESTAURANT_INFO['address']}.

Business hours:
- Mon-Thu: {hours['monday_to_thursday']}
- Fri-Sat: {hours['friday_saturday']}
- Sun: {hours['sunday']}

Delivery: ${delivery['fee']:.2f} fee (free over ${delivery['free_delivery_over']:.2f}),
estimated {delivery['estimated_time_minutes']} minutes, within {delivery['delivery_radius_miles']} miles.

Refund policy: {RESTAURANT_INFO['policies']['refund_policy']}

Current promotions: {", ".join(RESTAURANT_INFO['promotions'])}

Rules:
- NEVER state a menu price or stock status from memory — always use the
  search_menu and check_inventory tools.
- Hours, address, delivery fee, and policy info above can be answered
  directly without a tool call.
- Before creating an order, resolve item names to ids via search_menu,
  and confirm stock via check_inventory.
- When a customer wants to change an existing order, use update_order
  with the order's FULL new item list, not just the change.
- If a customer explicitly asks for a human, or you're not confident you
  understood their request, use escalate_to_human rather than guessing.
- Be concise and friendly, like a real restaurant staff member on the phone.
"""


# ---------------------------------------------------------------------------
# 4. The graph itself. This is the part worth understanding line by line.
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    # add_messages is a "reducer": instead of replacing this field each
    # time a node returns, LangGraph appends new messages to the existing
    # list. This is what replaces the `messages.append(...)` calls you
    # wrote by hand in the raw version.
    messages: Annotated[list[AnyMessage], add_messages]


def build_graph():
    llm = ChatGroq(model="openai/gpt-oss-120b", api_key=os.environ["GROQ_API_KEY"])
    llm_with_tools = llm.bind_tools(TOOLS)  # attaches TOOLS' auto-generated schemas

    def agent_node(state: AgentState) -> AgentState:
        """Equivalent to the `client.chat.completions.create(...)` call in
        the raw version — sends the conversation so far, gets back either
        a tool-call request or a final answer."""
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        """Equivalent to `if message.tool_calls: ... else: return` in the
        raw version. This is the conditional edge: it inspects the last
        message and decides whether to route to the tool node or end."""
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    # ToolNode is LangGraph's prebuilt equivalent of your manual for-loop
    # that dispatched AVAILABLE_TOOLS[fn_name](**fn_args) and appended a
    # "tool" role message back — same job, provided for you here.
    graph.add_node("tools", ToolNode(TOOLS))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    # After tools run, loop back to the agent — equivalent to the
    # `continue` statement in your raw while-loop.
    graph.add_edge("tools", "agent")

    # MemorySaver is the checkpointer: it persists AgentState (the message
    # list) between .invoke() calls, keyed by a thread_id. This is what
    # gives you multi-turn memory without manually carrying a `messages`
    # list around yourself, as the raw version did.
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# 5. Run loop — much shorter than the raw version, since the graph now
#    owns the tool-call round trip and the message history.
# ---------------------------------------------------------------------------

def main():
    app = build_graph()
    thread_id = str(uuid.uuid4())  # one thread = one conversation's memory
    config = {"configurable": {"thread_id": thread_id}}

    system_prompt = build_system_prompt()
    first_turn = True

    print(f"{RESTAURANT_INFO['name']} agent ready (LangGraph). Type a question (or 'quit').\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        messages = [{"role": "user", "content": user_input}]
        if first_turn:
            # Only send the system prompt once — the checkpointer keeps
            # it in state for every subsequent turn on this thread_id.
            messages = [{"role": "system", "content": system_prompt}] + messages
            first_turn = False

        for event in app.stream({"messages": messages}, config, stream_mode="values"):
            last_message = event["messages"][-1]
            if getattr(last_message, "tool_calls", None):
                for tc in last_message.tool_calls:
                    print(f"  [tool call] {tc['name']}({tc['args']})")

        final_reply = event["messages"][-1].content
        print(f"Agent: {final_reply}\n")


if __name__ == "__main__":
    main()
