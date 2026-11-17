# Endpoint list

All 81 endpoints: what each does, what it takes, what it returns. Generated from the live API schema.

**Legend:** `*` = required, `?` = optional query parameter. `body` is the JSON request body. `path` values go in the URL. Money is sent as a number or numeric string and returned as a number. Full details, field types and real examples are in `API_REFERENCE.md`.

## Orders (19)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `create_order` | `POST /orders` | Create a new delivery order (status NEW) from a phone / WhatsApp / social-media request. | body: customer_id OR customer{name*, phone*}; address_id OR address{line1*, area, city, ...}; items[]* {menu_item_id*, variant_id, modifier_ids, quantity, note}; payment_method*; zone_id, note, source, discount{type*, value*, reason*}; header: Idempotency-Key (recommended); header: X-Action-Pin (only if a PIN is configured) | The full order (status NEW): totals, items[], payments[], events[] |
| `list_orders` | `GET /orders` | Search and filter orders (summaries, newest first, paginated). | query: q?, status?, payment_status?, payment_method?, rider_id?, source?, date_from?, date_to?, late?, needs_refund?, page?, page_size? | Page {items[] order summaries, total, page, page_size} |
| `get_order` | `GET /orders/{order_id}` | Get everything about one order: line items, totals, payments and link status, rider, timestamps, and the event log. | path: order_id* | The full order: status, payment_status, totals, amount_due, is_late, needs_refund, items[], payments[], events[] |
| `edit_order` | `PATCH /orders/{order_id}` | Change an order's delivery address, zone, note, source, or payment method. Only the fields you send change. | path: order_id*; body: {(all optional) address_id, address, zone_id, clear_zone, note, payment_method, source} | The updated full order |
| `get_order_events` | `GET /orders/{order_id}/events` | Get the audit log for an order, oldest first: creation, item edits with reasons, payments, status changes, cancellation, and who did them (when X-Actor was sent). | path: order_id* | Array of audit events {event_type, message, actor, created_at, data} |
| `add_order_items` | `POST /orders/{order_id}/items` | Add one or more items to an existing order. | path: order_id*; body: list of {menu_item_id*, variant_id, modifier_ids, quantity, note} | The updated full order |
| `update_order_item` | `PATCH /orders/{order_id}/items/{item_id}` | Change an order line's quantity or note. | path: order_id*, item_id*; body: {(all optional) quantity, note, reason} | The updated full order |
| `remove_order_item` | `DELETE /orders/{order_id}/items/{item_id}` | Remove one line from an order. | path: order_id*, item_id*; query: reason? | The updated full order |
| `set_order_discount` | `PUT /orders/{order_id}/discount` | Apply a discount to an order (replaces any existing discount). | path: order_id*; body: {type*, value*, reason*}; header: X-Action-Pin (only if a PIN is configured) | The updated full order |
| `clear_order_discount` | `DELETE /orders/{order_id}/discount` | Remove the discount from an order and restore the full total. Same rules as set_order_discount: NEW or CONFIRMED only, and X-Action-Pin if configured. | path: order_id*; header: X-Action-Pin (only if a PIN is configured) | The updated full order |
| `confirm_order` | `POST /orders/{order_id}/confirm` | Accept a NEW order into the delivery flow (NEW -> CONFIRMED) and start its delivery-time estimate. | path: order_id*; body (optional): {(all optional) estimated_delivery_minutes} | The updated full order (status CONFIRMED, with estimated_delivery_at) |
| `assign_rider` | `PUT /orders/{order_id}/rider` | Assign (or change) the delivery rider. | path: order_id*; body: {rider_id*} | The updated full order |
| `dispatch_order` | `POST /orders/{order_id}/dispatch` | Send a CONFIRMED order out for delivery (CONFIRMED -> OUT_FOR_DELIVERY). | path: order_id* | The updated full order (status OUT_FOR_DELIVERY) |
| `deliver_order` | `POST /orders/{order_id}/deliver` | Mark an OUT_FOR_DELIVERY order as delivered (-> DELIVERED). This is the moment the order counts as a sale in reports. | path: order_id*; body (optional): {(all optional) cash_collected} | The updated full order (status DELIVERED) |
| `fail_delivery` | `POST /orders/{order_id}/fail-delivery` | Record that delivery could not be completed (customer unreachable, wrong address, refused). OUT_FOR_DELIVERY -> DELIVERY_FAILED. | path: order_id*; body: {reason*} | The updated full order (status DELIVERY_FAILED) |
| `reattempt_delivery` | `POST /orders/{order_id}/reattempt` | Put a DELIVERY_FAILED order back to CONFIRMED to try again, with a new estimate (optional estimated_delivery_minutes). | path: order_id*; body (optional): {(all optional) estimated_delivery_minutes} | The updated full order (status CONFIRMED again) |
| `cancel_order` | `POST /orders/{order_id}/cancel` | Cancel an order (-> CANCELLED). Irreversible. | path: order_id*; body: {reason*}; header: X-Action-Pin (only if a PIN is configured) | The updated full order (status CANCELLED; needs_refund true if money was paid) |
| `print_order_document` | `GET /orders/{order_id}/print/{kind}` | Get a PDF for an order. kind = invoice (customer bill), delivery-slip (for the rider; shows the cash to collect) or packing-slip (items only). | path: order_id*, kind* | A PDF file (not JSON) |
| `get_invoice_share_links` | `GET /orders/{order_id}/share` | Get a shareable invoice link plus a ready wa.me WhatsApp link with a prefilled message. | path: order_id* | {invoice_url, whatsapp_url} |

