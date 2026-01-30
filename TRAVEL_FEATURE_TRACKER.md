## Travel Support Feature Tracker

High-level goal: extend `UnifiedAgent` to support travel assistance (itinerary planning, flight search, and mock booking with payment integration).

### Phase 1 – Design & Scope

- [x] Define supported travel tasks (planning, flight search, mock booking)
- [x] Decide integration strategy (local mock travel MCP server)
- [ ] Document non-goals and limitations in README / instructions

### Phase 2 – Travel MCP Server (`travel-server`)

- [x] Create travel MCP server entry file (e.g., `travel-server.js`)
- [x] Define mock flight data source (static JSON or in-memory list)
- [x] Implement `travel.search_flights` tool
  - [x] Accept origin, destination, date, trip_type, passengers (currently origin/destination/date)
  - [x] Return list of flights with `flightId`, `airline`, times, duration, price, cabin
- [x] Implement `travel.get_flight` tool
  - [x] Validate `flightId`
  - [x] Return detailed flight information
- [x] Implement `hold_flight_booking` tool
  - [x] Accept `flightId`, passenger details, contact info
  - [x] Create in-memory booking with `bookingId`, amount, currency, status `held`
- [x] Implement `travel.get_flight_booking_status` tool
  - [x] Return booking details (`bookingId`, status, amount)
- [ ] Add basic logging and error handling to travel server

### Phase 3 – Wire Travel MCP into `UnifiedAgent`

- [x] Define `TRAVEL_CMD` constant in `unified_agent.py`
- [x] Add `self.travel_client: McpClient | None` to `UnifiedAgent`
- [x] Implement `_ensure_travel()` initializer mirroring `_ensure_blinkit` / `_ensure_payment`
- [ ] Verify travel MCP client starts and initializes correctly

### Phase 4 – LM-Visible Travel Tools in `UnifiedAgent`

Define as async tools inside `UnifiedAgent.__init__` and register with `self.agent.tool(...)`:

- [ ] `search_flights_tool`
  - [x] Inputs: origin, destination, date, optional trip_type, return_date, passengers
  - [x] Call `travel.search_flights` via `self.travel_client`
  - [x] Normalize response shape for the LLM
- [ ] `get_flight_tool`
  - [x] Input: `flight_id`
  - [x] Call `travel.get_flight` and return full details
- [ ] `hold_flight_booking_tool`
  - [x] Inputs: `flight_id`, passenger_name, contact_email
  - [x] Call `hold_flight_booking` and return booking object
- [ ] `get_flight_booking_status_tool`
  - [x] Input: `booking_id`
  - [x] Call `travel.get_flight_booking_status` and return status
- [x] Register all four tools with `self.agent.tool(...)`

### Phase 5 – Instructions & Prompt Updates

- [x] Extend core `instructions` in `UnifiedAgent.__init__` with Travel Assistant persona
  - [x] Describe supported travel capabilities
  - [x] Clarify that flight data and bookings are mock/simulated
- [x] Add “WHEN TO USE TRAVEL TOOLS” section
  - [x] Outline when to plan itinerary vs call tools
  - [ ] Include examples: trip planning, flight search, booking flow
- [ ] Add example flows:
  - [ ] Plan 3–5 day trips (with rough day-by-day structure)
  - [ ] Flight search + user selection + booking + payment

### Phase 6 – Payment Flow Integration for Bookings

- [ ] Decide booking → payment mapping:
  - [ ] Use `booking_id` as `orderId` for `create_payment`
- [ ] Instruct agent to:
  - [ ] Use `hold_flight_booking_tool` before payment when user says “book”
  - [ ] Use `create_payment(amount, order_id=booking_id)`
  - [ ] Then `check_payment_status(payment_id)` and report result
- [ ] (Optional) Update travel MCP booking status to `paid` after successful payment

### Phase 7 – Safety & UX Refinements

- [ ] Add explicit safety rules to instructions:
  - [ ] No guarantees of real airline ticket issuance
  - [ ] Clarify that flights and bookings are examples/mock
- [ ] Ensure NPCI + travel queries are handled clearly (separate sections in replies)
- [ ] Avoid double-asking for confirmations (booking & payment)

### Phase 8 – Testing & Validation

- [ ] Manual tests for travel MCP tools directly
  - [ ] `travel.search_flights`
  - [ ] `travel.get_flight`
  - [ ] `hold_flight_booking`
  - [ ] `travel.get_flight_booking_status`
- [ ] Manual tests via `UnifiedAgent` CLI or API server
  - [ ] Pure NPCI / general queries (ensure no travel tools triggered)
  - [ ] Itinerary-only prompts (ensure no travel tool unless flights requested)
  - [ ] Flight search prompts (ensure `search_flights_tool` used)
  - [ ] Booking + payment prompts (ensure hold → payment → status flow)
- [ ] Adjust instructions or tool schemas based on observed LLM behavior

### Phase 9 – Documentation & Cleanup

- [ ] Update main project README with travel feature overview
- [ ] Document travel MCP server usage (commands, requirements)
- [ ] Add notes about limitations and future enhancements (hotels, trains, real APIs)
- [ ] Review logs and remove overly noisy debug output if needed

