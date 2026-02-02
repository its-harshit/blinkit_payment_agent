# Conversation Summariser – Implementation Plan

## Goal

After every **4 conversation turns** (4 full user+assistant exchanges), call a **summariser LLM** that extracts **concrete, important details** from the chat. This summary is then passed to the main LLM as context so that the main LLM can continue correctly without re-scanning long history.

**Important:** The main LLM does **more than travel** – it handles NPCI support, shopping (Blinkit), payments, recipe/cab, etc. So the summariser and summary must be **multi-domain**: they should capture relevant state for **whatever the user is doing** (travel, shopping, grievance, or a mix), not only travel.

## Use Case – Travel (example)

1. User: "I want a solo trip for 5 days from Delhi to Goa, starting tomorrow."  
2. Agent: books flight (e.g. DEL → GOA, tomorrow).  
3. User: "Book a hotel."  
4. Agent should **already know** from the summary: **solo** → 1 guest; **5 days, starting tomorrow** → check-in and check-out dates; **destination Goa** → hotel city = GOA. So it calls search_hotels with the right dates and guests without asking again.

Other domains: if the user was shopping (recipe ingredients planned, cart state), the summary should capture that so "add to cart" or "checkout" can use it. If they were asking about a UPI grievance, the summary can hold txn ID, VPA, etc. so the main LLM doesn’t re-ask.

## When to Run the Summariser

- **Trigger:** After every **4 conversation exchanges** (4 pairs of user message + assistant response).
- **Where:** At the end of `UnifiedAgent.run()`, **after** appending the new (user_message, assistant_response) to `conversation_history`. So when `len(conversation_history)` becomes 4, 8, 12, … run the summariser.

## Incremental Summarisation (2nd+ time)

- **First time (4 turns):** Pass only the **4 new turns** to the summariser. No previous summary. Output = first summary.
- **Second time (8 turns) and after:** Do **not** pass the whole chat. Pass:
  1. The **previous summary** (from the last summariser run).
  2. Only the **4 new conversation turns** (the exchanges since the last summary).
  3. Instruction: *"Merge the previous summary with the new details from these conversation turns. Output a single updated summary that includes all concrete details (travel, shopping, NPCI, or other – whatever is relevant). Overwrite or add fields as needed; do not duplicate."*

This way:
- **Token input to summariser stays bounded** (old summary + 4 exchanges), instead of growing with full chat history.
- **Cost and latency** stay stable as the conversation gets long.
- The main LLM still receives one **current state** summary that reflects the whole conversation so far.

## What the Summary Should Contain (Multi-Domain, Structured)

The main LLM handles **travel, shopping, NPCI, payments, cabs, recipe**, etc. So the summary should capture **concrete details for whichever domain(s) the conversation touches**, not only travel. Suggested structure (include only sections that are relevant):

- **Travel (if discussed):** trip_type, duration_days, start_date, origin_city, destination_city; what’s booked (flight/hotel/cab with key IDs); what’s pending; for next step (e.g. for hotel: check_in, check_out, guests, city).
- **Shopping / recipe (if discussed):** e.g. recipe or dish name, ingredients planned or in cart, cart total, whether user said they want to checkout.
- **NPCI / UPI (if discussed):** e.g. txn ID, VPA, bank, issue type, so the main LLM doesn’t re-ask.
- **Other:** Any other concrete facts (preferences, names, contact) that the main LLM should reuse.

Use a **consistent format** (e.g. key-value lines or short bullet list, with optional section headers like "Travel:", "Shopping:") so the main LLM can parse it. Only populate sections that apply; leave others out or write "none".

## Where the Summary Goes (Main LLM Context)

- **Storage:** On the agent instance, e.g. `self.conversation_summary: str = ""`. Updated each time the summariser runs (every 4 turns).
- **When building the prompt for the main agent:** In `run()`, when constructing `full_message`:
  - **If** `self.conversation_summary` is set:
    - Prepend: `**Conversation summary (use for bookings and next steps):**\n{self.conversation_summary}\n\n`
    - Then add **only the last 1 exchange** (last user + assistant) as "**Last exchange:** ...", then "**Current question:**" + user_message.
  - **Else:** Keep current behaviour: last `max_history_exchanges` (e.g. 3–4) full exchanges + current question.
- So the main LLM sees: **summary** (compact state) + **last exchange** (for continuity) + **current user message**. This reduces tokens and gives the main LLM the important details in one place.

## Implementation Outline

### 1. UnifiedAgent (backend/unified_agent.py)