## Payments (6)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `list_order_payments` | `GET /orders/{order_id}/payments` | List every payment record on an order: online payment links/attempts (PENDING, SUCCEEDED, FAILED, EXPIRED), cash collections, and refunds. | path: order_id* | Array of payment records: online attempts, cash collections, refunds |
| `create_payment_link` | `POST /orders/{order_id}/payment-link` | Create an online payment link for an order, or regenerate it. | path: order_id*; body (optional): {(all optional) amount} | {url, whatsapp_url, message, payment{...}} |
| `collect_cash` | `POST /orders/{order_id}/collect-cash` | Record cash collected from the customer by the rider on an OUT_FOR_DELIVERY or DELIVERED order. | path: order_id*; body (optional): {(all optional) amount} | The updated full order |
| `refund_order` | `POST /orders/{order_id}/refund` | Record a refund of money already paid. | path: order_id*; body: {amount*, reason*, mode, payment_id}; header: X-Action-Pin (only if a PIN is configured) | The updated full order |
| `payment_webhook` | `POST /webhooks/payments` | Gateway callback - NOT for agents. | raw signed JSON body {event_id, type, reference, amount} + X-Signature header | {status}: processed, duplicate, ignored or amount_mismatch |
| `simulate_mock_payment` | `POST /dev/mock-gateway/{reference}/simulate` | Development only (PAYMENT_GATEWAY=mock): simulate the customer finishing a payment. | path: reference*; query: outcome? | {status}: same values as the webhook |

