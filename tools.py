"""
tools.py — Yavar agent tools, backed by the real restaurant POS API.

Replaces the earlier in-memory/mock version. Tools are now thin HTTP
clients over the POS — no business logic, no local data store. The POS
owns orders, menu, customers, inventory, zones. See ENDPOINTS.md for
the full API surface; this file wraps only what the customer-facing
agent needs (see tool-to-endpoint mapping discussion for what was
excluded and why).

DESIGN DECISIONS MADE HERE (flagging explicitly, revisit if wrong):
1. create_order AUTO-CONFIRMS (NEW -> CONFIRMED) immediately after
   creation, matching the "autonomous, no human intervention for
   routine requests" premise from the original project brief. If you
   want orders to sit at NEW for staff review instead, remove the
   confirm_order call in create_order().
2. update_order is split into THREE tools (add_order_items,
   update_order_item, remove_order_item) matching the POS's granular
   item-level endpoints, rather than one tool that diffs a full list
   client-side. The LLM picks the right one based on what the customer
   asked for.
3. check_delivery_availability has no direct POS endpoint — it's
   implemented by cross-referencing list_zones() against the
   customer-stated area, client-side. Flagged as a gap: a dedicated
   POS endpoint would be more robust than name-matching.

Setup:
  pip install requests pydantic python-dotenv
  .env: POS_BASE_URL=..., POS_API_TOKEN=..., POS_ACTION_PIN=... (optional)
"""

import json
import os
import uuid

import requests
from pydantic import BaseModel, Field, ValidationError

try:
    from langchain_core.tools import tool
except ImportError:
    def tool(fn):  # fallback no-op decorator if langchain isn't installed yet
        return fn

POS_BASE_URL = os.environ.get("POS_BASE_URL", "http://localhost:8000").rstrip("/")
POS_API_TOKEN = os.environ.get("POS_API_TOKEN", "")
POS_ACTION_PIN = os.environ.get("POS_ACTION_PIN")  # only sent if configured

_SESSION = requests.Session()
_SESSION.headers.update({"Authorization": f"Bearer {POS_API_TOKEN}"})


