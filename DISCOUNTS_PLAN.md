# Discounts Feature – Implementation Plan (Domain-specific)

Discounts are **domain-specific**: **Blinkit** (shopping) and **Travel** each expose and apply their own discounts via their existing MCP servers. Applied at checkout for that domain.

---

## 1. High-level flow

- **Today:** Checkout = get total (cart or booking) → `create_payment(amount, order_id)` → `check_payment_status(payment_id)`.
- **With discounts:** Checkout = get total → **optionally** list that domain’s eligible discounts → show user → if user picks one, apply it to get final amount → `create_payment(final_amount, order_id)` → `check_payment_status(payment_id)`.
- **Blinkit checkout:** Use Blinkit MCP discount tools (cart total, Blinkit-specific promos).
- **Travel checkout:** Use Travel MCP discount tools (booking amount, travel-specific offers).
- Payment MCP is unchanged; it always receives the final amount to charge.

---

## 2. Blinkit (shopping) – discount tools on existing Blinkit MCP

- **Where:** `backend/servers/dist/blinkit-server.js` (or source that compiles to it). Add new tools to the existing Blinkit server.
- **Tools:**

| Tool | Purpose | Input | Output |
|------|----------|--------|--------|
| `blinkit.list_discounts` | List Blinkit promos eligible for cart/amount | `amount` (number), `orderId` (optional) | List of `{ code, description, discountAmount or percent, finalAmount }` |
| `blinkit.apply_discount` | Apply a Blinkit code and get final amount | `code` (string), `amount` (number), `orderId` (optional) | `{ valid, finalAmount, message }` |

- **Behaviour (v1):** Mock 2–3 Blinkit-style offers (e.g. “FIRST50” ₹50 off above ₹300, “BLINK10” 10% off). `list_discounts` returns only those eligible for the given `amount`; `apply_discount` validates the code and returns `finalAmount` for `create_payment`.

---

## 3. Travel – discount tools on existing Travel MCP

- **Where:** `backend/servers/travel-server.js`. Add new tools to the existing Travel server.
- **Tools:**

| Tool | Purpose | Input | Output |
|------|----------|--------|--------|
| `travel.list_discounts` | List travel offers eligible for a booking amount | `amount` (number), `orderId` (optional), `type` (optional: `"flight"` \| `"hotel"` \| `"cab"`) | List of `{ code, description, discountAmount or percent, finalAmount }` |
| `travel.apply_discount` | Apply a travel discount code and get final amount | `code` (string), `amount` (number), `orderId` (optional) | `{ valid, finalAmount, message }` |

- **Behaviour (v1):** Mock 2–3 travel-style offers (e.g. “FLY20” ₹200 off flights, “STAY15” 15% off hotels). Same pattern: list eligible, apply returns final amount.

---

## 4. Backend Python changes

- **No new MCP client.** Use existing `blinkit_client` and `travel_client`.
- **Blinkit discount tools:** In `backend/tools/shopping.py` (or a small `discounts.py` that only wraps Blinkit + Travel), add:
  - `list_blinkit_discounts_tool(amount, order_id=None)` → calls `blinkit.list_discounts`.
  - `apply_blinkit_discount_tool(code, amount, order_id=None)` → calls `blinkit.apply_discount`; agent uses `finalAmount` in `create_payment` for cart checkout.
- **Travel discount tools:** In `backend/tools/travel.py` (or the same discounts module), add:
  - `list_travel_discounts_tool(amount, order_id=None, booking_type=None)` → calls `travel.list_discounts`.
  - `apply_travel_discount_tool(code, amount, order_id=None)` → calls `travel.apply_discount`; agent uses `finalAmount` in `create_payment` for travel checkout.
- **Registration:** Register Blinkit discount tools with the rest of shopping tools; register Travel discount tools with the rest of travel tools. No new client or `_ensure_*` for discounts.

---

## 5. Checkout flow (agent behaviour)

- **Shopping (Blinkit) checkout:**  
  When user confirms checkout: `view_cart()` → total → `list_blinkit_discounts_tool(amount=total)` → show Blinkit offers → if user picks a code, `apply_blinkit_discount_tool(code, total)` → `create_payment(finalAmount, order_id)` → `check_payment_status`. If no discount, `create_payment(total, order_id)` as today.

- **Travel checkout:**  
  After held booking: total = booking amount → `list_travel_discounts_tool(amount=total, order_id=booking_id, booking_type=...)` → show travel offers → if user picks a code, `apply_travel_discount_tool(code, total, booking_id)` → `create_payment(finalAmount, order_id=booking_id)` → `check_payment_status`. If no discount, `create_payment(total, order_id=booking_id)` as today.

---

## 6. Instructions (core / shopping / travel)

- **Core:** One line: “At checkout, offer domain-specific discounts: for **shopping** use Blinkit discount tools; for **travel** use Travel discount tools; then use the final amount (after any applied discount) in create_payment.”
- **Shopping:** In the checkout step: “Before create_payment, optionally call list_blinkit_discounts_tool(amount=cart_total). If user selects a code, call apply_blinkit_discount_tool and use finalAmount in create_payment.”
- **Travel:** In the payment step: “Before create_payment, optionally call list_travel_discounts_tool(amount=booking_amount, order_id=booking_id). If user applies a code, call apply_travel_discount_tool and use finalAmount in create_payment.”

---

## 7. File checklist

| Item | Action |
|------|--------|
| `backend/servers/dist/blinkit-server.js` (or source) | **Edit** – Add `blinkit.list_discounts`, `blinkit.apply_discount` |
| `backend/servers/travel-server.js` | **Edit** – Add `travel.list_discounts`, `travel.apply_discount` |
| `backend/tools/shopping.py` | **Edit** – Add `list_blinkit_discounts_tool`, `apply_blinkit_discount_tool` (or new `backend/tools/discounts.py` and export from `__init__`) |
| `backend/tools/travel.py` | **Edit** – Add `list_travel_discounts_tool`, `apply_travel_discount_tool` |
| `backend/instructions/core.py` | **Edit** – One line on domain-specific discounts at checkout |
| `backend/instructions/shopping.py` | **Edit** – Checkout: optional Blinkit list → apply → create_payment(finalAmount) |
| `backend/instructions/travel.py` | **Edit** – Payment: optional Travel list → apply → create_payment(finalAmount) |

No new server, no new MCP client; only domain servers and their Python tool wrappers.

---

## 8. Optional (later)

- Stricter eligibility per domain (min order, category, first booking, etc.) inside each server.
- Persist applied discount per order in the domain server for analytics.