## Menu (18)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `list_categories` | `GET /categories` | List menu categories ordered by sort_order, then name. | none | Array of categories {id, name, sort_order, is_active} |
| `create_category` | `POST /categories` | Create a menu category such as 'Karahi' or 'Drinks'. | body: {name*, sort_order, is_active} | The new category |
| `update_category` | `PATCH /categories/{category_id}` | Rename, reorder, or hide/show a category. Only the fields you send are changed. | path: category_id*; body: {(all optional) name, sort_order, is_active} | The updated category |
| `delete_category` | `DELETE /categories/{category_id}` | Permanently delete an EMPTY category. | path: category_id* | Nothing (204) |
| `get_menu_tree` | `GET /menu` | Get the full menu as a tree: active categories, each with its active items, size variants and add-ons. | query: include_unavailable? | Array of categories, each with items[] {id, name, price, is_available, variants[], modifiers[]} |
| `list_menu_items` | `GET /menu/items` | Search or filter menu items as a flat list. | query: category_id?, q?, available?, include_inactive? | Array of items, each with variants[] and modifiers[] |
| `create_menu_item` | `POST /menu/items` | Create a menu item, optionally with size variants and add-ons in the same call. | body: {category_id*, name*, description, image_url, price, is_available, is_active, variants, modifiers} | The new item, including ids of its variants and add-ons |
| `get_menu_item` | `GET /menu/items/{item_id}` | Get one menu item with its variants and add-ons. | path: item_id* | One item with variants[] and modifiers[] |
| `update_menu_item` | `PATCH /menu/items/{item_id}` | Edit a menu item's name, description, image_url, base price, category, availability, or visibility. Only the fields you send change. | path: item_id*; body: {(all optional) category_id, name, description, image_url, price, is_available, is_active} | The updated item |
| `delete_menu_item` | `DELETE /menu/items/{item_id}` | Permanently delete a menu item together with its variants and add-ons. | path: item_id* | Nothing (204) |
| `set_menu_item_availability` | `PUT /menu/items/{item_id}/availability` | Mark an item in stock or out of stock. | path: item_id*; body: {is_available*} | The updated item |
| `add_item_variant` | `POST /menu/items/{item_id}/variants` | Add a size/portion to an existing item, e.g. 'Large' at 1400. The variant price REPLACES the item's base price for that choice. | path: item_id*; body: {name*, price*, is_available} | The new variant {id, name, price, is_available} |
| `update_item_variant` | `PATCH /menu/variants/{variant_id}` | Change a variant's name, price, or availability. Only the fields you send change. | path: variant_id*; body: {(all optional) name, price, is_available} | The updated variant |
| `delete_item_variant` | `DELETE /menu/variants/{variant_id}` | Delete a size variant. Past orders are unaffected. | path: variant_id* | Nothing (204) |
| `add_item_modifier` | `POST /menu/items/{item_id}/modifiers` | Add an add-on or instruction to an item, e.g. 'Extra cheese' (+100) or 'No onion' (+0). | path: item_id*; body: {name*, extra_price, is_available} | The new add-on {id, name, extra_price, is_available} |
| `update_item_modifier` | `PATCH /menu/modifiers/{modifier_id}` | Change an add-on's name, price, or availability (is_available=false makes it unselectable). Only the fields you send change. Existing orders keep their old price. | path: modifier_id*; body: {(all optional) name, extra_price, is_available} | The updated add-on |
| `delete_item_modifier` | `DELETE /menu/modifiers/{modifier_id}` | Delete an add-on from an item. Past orders keep their copy of it. Returns 204 with no body. | path: modifier_id* | Nothing (204) |
| `upload_image` | `POST /uploads/image` | Upload an image (JPEG, PNG or WebP, max 2 MB) and get back a URL. | multipart file* (JPEG, PNG or WebP, max 2 MB) | {url} of the stored image (relative, e.g. /uploads/abc.jpg) |

## Customers (10)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `search_customers` | `GET /customers` | Search customers by a name or phone fragment. | query: q?, limit?, offset? | Array of customers, each with addresses[] |
| `create_customer` | `POST /customers` | Create a customer profile, optionally with a first address (saved as the default). | body: {name*, phone*, notes, address} | The new customer with addresses[] |
| `lookup_customer_by_phone` | `GET /customers/lookup` | Find the customer for an exact phone number, typed in any format. | query: phone* | The customer with saved addresses[] (404 if there is no such customer) |
| `get_customer` | `GET /customers/{customer_id}` | Get one customer with all saved addresses. Errors: 404 if unknown. | path: customer_id* | The customer with addresses[] |
| `update_customer` | `PATCH /customers/{customer_id}` | Edit a customer's name, phone, or notes. Only the fields you send change. | path: customer_id*; body: {(all optional) name, phone, notes} | The updated customer |
| `delete_customer` | `DELETE /customers/{customer_id}` | Delete a customer profile and their saved addresses. | path: customer_id* | Nothing (204) |
| `list_customer_orders` | `GET /customers/{customer_id}/orders` | List one customer's orders, newest first, paginated (page, page_size up to 100). | path: customer_id*; query: page?, page_size? | Page {items[] order summaries, total, page, page_size} |
| `add_customer_address` | `POST /customers/{customer_id}/addresses` | Save another delivery address for a customer (label, line1, area, city, notes). | path: customer_id*; body: {label, line1*, area, city, notes, is_default} | The new address {id, label, line1, area, city, notes, is_default} |
| `update_customer_address` | `PATCH /customers/{customer_id}/addresses/{address_id}` | Edit a saved address. Only the fields you send change; is_default=true makes it the default. Orders already placed keep their own copy of the address they used. | path: customer_id*, address_id*; body: {(all optional) label, line1, area, city, notes, is_default} | The updated address |
| `delete_customer_address` | `DELETE /customers/{customer_id}/addresses/{address_id}` | Delete a saved address. Orders already placed keep their own copy. Returns 204 with no body. | path: customer_id*, address_id* | Nothing (204) |