def _pos_request(method: str, path: str, **kwargs) -> dict | list | str:
    """Thin wrapper around requests to the POS API. Returns parsed JSON on
    success, or a plain error string on failure — tool functions return
    that string straight to the LLM rather than raising, so a POS error
    becomes a conversational fact the agent can act on, not a crash."""
    url = f"{POS_BASE_URL}{path}"
    try:
        resp = _SESSION.request(method, url, timeout=8, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()
    except requests.exceptions.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else str(e)
        return f"POS error ({e.response.status_code if e.response is not None else '?'}): {body}"
    except requests.exceptions.RequestException as e:
        return f"POS request failed: {e}"


def _action_pin_header() -> dict:
    return {"X-Action-Pin": POS_ACTION_PIN} if POS_ACTION_PIN else {}


# ---------------------------------------------------------------------------
# Pydantic schemas — match the POS's request shapes, not the old mock shapes.
# ---------------------------------------------------------------------------

class OrderItemInput(BaseModel):
    menu_item_id: str
    variant_id: str | None = None
    modifier_ids: list[str] | None = None
    quantity: int = Field(default=1, gt=0)
    note: str | None = None


class CustomerInput(BaseModel):
    name: str
    phone: str


class AddressInput(BaseModel):
    line1: str
    area: str | None = None
    city: str | None = None


class CreateOrderInput(BaseModel):
    customer: CustomerInput
    address: AddressInput
    items: list[OrderItemInput]
    payment_method: str  # "cash" or "online", per POS
    note: str | None = None
    source: str = "phone"


# ===========================================================================
# CATEGORY 1 — READ-ONLY TOOLS
# ===========================================================================

@tool
def search_menu(query: str) -> str:
    """Search the restaurant's live menu by name. Always call this to
    answer any question about menu items or prices — never answer from
    memory, since the menu changes."""
    result = _pos_request("GET", "/menu/items", params={"q": query, "available": True})
    if isinstance(result, str):
        return result
    if not result:
        return f"No menu item matching '{query}' was found."
    return json.dumps(result)


@tool
def list_menu(category_name: str | None = None) -> str:
    """List all menu items, optionally filtered by category name (e.g.
    'Pizza', 'Dessert'). Use this when the customer asks to see the
    full menu or a whole category, rather than guessing item names."""
    if category_name:
        categories = _pos_request("GET", "/categories")
        if isinstance(categories, str):
            return categories
        match = next((c for c in categories if c["name"].lower() == category_name.lower()), None)
        if not match:
            return f"No category named '{category_name}' found."
        result = _pos_request("GET", "/menu/items", params={"category_id": match["id"]})
    else:
        result = _pos_request("GET", "/menu")
    if isinstance(result, str):
        return result
    return json.dumps(result)


@tool
def check_inventory(item_id: str) -> str:
    """Check whether a menu item is currently available. Always call
    this before confirming an order. Use the item's id from search_menu
    or list_menu — note the POS reports available/unavailable only, not
    a stock count."""
    result = _pos_request("GET", f"/menu/items/{item_id}")
    if isinstance(result, str):
        return result
    status = "available" if result.get("is_available") else "OUT OF STOCK"
    return f"Item {item_id} ({result.get('name', '?')}) is currently {status}."


@tool
def check_order_status(order_id: str) -> str:
    """Look up an existing order's current items, status, payment
    status, and whether it's running late."""
    result = _pos_request("GET", f"/orders/{order_id}")
    if isinstance(result, str):
        return result
    return json.dumps(result)


@tool
def list_zones() -> str:
    """List delivery zones/areas the restaurant delivers to, with their
    delivery fees. Use this to answer 'do you deliver to X' questions."""
    result = _pos_request("GET", "/zones", params={"include_inactive": False})
    if isinstance(result, str):
        return result
    return json.dumps(result)


@tool
def check_delivery_availability(area: str) -> str:
    """Check whether a customer's area is within a known delivery zone,
    and what the delivery fee is. Call this before confirming a
    delivery order.

    IMPLEMENTATION NOTE: the POS has no dedicated address-check
    endpoint — this matches the customer's stated area against the
    zone list by name. Imprecise for ambiguous/misspelled area names;
    a real deployment should add a proper POS endpoint for this."""
    zones = _pos_request("GET", "/zones", params={"include_inactive": False})
    if isinstance(zones, str):
        return zones
    match = next((z for z in zones if z["name"].lower() == area.strip().lower()), None)
    if match:
        return f"'{area}' is in delivery zone '{match['name']}' — fee: {match['fee']}."
    zone_names = ", ".join(z["name"] for z in zones)
    return f"'{area}' does not match a known delivery zone (known zones: {zone_names}). Confirm the area with the customer or offer pickup."


@tool
def lookup_customer_by_phone(phone: str) -> str:
    """Look up a returning customer by phone number — returns their
    name and saved addresses if found. Use this when a customer
    provides their phone number, so you don't have to re-collect their
    details from scratch."""
    result = _pos_request("GET", "/customers/lookup", params={"phone": phone})
    if isinstance(result, str):
        return result
    return json.dumps(result)


# ===========================================================================
# CATEGORY 2 — STATE-MUTATING TOOLS
# ===========================================================================

@tool
def create_order(customer_name: str, customer_phone: str, address_line1: str,
                  items: list[dict], payment_method: str,
                  address_area: str | None = None, address_city: str | None = None,
                  note: str | None = None) -> str:
    """Create and immediately confirm a new delivery order. ALWAYS call
    search_menu first to get correct menu_item_id values, and
    check_inventory to confirm availability, before calling this.
    items is a list of {menu_item_id, variant_id (optional),
    modifier_ids (optional), quantity, note (optional)}.
    payment_method is 'cash' or 'online'."""
    try:
        validated = CreateOrderInput(
            customer=CustomerInput(name=customer_name, phone=customer_phone),
            address=AddressInput(line1=address_line1, area=address_area, city=address_city),
            items=[OrderItemInput(**i) for i in items],
            payment_method=payment_method,
            note=note,
        )
    except ValidationError as e:
        return f"Could not create order — invalid input: {e}"

    body = {
        "customer": validated.customer.model_dump(),
        "address": validated.address.model_dump(exclude_none=True),
        "items": [i.model_dump(exclude_none=True) for i in validated.items],
        "payment_method": validated.payment_method,
    }
    if validated.note:
        body["note"] = validated.note
    body["source"] = validated.source

    headers = {"Idempotency-Key": str(uuid.uuid4())}
    order = _pos_request("POST", "/orders", json=body, headers=headers)
    if isinstance(order, str):
        return order

    order_id = order["id"] if "id" in order else order.get("order_id")
    # Design decision #1 (see module docstring): auto-confirm immediately.
    confirmed = _pos_request("POST", f"/orders/{order_id}/confirm")
    if isinstance(confirmed, str):
        # Order WAS created even though confirm failed — say so clearly,
        # don't claim total failure.
        return json.dumps({
            "order_id": order_id,
            "display_text": f"Order {order_id} was created but could not be auto-confirmed ({confirmed}). A staff member will need to confirm it manually.",
        })

    total = confirmed.get("totals", {}).get("total", "")
    eta = confirmed.get("estimated_delivery_at", "")
    display_text = f"Order {order_id} confirmed. Total: {total}." + (f" Estimated delivery: {eta}." if eta else "")
    return json.dumps({"order_id": order_id, "display_text": display_text})


@tool
def add_order_items(order_id: str, items: list[dict]) -> str:
    """Add one or more NEW items to an existing order (does not touch
    existing items). items is a list of {menu_item_id, variant_id
    (optional), modifier_ids (optional), quantity, note (optional)}.
    Use this when a customer wants to add something to an order already
    placed, e.g. 'also add a cola'."""
    try:
        validated_items = [OrderItemInput(**i) for i in items]
    except ValidationError as e:
        return f"Could not add items — invalid input: {e}"
    body = [i.model_dump(exclude_none=True) for i in validated_items]
    result = _pos_request("POST", f"/orders/{order_id}/items", json=body)
    if isinstance(result, str):
        return result
    return json.dumps(result)


@tool
def update_order_item(order_id: str, item_id: str, quantity: int | None = None,
                       note: str | None = None, reason: str | None = None) -> str:
    """Change the quantity or note on ONE existing line item of an
    order — e.g. 'make it two pizzas instead of one'. Use
    check_order_status first if you need the item_id for a specific line."""
    body = {}
    if quantity is not None:
        body["quantity"] = quantity
    if note is not None:
        body["note"] = note
    if reason is not None:
        body["reason"] = reason
    if not body:
        return "No change specified — provide quantity and/or note."
    result = _pos_request("PATCH", f"/orders/{order_id}/items/{item_id}", json=body)
    if isinstance(result, str):
        return result
    return json.dumps(result)


@tool
def remove_order_item(order_id: str, item_id: str, reason: str | None = None) -> str:
    """Remove one line item from an existing order — e.g. 'actually
    remove the salad'. Use check_order_status first if you need the
    item_id for a specific line."""
    params = {"reason": reason} if reason else {}
    result = _pos_request("DELETE", f"/orders/{order_id}/items/{item_id}", params=params)
    if isinstance(result, str):
        return result
    return "Item removed from the order."


@tool
def cancel_order(order_id: str, reason: str) -> str:
    """Cancel an existing order entirely. Irreversible — confirm with
    the customer before calling this. The POS automatically flags
    whether a refund is needed if money was already paid."""
    result = _pos_request("POST", f"/orders/{order_id}/cancel", json={"reason": reason},
                           headers=_action_pin_header())
    if isinstance(result, str):
        return result
    needs_refund = result.get("needs_refund", False)
    msg = f"Order {order_id} cancelled."
    if needs_refund:
        msg += " A refund is needed — this has been flagged for staff."
    return msg


# ===========================================================================
# Export list — import this into the agent.
# ===========================================================================

TOOLS = [
    search_menu,
    list_menu,
    check_inventory,
    check_order_status,
    list_zones,
    check_delivery_availability,
    lookup_customer_by_phone,
    create_order,
    add_order_items,
    update_order_item,
    remove_order_item,
    cancel_order,
]
