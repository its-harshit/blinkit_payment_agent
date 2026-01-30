"""Travel tools (flights + hotels) for the unified agent."""
import time
from typing import Annotated, Any

from pydantic_ai import RunContext

from ..core import parse_mcp_text_result


def make_travel_tools(agent: Any):
    """Return travel tool functions that close over the given agent."""
    assert agent is not None

    async def search_flights_tool(
        ctx: RunContext,
        origin: Annotated[str, "Origin airport/city code (e.g., DEL, BLR)"],
        destination: Annotated[str, "Destination airport/city code (e.g., BOM, GOI)"],
        date: Annotated[str, "Departure date in YYYY-MM-DD format"],
        passengers: Annotated[int | None, "Number of passengers (defaults to 1)"] = None,
    ):
        """Search available flights between two cities on a given date."""
        start_time = time.time()
        pax = passengers or 1
        agent.log.info(
            "🛫 TOOL CALL: search_flights_tool(origin=%s, destination=%s, date=%s, passengers=%d)",
            origin, destination, date, pax,
        )
        try:
            await agent._ensure_travel()
            params = {"origin": origin, "destination": destination, "date": date}
            agent.log.debug("Calling MCP tool: travel.search_flights with params: %s", params)
            result = await agent.travel_client.call_tool("travel.search_flights", params)
            flights = parse_mcp_text_result(result, "flights") or []
            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: search_flights_tool found %d flights (took %.2fs)",
                len(flights), elapsed,
            )
            if flights:
                agent.log.debug("First flight: %s", flights[0])
            return {"flights": flights, "time_taken": elapsed}
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error(
                "❌ TOOL ERROR: search_flights_tool failed after %.2fs - %s",
                elapsed, str(e),
            )
            raise

    async def get_flight_tool(
        ctx: RunContext,
        flight_id: Annotated[str, "Flight ID returned from search_flights_tool (e.g., TRV-001)"],
    ):
        """Get detailed information for a specific flight."""
        agent.log.info("🛫 TOOL CALL: get_flight_tool(flight_id=%s)", flight_id)
        try:
            await agent._ensure_travel()
            params = {"flightId": flight_id}
            agent.log.debug("Calling MCP tool: travel.get_flight with params: %s", params)
            result = await agent.travel_client.call_tool("travel.get_flight", params)
            flight = parse_mcp_text_result(result, "flight") or {}
            agent.log.info(
                "✅ TOOL SUCCESS: get_flight_tool retrieved flight: %s",
                flight.get("flightId", flight_id),
            )
            agent.log.debug("Flight details: %s", flight)
            return flight
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: get_flight_tool failed - %s", str(e))
            raise

    async def hold_flight_booking_tool(
        ctx: RunContext,
        flight_id: Annotated[str, "Flight ID to book (from search_flights_tool)"],
        passenger_name: Annotated[str, "Passenger full name"],
        contact_email: Annotated[str, "Passenger contact email"],
    ):
        """Create a held booking for a selected flight."""
        start_time = time.time()
        agent.log.info(
            "🧾 TOOL CALL: hold_flight_booking_tool(flight_id=%s, passenger_name=%s)",
            flight_id, passenger_name,
        )
        try:
            await agent._ensure_travel()
            params = {
                "flightId": flight_id,
                "passengerName": passenger_name,
                "contactEmail": contact_email,
            }
            agent.log.debug("Calling MCP tool: hold_flight_booking with params: %s", params)
            result = await agent.travel_client.call_tool("hold_flight_booking", params)
            booking = parse_mcp_text_result(result, "booking") or {}
            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: hold_flight_booking_tool created booking %s (status=%s, amount=₹%.2f, took %.2fs)",
                booking.get("bookingId", "unknown"),
                booking.get("status", "unknown"),
                booking.get("amount", 0),
                elapsed,
            )
            agent.log.debug("Booking details: %s", booking)
            return booking
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error(
                "❌ TOOL ERROR: hold_flight_booking_tool failed after %.2fs - %s",
                elapsed, str(e),
            )
            raise

    async def get_flight_booking_status_tool(
        ctx: RunContext,
        booking_id: Annotated[str, "Booking ID returned from hold_flight_booking_tool"],
    ):
        """Check the status of a held flight booking."""
        agent.log.info(
            "🧾 TOOL CALL: get_flight_booking_status_tool(booking_id=%s)",
            booking_id,
        )
        try:
            await agent._ensure_travel()
            params = {"bookingId": booking_id}
            agent.log.debug(
                "Calling MCP tool: travel.get_flight_booking_status with params: %s",
                params,
            )
            result = await agent.travel_client.call_tool("travel.get_flight_booking_status", params)
            booking = parse_mcp_text_result(result, "booking") or {}
            agent.log.info(
                "✅ TOOL SUCCESS: get_flight_booking_status_tool - booking %s status=%s",
                booking.get("bookingId", booking_id),
                booking.get("status", "unknown"),
            )
            agent.log.debug("Booking status details: %s", booking)
            return booking
        except Exception as e:
            agent.log.error(
                "❌ TOOL ERROR: get_flight_booking_status_tool failed - %s",
                str(e),
            )
            raise

    async def search_hotels_tool(
        ctx: RunContext,
        city: Annotated[str, "City code (e.g., GOA, BOM, DEL, BLR)"],
        check_in: Annotated[str | None, "Check-in date YYYY-MM-DD"] = None,
        check_out: Annotated[str | None, "Check-out date YYYY-MM-DD"] = None,
        guests: Annotated[int | None, "Number of guests (default 1)"] = None,
        max_price_per_night: Annotated[float | None, "Optional max price per night in INR"] = None,
    ):
        """Search hotels in a city; optionally filter by dates and budget."""
        start_time = time.time()
        agent.log.info("🏨 TOOL CALL: search_hotels_tool(city=%s, check_in=%s, check_out=%s)", city, check_in, check_out)
        try:
            await agent._ensure_travel()
            params = {"city": city}
            if check_in:
                params["checkIn"] = check_in
            if check_out:
                params["checkOut"] = check_out
            if guests is not None:
                params["guests"] = guests
            if max_price_per_night is not None:
                params["maxPricePerNight"] = max_price_per_night
            result = await agent.travel_client.call_tool("travel.search_hotels", params)
            hotels = parse_mcp_text_result(result, "hotels") or []
            elapsed = time.time() - start_time
            agent.log.info("✅ TOOL SUCCESS: search_hotels_tool found %d hotels (took %.2fs)", len(hotels), elapsed)
            return {"hotels": hotels, "time_taken": elapsed}
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error("❌ TOOL ERROR: search_hotels_tool failed after %.2fs - %s", elapsed, str(e))
            raise

    async def get_hotel_tool(
        ctx: RunContext,
        hotel_id: Annotated[str, "Hotel ID from search_hotels_tool (e.g., HTL-001)"],
    ):
        """Get detailed information for a specific hotel."""
        agent.log.info("🏨 TOOL CALL: get_hotel_tool(hotel_id=%s)", hotel_id)
        try:
            await agent._ensure_travel()
            result = await agent.travel_client.call_tool("travel.get_hotel", {"hotelId": hotel_id})
            hotel = parse_mcp_text_result(result, "hotel") or {}
            agent.log.info("✅ TOOL SUCCESS: get_hotel_tool retrieved %s", hotel.get("name", hotel_id))
            return hotel
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: get_hotel_tool failed - %s", str(e))
            raise

    async def hold_hotel_booking_tool(
        ctx: RunContext,
        hotel_id: Annotated[str, "Hotel ID to book (from search_hotels_tool)"],
        guest_name: Annotated[str, "Guest full name"],
        contact_email: Annotated[str, "Guest contact email"],
        check_in: Annotated[str, "Check-in date YYYY-MM-DD"],
        check_out: Annotated[str, "Check-out date YYYY-MM-DD"],
        guests: Annotated[int | None, "Number of guests (default 1)"] = None,
    ):
        """Create a held booking for a selected hotel."""
        start_time = time.time()
        agent.log.info("🏨 TOOL CALL: hold_hotel_booking_tool(hotel_id=%s, guest=%s)", hotel_id, guest_name)
        try:
            await agent._ensure_travel()
            params = {
                "hotelId": hotel_id,
                "guestName": guest_name,
                "contactEmail": contact_email,
                "checkIn": check_in,
                "checkOut": check_out,
            }
            if guests is not None:
                params["guests"] = guests
            result = await agent.travel_client.call_tool("travel.hold_hotel_booking", params)
            booking = parse_mcp_text_result(result, "booking") or {}
            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: hold_hotel_booking_tool created %s (amount=₹%.2f, took %.2fs)",
                booking.get("hotelBookingId", "?"), booking.get("amount", 0), elapsed,
            )
            return booking
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error("❌ TOOL ERROR: hold_hotel_booking_tool failed after %.2fs - %s", elapsed, str(e))
            raise

    async def get_hotel_booking_status_tool(
        ctx: RunContext,
        hotel_booking_id: Annotated[str, "Hotel booking ID from hold_hotel_booking_tool"],
    ):
        """Check the status of a hotel booking."""
        agent.log.info("🏨 TOOL CALL: get_hotel_booking_status_tool(hotel_booking_id=%s)", hotel_booking_id)
        try:
            await agent._ensure_travel()
            result = await agent.travel_client.call_tool(
                "travel.get_hotel_booking_status", {"hotelBookingId": hotel_booking_id}
            )
            booking = parse_mcp_text_result(result, "booking") or {}
            agent.log.info("✅ TOOL SUCCESS: get_hotel_booking_status_tool - status=%s", booking.get("status", "?"))
            return booking
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: get_hotel_booking_status_tool failed - %s", str(e))
            raise

    return [
        search_flights_tool,
        get_flight_tool,
        hold_flight_booking_tool,
        get_flight_booking_status_tool,
        search_hotels_tool,
        get_hotel_tool,
        hold_hotel_booking_tool,
        get_hotel_booking_status_tool,
    ]
