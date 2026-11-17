"""
Milestone 1 — Groq version (same knowledge base + tools as the Gemini version).

Why the code looks different: Groq doesn't have its own SDK for this —
it exposes an OpenAI-compatible endpoint, so we use the `openai` Python
package pointed at Groq's base_url instead of `google-genai`.

Key difference from the Gemini version: there's no "automatic function
calling" here. The openai SDK does NOT auto-resolve tool calls for you —
you get the tool-call request back, run the function yourself, and send
the result back in a second call. This is actually a good thing to see
once: it's the manual version of what google-genai was hiding from you.

Setup:
  pip install openai
  export GROQ_API_KEY="your-key-here"   (Mac/Linux)
  setx GROQ_API_KEY "your-key-here"     (Windows, then restart terminal)

  Get a free key at https://console.groq.com/keys — no card required.
  Place restaurant_knowledge_base.json in the same folder as this script.
"""

import json
import os
import uuid
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# 1. Load the knowledge base — identical to the Gemini version.
# ---------------------------------------------------------------------------

with open("restaurant_knowledge_base.json", "r", encoding="utf-8") as f:
    KB = json.load(f)

MENU = {item["id"]: item for item in KB["menu"]}
INVENTORY = KB["inventory"]
RESTAURANT_INFO = KB["restaurant"]


# ---------------------------------------------------------------------------
# 2. Tool functions — identical logic to the Gemini version.
#    (Same functions, just registered differently below.)
# ---------------------------------------------------------------------------

def search_menu(item_name: str) -> str:
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


def check_inventory(item_id: str) -> str:
    record = INVENTORY.get(item_id)
    if record is None:
        return f"No inventory record found for item id '{item_id}'."
    if not record["in_stock"]:
        return f"Item {item_id} is currently OUT OF STOCK."
    return f"Item {item_id} is in stock — {record['quantity_available']} available."


# Map tool names (strings) to the actual Python functions, so we can look
# them up dynamically when Groq sends back a tool-call request by name.
AVAILABLE_TOOLS = {
    "search_menu": search_menu,
    "check_inventory": check_inventory,
}


# ---------------------------------------------------------------------------
# 2b. Order management — this is where the agent goes from "answering
#     questions" to "taking action." Note the Pydantic model: order items
#     are structured/nested data (a list of {id, quantity} pairs), not a
#     flat string, so this is exactly the case where Pydantic earns its
#     place over a plain docstring, as discussed.
# ---------------------------------------------------------------------------

class OrderItemInput(BaseModel):
    item_id: str
    quantity: int = Field(gt=0, description="Must be at least 1")


class CreateOrderInput(BaseModel):
    items: list[OrderItemInput]
    delivery_type: str = Field(description="'pickup' or 'delivery'")


# In-memory order store. Keyed by order_id. This is intentionally simple —
# a real system would use Postgres, but for now this lets us prove the
# multi-turn "create, then modify" pattern works before adding a database.
ORDERS: dict[str, dict] = {}


def _calculate_order_total(items: list[dict]) -> float:
    total = 0.0
    for line in items:
        menu_item = MENU.get(line["item_id"])
        if menu_item:
            total += menu_item["price"] * line["quantity"]
    return round(total, 2)


def create_order(items: list[dict], delivery_type: str) -> str:
    """Create a new order with one or more menu items. ALWAYS call
    search_menu first to get correct item ids, and check_inventory to
    confirm stock, before calling this. Do not guess item ids.

    Args:
        items: A list of items, each with 'item_id' (from search_menu,
            e.g. 'M002') and 'quantity' (a positive integer).
        delivery_type: Either 'pickup' or 'delivery'.

    Returns:
        A confirmation message with the new order_id and total price,
        or a validation error message if the input was malformed.
    """
    try:
        validated = CreateOrderInput(items=items, delivery_type=delivery_type)
    except ValidationError as e:
        return f"Could not create order — invalid input: {e}"

    # Verify every item actually exists on the menu before committing.
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


def update_order(order_id: str, items: list[dict]) -> str:
    """Update an existing order's items — e.g. changing quantity or adding
    an item. This REPLACES the order's item list with the new one you
    provide, so include ALL items the order should have after the update,
    not just the changed one. Use check_order_status first if you need to
    see the current items before modifying them.

    Args:
        order_id: The order's id, e.g. 'ORD-A1B2C3'.
        items: The full new list of items for this order, each with
            'item_id' and 'quantity'.

    Returns:
        A confirmation with the updated total, or an error if the order
        doesn't exist or is no longer modifiable.
    """
    order = ORDERS.get(order_id)
    if order is None:
        return f"No order found with id '{order_id}'."
    if order["status"] not in ("confirmed",):
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


def check_order_status(order_id: str) -> str:
    """Look up an existing order's current items, status, and total.

    Args:
        order_id: The order's id, e.g. 'ORD-A1B2C3'.

    Returns:
        The order's details, or a not-found message.
    """
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


def escalate_to_human(reason: str) -> str:
    """Escalate the conversation to a human staff member. Call this when:
    the customer explicitly asks for a human, the request is sensitive or
    a policy exception, you are repeatedly unable to help, or you are not
    confident you understood the request correctly.

    Args:
        reason: A short explanation of why this is being escalated.

    Returns:
        A confirmation that escalation has been logged.
    """
    print(f"  [ESCALATION LOGGED] reason: {reason}")  # stands in for a real alert/notification
    return "This has been escalated to a human team member, who will follow up shortly."


