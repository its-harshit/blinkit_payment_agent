# Cab Booking & Trip-Level Integration – Plan

This document captures the plan for **cab booking** (Uber-like, same-city) and **trip-level integration** so the agent can maintain flight + hotel + cab in one flow. It aligns with the discussions: cab in the Travel server, no separate LLM parser/sub-agent for now, and optional trip-level features to help the LLM maintain context.

---

## Goals

1. **Cab booking** – User can book a cab between two places **within a city** (Uber-like). Cabs are always available (simulated). Works standalone (“book cab from CP to airport”) and inside the travel flow (“cab from airport to my hotel”).
2. **Trip-level integration** – A **trip** (itinerary) groups flight, hotel, and cab bookings. The server can resolve cab segments from the trip (e.g. `airport_to_hotel`) so the LLM doesn’t have to re-pass origin/destination strings. Enables “what’s in my trip?” and “add return cab” without fragile param passing.
3. **No extra LLM parser or cab sub-agent** – Main agent fills cab params from conversation (and from trip/tool results). Optional `parse_cab_request` tool only if we see consistent param mistakes later.

---

## Architecture Summary

| Component | Responsibility |
|-----------|----------------|
| **Travel MCP server** (`travel-server.js`) | Flights, hotels, **cabs**, and **trips**. Same server, one `travel_client` in Python. |
| **Cab tools** | `search_cabs`, `book_cab`, `get_cab_booking_status`. Optional: `search_cabs(trip_id, segment)` when trip exists. |
| **Trip (Phase 2)** | `create_trip`, optional `trip_id` on flight/hotel/cab bookings, `get_trip`, and cab segment resolution from trip. |
| **Main agent** | Same UnifiedAgent; new travel instructions and tools for cab (and trip). No dedicated cab agent or parser unless we add `parse_cab_request` later. |

---

## Phase 1: Cab Booking (Standalone + Travel Flow Without Trip)

**Scope:** Add cab tools to the Travel server and to the Python backend. Cab works with explicit `origin`, `destination`, `city`. Travel flow uses flight/hotel results to fill those params (no trip_id yet).

### 1.1 Travel server (Node.js)

**New tools:**

| Tool | Purpose | Parameters | Returns |
|------|---------|------------|---------|
| `travel.search_cabs` | Search cab options between two places in a city | `origin`, `destination`, `city` | `{ cabs: [{ cabId, type, fare, etaMinutes, vehicleDescription }] }` |
| `travel.book_cab` | Book a selected cab | `cabId`, `passengerName`, `contact` | `{ booking: { cabBookingId, cabId, passengerName, contact, fare, etaMinutes, status } }` |
| `travel.get_cab_booking_status` | Get cab booking status | `cabBookingId` | `{ booking: { ... } }` |

**Behaviour:**

- **Same-city validation:** Require `city`. Treat all requests as same-city (origin and destination in that city). Reject or cap if you add a max distance later (e.g. 50 km).
- **Always available:** For any valid `(origin, destination, city)` return 2–3 simulated options (e.g. Economy, Sedan, SUV) with deterministic or random-but-realistic fare and ETA (e.g. fare from simple distance heuristic 5–25 km, ETA 10–30 min).
- **In-memory store:** e.g. `CAB_OPTIONS` (or generate on the fly) and `CAB_BOOKINGS = new Map()` keyed by `cabBookingId`.

**Files to change:** `backend/servers/travel-server.js` (add tools to `tools` array and handle in `tools/call`).

### 1.2 Python backend

**New tools (same Travel MCP client):**

- `search_cabs_tool(origin, destination, city)` – calls `travel.search_cabs`, returns `{ cabs, time_taken? }`.
- `book_cab_tool(cab_id, passenger_name, contact)` – calls `travel.book_cab`, returns booking.
- `get_cab_booking_status_tool(cab_booking_id)` – calls `travel.get_cab_booking_status`, returns booking.

**Registration:** In `unified_agent.py`, add these tools from a new module e.g. `tools/cabs.py` (or extend `tools/travel.py` with cab tools). Reuse existing `travel_client` and `_ensure_travel()`.

**Instructions:** Extend `instructions/travel.py` (or add `instructions/cabs.py` and compose in `get_full_instructions()`):

- Cab is supported: same-city only; use `search_cabs_tool(origin, destination, city)` then `book_cab_tool`; pay with `create_payment` + `check_payment_status`.
- **Standalone:** “When user asks for a cab only, get origin, destination, and city from the message; if city is missing, ask once or infer from airport/landmark.”
- **Travel flow (without trip):** “After booking flight and hotel, offer cab from airport to hotel and hotel to airport. Use arrival airport and hotel address from the latest flight and hotel booking results as origin/destination and city.”
- Add 1–2 short examples (e.g. “Cab from CP to airport” → `search_cabs(origin='Connaught Place', destination='IGI Airport', city='Delhi')`).

**Deliverables:**

- [x] Travel server: `travel.search_cabs`, `travel.book_cab`, `travel.get_cab_booking_status` implemented and listed in `tools/list`.
- [x] Python: `search_cabs_tool`, `book_cab_tool`, `get_cab_booking_status_tool` in `tools/cabs.py`, registered on UnifiedAgent.
- [x] Instructions: travel instructions updated with cab flow, examples, and travel-flow cab offer.

---

## Phase 2: Trip-Level Integration

**Scope:** Introduce a **trip** (itinerary) in the Travel server. Create/link trip, attach flight/hotel/cab bookings to it, resolve cab segments from trip, and support “what’s in my trip?”.

### 2.1 Travel server – Trip model and storage