## Delivery (10)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `list_zones` | `GET /zones` | List delivery zones (area name + delivery fee). | query: include_inactive? | Array of zones {id, name, fee, is_active} |
| `create_zone` | `POST /zones` | Create a delivery zone with a fixed fee, e.g. name 'DHA', fee 200. The name should match the 'area' used in customer addresses so it is applied automatically. 409 if the name exists. | body: {name*, fee*, is_active} | The new zone |
| `update_zone` | `PATCH /zones/{zone_id}` | Change a zone's name, fee, or active flag. Only the fields you send change. | path: zone_id*; body: {(all optional) name, fee, is_active} | The updated zone |
| `delete_zone` | `DELETE /zones/{zone_id}` | Delete a delivery zone. Open orders that used it fall back to the default delivery fee the next time they are edited; finished orders are unaffected. Prefer update_zone with is_active=false. Returns 204. | path: zone_id* | Nothing (204) |
| `list_riders` | `GET /riders` | List delivery riders (inactive ones hidden unless include_inactive=true). Use when: you need a rider_id for assign_rider. | query: include_inactive? | Array of riders {id, name, phone, is_active} |
| `create_rider` | `POST /riders` | Add a delivery rider (name, optional phone). Returns the rider with its id. | body: {name*, phone, is_active} | The new rider |
| `update_rider` | `PATCH /riders/{rider_id}` | Edit a rider's name/phone, or set is_active=false when they leave (inactive riders cannot be assigned, history is kept). | path: rider_id*; body: {(all optional) name, phone, is_active} | The updated rider |
| `get_rider_cash_summary` | `GET /riders/cash-summary` | Show the unsettled cash-on-delivery money each rider is holding. | none | Array of {rider_id, rider_name, unsettled_total, payments (count)}; empty list = everything settled |
| `get_rider_unsettled_cash` | `GET /riders/{rider_id}/cash` | List one rider's individual unsettled cash collections (payment id, order id, amount, time) and their total. | path: rider_id* | {rider_id, unsettled_total, payments[]} - the individual cash collections (id, order_id, amount, ...) |
| `settle_rider_cash` | `POST /riders/{rider_id}/settlements` | Record that a rider handed their collected COD cash to the business. | path: rider_id*; body: {(all optional) payment_ids, note} | Settlement record {id, rider_id, amount, note, created_at} |