AVAILABLE_TOOLS.update({
    "create_order": create_order,
    "update_order": update_order,
    "check_order_status": check_order_status,
    "escalate_to_human": escalate_to_human,
})

# ---------------------------------------------------------------------------
# 3. Manual tool schemas.
#    Unlike google-genai, the openai-compatible SDK does NOT generate this
#    from your docstrings automatically — you write the JSON schema by hand.
#    This is the exact structure we discussed earlier: name, description,
#    and a parameters schema.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_menu",
            "description": (
                "Search the restaurant's live menu for a specific item's price, "
                "category, and description. Always call this tool to answer any "
                "question about menu items or prices — never answer from your own "
                "knowledge, since the menu and prices can change at any time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_name": {
                        "type": "string",
                        "description": "The name of the menu item to search for, e.g. 'pepperoni pizza'. Partial matches are okay.",
                    }
                },
                "required": ["item_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": (
                "Check whether a menu item is currently in stock and how many are "
                "available. Always call this tool before confirming an order can be "
                "placed — never assume an item is available. Use the item's id "
                "(e.g. 'M002'), which you can get from search_menu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "The menu item's id, e.g. 'M002'.",
                    }
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": (
                "Create a new order with one or more menu items. Always call "
                "search_menu first to get correct item ids, and check_inventory "
                "to confirm stock, before calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of items to order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_id": {"type": "string", "description": "Menu item id, e.g. 'M002'."},
                                "quantity": {"type": "integer", "description": "How many of this item, minimum 1."},
                            },
                            "required": ["item_id", "quantity"],
                        },
                    },
                    "delivery_type": {
                        "type": "string",
                        "enum": ["pickup", "delivery"],
                        "description": "Whether the order is for pickup or delivery.",
                    },
                },
                "required": ["items", "delivery_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_order",
            "description": (
                "Update an existing order's items. This REPLACES the order's item "
                "list, so include ALL items the order should have after the update, "
                "not just the changed one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order's id, e.g. 'ORD-A1B2C3'."},
                    "items": {
                        "type": "array",
                        "description": "The FULL new list of items for this order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_id": {"type": "string"},
                                "quantity": {"type": "integer"},
                            },
                            "required": ["item_id", "quantity"],
                        },
                    },
                },
                "required": ["order_id", "items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Look up an existing order's current items, status, and total.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order's id, e.g. 'ORD-A1B2C3'."}
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": (
                "Escalate the conversation to a human staff member. Call this when "
                "the customer explicitly asks for a human, the request is sensitive "
                "or a policy exception, you are repeatedly unable to help, or you "
                "are not confident you understood the request correctly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "A short explanation of why this is being escalated."}
                },
                "required": ["reason"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 4. Static system prompt — identical content to the Gemini version.
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
  search_menu and check_inventory tools, since this data changes often.
- Hours, address, delivery fee, and policy information above are current
  and can be answered directly without a tool call.
- Before creating an order, always resolve item names to ids via search_menu,
  and confirm stock via check_inventory.
- When a customer wants to change an existing order (e.g. "make it two"),
  use update_order with the order's FULL new item list, not just the change.
- If a customer explicitly asks for a human, or you are not confident you
  understood their request, use escalate_to_human rather than guessing.
- Be concise and friendly, like a real restaurant staff member on the phone.
"""


# ---------------------------------------------------------------------------
# 5. The manual agent loop — this is the part that's genuinely different
#    from the Gemini version. Read the comments closely; this is exactly
#    the two-step round trip we discussed earlier, made visible in code.
# ---------------------------------------------------------------------------

def run_agent_turn(client, model, messages):
    """Send the conversation to Groq, resolve any tool calls, and return
    the final assistant reply. Loops in case the model chains multiple
    tool calls before giving a final answer."""

    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SCHEMAS,
        )
        message = response.choices[0].message

        # Case 1: the model wants to call one or more tools.
        if message.tool_calls:
            # Append the assistant's tool-call request to the conversation
            # history. We build this dict manually (rather than using
            # message.model_dump()) because the OpenAI SDK's full object
            # includes extra fields (like "annotations") that Groq's API
            # rejects when you send them back in a later request.
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)

                print(f"  [tool call] {fn_name}({fn_args})")  # visibility while learning

                fn = AVAILABLE_TOOLS[fn_name]
                result = fn(**fn_args)

                # Send the function's result back as a "tool" role message,
                # tagged with the same tool_call_id so the model knows which
                # call this result answers.
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })

            # Loop again — the model may chain another tool call, or now
            # give its final answer using the tool result(s).
            continue

        # Case 2: the model has a final natural-language answer.
        messages.append({"role": "assistant", "content": message.content})
        return message.content


def main():
    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1",
    )
    model = "openai/gpt-oss-120b"

    messages = [{"role": "system", "content": build_system_prompt()}]

    print(f"{RESTAURANT_INFO['name']} agent ready (Groq). Type a question (or 'quit').\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        messages.append({"role": "user", "content": user_input})
        reply = run_agent_turn(client, model, messages)
        print(f"Agent: {reply}\n")


if __name__ == "__main__":
    main()