- **Trip:** `tripId`, `destinationCity` (or `city`), optional `createdAt`. Store in e.g. `TRIPS = new Map()`.
- **Create trip:** New tool `travel.create_trip` with e.g. `{ city }` or `{}` → returns `{ trip: { tripId, city } }`.
- **Link bookings to trip (optional `tripId` in params):**
  - `hold_flight_booking(..., tripId?)` – if `tripId` provided, store `tripId` on the booking and add booking ref to trip.
  - `travel.hold_hotel_booking(..., tripId?)` – same.
  - `travel.book_cab(..., tripId?, segment?)` – same; `segment` is e.g. `airport_to_hotel` or `hotel_to_airport` for resolution (see below).

**Trip structure (server-side):** For each trip, maintain:

- `flightBooking` (or `flightBookingId`) – has arrival airport, arrival city, etc.
- `hotelBooking` (or `hotelBookingId`) – has hotel address, city.
- `cabBookings` – array of cab booking refs with segment.

So when resolving cab segment we have: arrival airport, hotel address, city, and (for return) departure airport from same or return flight.

### 2.2 Cab segment resolution from trip

- **New overload or behaviour of `travel.search_cabs`:**
  - **Option A:** `search_cabs(origin, destination, city)` – unchanged for standalone.
  - **Option B:** `search_cabs(tripId, segment)` where `segment` is `airport_to_hotel` or `hotel_to_airport`. Server looks up trip’s flight and hotel, sets origin/destination/city and returns same shape `{ cabs: [...] }`.
- **Validation:** If trip has no flight or no hotel for the requested segment, return a clear error (e.g. “Trip has no hotel” for `airport_to_hotel`).

**Tool schema (example):**

- `travel.search_cabs`: either  
  - `origin`, `destination`, `city` (standalone), or  
  - `tripId`, `segment` (`"airport_to_hotel"` | `"hotel_to_airport"`).
- Server implements both; Python can expose two tools or one tool with optional params.

### 2.3 Get trip

- **New tool:** `travel.get_trip(tripId)` → returns trip summary: flight booking (if any), hotel booking (if any), cab bookings (if any), and `destinationCity`. So the agent can answer “what’s in my trip?” and decide what to offer next.

### 2.4 Python backend – Trip and cab-by-segment

- **New tools:**  
  - `create_trip_tool(city?)` – calls `travel.create_trip`, returns `{ trip }`.  
  - `get_trip_tool(trip_id)` – calls `travel.get_trip`, returns trip summary.  
  - Optionally: `search_cabs_tool(trip_id=..., segment=...)` in addition to `search_cabs_tool(origin=..., destination=..., city=...)` (or single tool with optional params).
- **Extend flight/hotel/cab tools** to pass `trip_id` when the agent has an active trip (e.g. from conversation or from `create_trip` result).

**Instructions:**

- “When the user is booking a multi-step trip (flight + hotel + cab), create or reuse a trip: call `create_trip` (or get existing trip_id from context), then book flight and hotel with `trip_id`. For cab, use `search_cabs(trip_id=..., segment='airport_to_hotel')` or `'hotel_to_airport'` so the server fills origin/destination from the trip. Use `get_trip(trip_id)` when the user asks what’s in their trip or what’s next.”
- “If the user only wants a cab (no flight/hotel), use `search_cabs(origin, destination, city)` without trip_id.”

**Deliverables:**

- [ ] Travel server: `TRIPS` store, `travel.create_trip`, `travel.get_trip`, flight/hotel/cab bookings accept optional `tripId` and link to trip.
- [ ] Travel server: `search_cabs(tripId, segment)` resolves origin/destination/city from trip; same response shape as standalone search.
- [ ] Python: `create_trip_tool`, `get_trip_tool`; cab search supports trip_id + segment; instructions updated for trip-based flow and “what’s in my trip?”.

---

## Phase 3: Optional Improvements (Later)

- **parse_cab_request tool (only if needed):** If the main agent often gets origin/destination/city wrong, add a single tool that takes the user message (and maybe last turn) and returns `{ origin, destination, city }`. Agent calls it when unsure, then calls `search_cabs` with that result. No new sub-agent.
- **Stricter validation:** Max distance per city, or reject obviously inter-city requests (e.g. “Delhi to Mumbai”) in the server with a clear error message.
- **Trip in response shape:** Ensure flight and hotel booking responses include fields like `arrivalAirport`, `arrivalCity`, `hotelAddress`, `hotelCity` so the agent (and trip resolution) can use them reliably.

---

## Implementation Order

1. **Phase 1** – Cab in Travel server + Python tools + instructions (standalone + travel flow without trip). No trip_id yet.
2. **Phase 2** – Trip model, create_trip, get_trip, link flight/hotel/cab to trip, search_cabs(trip_id, segment). Update instructions for trip-based flow.
3. **Phase 3** – Only if needed: parse_cab_request, validation tweaks, response shape tweaks.

---

## File Checklist (Quick Reference)

| Area | Files |
|------|--------|
| Travel server | `backend/servers/travel-server.js` (cab tools, then trip + segment resolution) |
| Python tools | `backend/tools/cabs.py` (new) or `backend/tools/travel.py` (extend) |
| Instructions | `backend/instructions/travel.py` and/or `backend/instructions/cabs.py`, `backend/instructions/__init__.py` |
| Agent registration | `backend/unified_agent.py` (import and register cab tools, then trip tools) |

---

## Summary

- **Cab:** Same-city only, always available (simulated), in Travel server; standalone and as part of travel flow.
- **Trip:** Optional trip_id and segment-based cab search so the LLM can maintain “the trip” and the server resolves cab origin/destination.
- **No parser/sub-agent** for now; optional `parse_cab_request` later if we see param confusion.
- Implement in two phases: Phase 1 = cab only (params by agent), Phase 2 = trip-level (create_trip, get_trip, search_cabs by segment).