- Add:
  - `self.conversation_summary: str = ""`
  - `self._summariser_model` (same or smaller model) and a small **summariser agent** (e.g. pydantic_ai Agent with a **multi-domain** system prompt: extract concrete details for travel, shopping/recipe, NPCI/UPI, and other context as relevant; output one structured summary in a consistent format; see summariser prompt below).
- **Summariser prompt (system):**  
  - "You are a conversation summariser for a support agent that handles **travel** (flights, hotels, cabs), **shopping** (Blinkit, recipe ingredients, cart), **NPCI/UPI** (grievances, txn details), and **payments**. You will receive either (A) a conversation excerpt only, or (B) a previous summary and new conversation turns. If (A), extract concrete facts and output one structured summary. If (B), merge the previous summary with the new details from the turns; output a single updated summary (same format). Include only what is relevant: **Travel** – trip type, guests, duration_days, start_date (YYYY-MM-DD), origin/destination city, what's booked (flight/hotel/cab + IDs), what's pending, for next step (e.g. for hotel: check_in, check_out, guests, city). **Shopping** – recipe/dish, ingredients or cart state, checkout intent. **NPCI/UPI** – txn ID, VPA, bank, issue. **Other** – names, contact, preferences. Keep key-value or short bullet style; use section labels (Travel:, Shopping:, etc.) only when that domain appears; overwrite or add as new info appears; do not duplicate."
- **Method** `_run_summariser(self) -> str`:
  - If **no previous summary** (first run): input = only the **last 4 exchanges** (the 4 we just completed). Prompt: "Summarise this conversation: ..."
  - If **previous summary exists**: input = **previous summary** + "**New conversation turns:**" + only the **last 4 exchanges**. Prompt: "Merge the previous summary below with the new conversation turns. Output one updated summary (same format)."
  - Call the summariser agent; return the new summary string. Store it in `self.conversation_summary` and use it for the next run.
- In `run()`:
  - **After** we append `(user_message, assistant_response)` to `conversation_history`, check: if `len(self.conversation_history) % 4 == 0`, call `self.conversation_summary = await self._run_summariser()` (and catch errors so a failed summarisation doesn’t break the run).
  - **Before** building `context_parts`: if `self.conversation_summary` is non-empty, set context to: summary block + last 1 exchange + "**Current question:**". Otherwise keep current behaviour (last N exchanges + current question).

### 2. Summariser Model

- Use the **same model** as the main agent for simplicity, or a **smaller/cheaper** model (e.g. same API, smaller model name) to save cost. The summariser is a single non-streaming call every 4 turns.

### 3. Instructions (main agent)

- Add one line to the main agent instructions (e.g. in core):  
  - "When you see a **Conversation summary** at the start of the context, use it so you don’t re-ask or re-infer: for **travel** use dates, guests, city from the summary when booking hotel/cab; for **shopping** use recipe/cart state; for **NPCI** use txn/VPA/details already mentioned; for **other** use any names, contact, or preferences from the summary."

### 4. Edge Cases

- **First 1–3 turns:** No summary yet; main LLM gets raw conversation (current behaviour).
- **Summary fails:** If `_run_summariser()` raises, log and leave `conversation_summary` unchanged; main LLM still gets raw last N exchanges.
- **Do not clear the summary** when the user switches topic. The user might do travel → then UPI/shopping → then return to travel. The summary should keep merging so that when they come back to the old topic, the main LLM still has that context (e.g. trip dates, what was booked) from the summary.

## File Checklist

| Area | Change |
|------|--------|
| `backend/unified_agent.py` | Add `conversation_summary`, summariser agent + prompt, `_run_summariser()`, call it every 4 turns after append, and use summary + last 1 exchange when building context. |
| `backend/instructions/*.py` (optional) | One line: use Conversation summary for bookings when present. |

## Summary

- **When:** After every 4 conversation exchanges (at end of `run()`, after appending to `conversation_history`).
- **Input (incremental):**
  - **First run (4 turns):** Last 4 exchanges only.
  - **Later runs (8, 12, … turns):** Previous summary + last 4 new exchanges only. Instruction: merge and output one updated summary.
- **Output:** Single structured summary, **multi-domain** – travel (when relevant), shopping/recipe (when relevant), NPCI/UPI (when relevant), other. Same format/style every time so the main LLM can use it.
- **Where it goes:** Stored in `self.conversation_summary`; prepended to main LLM context as "**Conversation summary:** ..." plus last 1 exchange and current question.
- **Main use case:** So the main LLM doesn’t forget or re-ask: travel → dates, guests, city for hotel/cab; shopping → recipe/cart for add/checkout; NPCI → txn/VPA for follow-up; etc.
