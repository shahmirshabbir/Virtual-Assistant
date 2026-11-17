"""
Milestone 0 — First tool-calling script.

Goal: watch Gemini decide, on its own, to call a Python function
to answer a question it can't answer from its own knowledge
(our fake restaurant's menu prices don't exist anywhere on the internet).

Setup:
  pip install google-genai
  export GEMINI_API_KEY="your-key-here"   (Mac/Linux)
  setx GEMINI_API_KEY "your-key-here"     (Windows, then restart terminal)
"""

import os
from google import genai

# ---------------------------------------------------------------------------
# 1. Our "tools" — for now, plain Python functions with fake/mock data.
#    Later, the body of these functions is the ONLY thing that changes
#    (e.g. querying a real database or calling a real API instead of
#    a hardcoded dict). The LLM-facing shape never changes.
# ---------------------------------------------------------------------------

FAKE_MENU = {
    "margherita pizza": 8.99,
    "pepperoni pizza": 10.99,
    "cola": 2.50,
    "garlic bread": 4.50,
    "caesar salad": 6.99,
}


def get_menu_item_price(item_name: str) -> str:
    """Look up the price of a menu item at our restaurant.

    Args:
        item_name: The name of the menu item, e.g. "pepperoni pizza".

    Returns:
        The price as a string, or a not-found message.
    """
    price = FAKE_MENU.get(item_name.lower().strip())
    if price is None:
        return f"'{item_name}' was not found on the menu."
    return f"{item_name} costs ${price:.2f}"


def check_item_availability(item_name: str) -> str:
    """Check whether a menu item is currently in stock.

    Args:
        item_name: The name of the menu item, e.g. "garlic bread".

    Returns:
        A short availability message.
    """
    # Fake logic for now — everything is in stock except cola.
    if item_name.lower().strip() == "cola":
        return f"{item_name} is currently out of stock."
    return f"{item_name} is available."


# ---------------------------------------------------------------------------
# 2. Wire the functions up to Gemini.
#    The google-genai SDK supports "automatic function calling": pass your
#    Python functions directly as tools, and the SDK handles detecting the
#    tool call, running your function, and feeding the result back to the
#    model for you. Great for learning the pattern with minimal boilerplate.
# ---------------------------------------------------------------------------

def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    tools = [get_menu_item_price, check_item_availability]

    print("Restaurant agent ready. Type a question (or 'quit').\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=user_input,
            config={"tools": tools},
        )

        print(f"Agent: {response.text}\n")


if __name__ == "__main__":
    main()