## Dashboard & Reports (13)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `get_live_counts` | `GET /reports/live` | Right-now operational snapshot - the first call to make when asked 'what's happening?' or 'what needs attention?'. Not date-filtered. | none | {new, confirmed, out_for_delivery, late, awaiting_online_payment, pending_online_links, cod_to_collect, unsettled_rider_cash, refunds_pending} |
| `get_sales_summary` | `GET /reports/summary` | Headline numbers for a period. Sales = total of orders DELIVERED in the period (cancelled and failed orders are excluded). | query: date_from?, date_to? | {sales, delivered_orders, average_order_value, delivery_fees, orders_received, cancelled_orders, cancelled_value, by_payment_method, money_received} |
| `get_sales_trend` | `GET /reports/sales-trend` | Sales over time, for charts and comparisons ('how are sales trending', 'this week vs last'). | query: group_by?, date_from?, date_to? | Array of {period, orders, sales} |
| `get_top_items` | `GET /reports/top-items` | Best-selling items by quantity in the period (limit default 10). Returns [{item, quantity, revenue}]. Use when asked what sells best. Params: date_from / date_to (default today). | query: limit?, date_from?, date_to? | Array of {item, quantity, revenue} |
| `get_bottom_items` | `GET /reports/bottom-items` | Worst-selling items in the period, including active menu items that sold zero. Returns [{item, quantity, revenue}]. Use when deciding what to remove or promote. Params: date_from / date_to (default today). | query: limit?, date_from?, date_to? | Array of {item, quantity, revenue} (includes items that sold zero) |
| `get_sales_by_category` | `GET /reports/by-category` | Sales and quantity by menu category for delivered orders in the period. Returns [{name, quantity, sales}] sorted by sales. Params: date_from / date_to (default today). | query: date_from?, date_to? | Array of {name, quantity, sales} |
| `get_sales_by_area` | `GET /reports/by-area` | Delivered orders and sales grouped by delivery area ('Unknown' when an address had no area). Use to see where demand is and to price zones. Params: date_from / date_to (default today). | query: date_from?, date_to? | Array of {name, orders, sales} |
| `get_sales_by_source` | `GET /reports/by-source` | Delivered orders and sales grouped by order source (phone, whatsapp, instagram, ...). Use to see which channels perform best. Params: date_from / date_to (default today). | query: date_from?, date_to? | Array of {name, orders, sales} |
| `get_peak_hours` | `GET /reports/peak-hours` | Orders received per local hour of day (24 buckets, cancelled orders excluded). Use to plan staffing and riders. Returns [{hour, orders}]. Params: date_from / date_to (default today). | query: date_from?, date_to? | 24 entries {hour, orders} |
| `get_delivery_performance` | `GET /reports/delivery-performance` | Delivery speed and reliability for the period: delivered count, average minutes from confirmation to delivery and from dispatch to delivery, late deliveries (after their estimate), failed delivery attempts, and delivered orders per rider. Params: date_from / date_to (default today). | query: date_from?, date_to? | {delivered, avg_minutes_confirm_to_delivery, avg_minutes_dispatch_to_delivery, late_deliveries, failed_delivery_attempts, orders_per_rider[]} |
| `get_cancellations_and_discounts` | `GET /reports/cancellations` | Why money was lost or given away in the period: cancellations (count, value, grouped by reason), refunds (count, amount, by reason), and discounts on delivered orders (orders, amount, by reason). Use to spot patterns or abuse. Params: date_from / date_to (default today). | query: date_from?, date_to? | {cancelled, refunds, discounts}, each with count/amount and by_reason[] |
| `export_orders_csv` | `GET /reports/export/orders.csv` | Download orders as a CSV file, one row per order. | query: date_from?, date_to?, status?, payment_status?, payment_method?, rider_id?, source? | A CSV file (not JSON) |
| `export_summary_pdf` | `GET /reports/export/summary.pdf` | Download a printable PDF sales summary for the period: headline figures, top and bottom items, sales by category. Use when a printed or shareable report is requested. Params: date_from / date_to (default today). | query: date_from?, date_to? | A PDF file (not JSON) |

## Settings (3)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `read_settings` | `GET /settings` | Read the restaurant's configuration: business details, currency, timezone, tax %, service charge %, default delivery fee, minimum order, free-delivery threshold, default delivery minutes, operating hours, whether orders are accepted, and whether online orders must be paid before confirmation. | none | All settings: business details, tax, delivery rules, hours, order rules |
| `update_settings` | `PATCH /settings` | Change the restaurant configuration. Only the fields you send change. | body: {(all optional) business_name, phone, email, address, logo_url, invoice_header, invoice_footer, currency, timezone, default_country_code, order_number_prefix, tax_rate, service_charge_rate, default_delivery_fee, +8 more} | The updated settings |
| `get_restaurant_status` | `GET /settings/status` | Is the restaurant taking orders right now? | none | {accepting_orders, enforce_hours, open_time, close_time, open_now} |

## Meta (1)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `health_check` | `GET /health` | Liveness check: returns {"status": "ok"} when the API and its database both respond. | none | {status: ok} |

## Public (1)

| Operation | Call | What it does | Inputs | Returns |
|---|---|---|---|---|
| `get_public_invoice` | `GET /public/invoices/{token}` | Public invoice PDF fetched by secret token (from get_invoice_share_links). Intended for customers' browsers, not for agents - agents should use print_order_document. | path: token* | A PDF file (not JSON) |
