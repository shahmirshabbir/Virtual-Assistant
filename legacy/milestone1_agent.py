"""
Milestone 1 — Agent wired to the real restaurant knowledge base.

What's new vs milestone0_tool_calling.py:
  1. Menu + inventory are loaded from restaurant_knowledge_base.json
     instead of being hardcoded in the script (data separated from code).
  2. Static, rarely-changing info (hours, policies, address, promotions)
     is placed directly in the system prompt — no tool call needed for these.
  3. Dynamic info (prices, stock) stays behind tools — search_menu and
     check_inventory — so the model is forced to look them up live instead
     of guessing from memory.
  4. Tool descriptions explicitly tell the model NOT to answer from memory,
     to reduce the model skipping the tool call.

Setup:
  pip install google-genai
  export GEMINI_API_KEY="your-key-here"   (Mac/Linux)
  setx GEMINI_API_KEY "your-key-here"     (Windows, then restart terminal)

  Place restaurant_knowledge_base.json in the same folder as this script.
"""

import json
import os
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 1. Load the knowledge base once at startup.
# ---------------------------------------------------------------------------

with open("restaurant_knowledge_base.json", "r", encoding="utf-8") as f:
    KB = json.load(f)

MENU = {item["id"]: item for item in KB["menu"]}
INVENTORY = KB["inventory"]
RESTAURANT_INFO = KB["restaurant"]


# ---------------------------------------------------------------------------
# 2. Tools — now backed by the real knowledge base instead of a toy dict.
#    Note: these still just read a local JSON file, not a real database.
#    That swap (JSON -> Postgres query) happens later without changing
#    the function signature or how the LLM calls it.
# ---------------------------------------------------------------------------

def search_menu(item_name: str) -> str:
    """Search the restaurant's live menu for a specific item's price,
    category, and description. Always call this tool to answer any
    question about menu items or prices — never answer from your own
    knowledge, since the menu and prices can change at any time.

    Args:
        item_name: The name of the menu item to search for, e.g.
            "pepperoni pizza" or "tiramisu". Partial matches are okay.

    Returns:
        The item's details if found, or a not-found message listing
        close matches if any exist.
    """
    query = item_name.lower().strip()
    matches = [
        item for item in MENU.values()
        if query in item["name"].lower()
    ]
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
    """Check whether a menu item is currently in stock and how many are
    available. Always call this tool before confirming an order can be
    placed — never assume an item is available. Use the item's id (e.g.
    "M002"), which you can get from search_menu.

    Args:
        item_id: The menu item's id, e.g. "M002".

    Returns:
        Stock status and quantity available, or an error if the id
        doesn't exist.
    """
    record = INVENTORY.get(item_id)
    if record is None:
        return f"No inventory record found for item id '{item_id}'."
    if not record["in_stock"]:
        return f"Item {item_id} is currently OUT OF STOCK."
    return f"Item {item_id} is in stock — {record['quantity_available']} available."


# ---------------------------------------------------------------------------
# 3. Static info goes directly into the system prompt — no tool needed,
#    since hours/policies/address don't change turn to turn.
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
- Be concise and friendly, like a real restaurant staff member on the phone.
"""


# ---------------------------------------------------------------------------
# 4. Agent loop.
# ---------------------------------------------------------------------------

def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    tools = [search_menu, check_inventory]

    chat = client.chats.create(
        model="gemini-3.1-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=build_system_prompt(),
            tools=tools,
        ),
    )

    print(f"{RESTAURANT_INFO['name']} agent ready. Type a question (or 'quit').\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        response = chat.send_message(user_input)
        print(f"Agent: {response.text}\n")


if __name__ == "__main__":
    main()
