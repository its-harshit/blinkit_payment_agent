"""Cab tools (same-city, Uber-like) for the unified agent. Uses Travel MCP client."""
import time
from typing import Annotated, Any

from pydantic_ai import RunContext

from ..core import parse_mcp_text_result


def make_cab_tools(agent: Any):
    """Return cab tool functions that close over the given agent."""
    assert agent is not None

    async def search_cabs_tool(
        ctx: RunContext,
        origin: Annotated[str, "Pickup place name or address (e.g., Connaught Place, IGI Airport)"],
        destination: Annotated[str, "Drop place name or address (e.g., IGI Airport, hotel address)"],
        city: Annotated[str, "City code for the ride (e.g., DEL, BOM, GOA, BLR). Required for same-city validation."],
    ):
        """Search cab options between two places within a city. Same-city only; always returns 2-3 options (Economy, Sedan, SUV)."""
        start_time = time.time()
        agent.log.info(
            "🚕 TOOL CALL: search_cabs_tool(origin=%s, destination=%s, city=%s)",
            origin, destination, city,
        )
        try:
            await agent._ensure_travel()
            params = {"origin": origin, "destination": destination, "city": city}
            agent.log.debug("Calling MCP tool: travel.search_cabs with params: %s", params)
            result = await agent.travel_client.call_tool("travel.search_cabs", params)
            data = parse_mcp_text_result(result)
            cabs = data.get("cabs", [])
            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: search_cabs_tool found %d cabs (took %.2fs)",
                len(cabs), elapsed,
            )
            if cabs:
                agent.log.debug("First cab: %s", cabs[0])
            return {"cabs": cabs, "time_taken": elapsed}
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error(
                "❌ TOOL ERROR: search_cabs_tool failed after %.2fs - %s",
                elapsed, str(e),
            )
            raise

    async def book_cab_tool(
        ctx: RunContext,
        cab_id: Annotated[str, "Cab ID from search_cabs_tool (e.g., CAB-DEL-100)"],
        passenger_name: Annotated[str, "Passenger full name"],
        contact: Annotated[str, "Passenger phone or email"],
        origin: Annotated[str | None, "Same pickup place as in search_cabs (so fare/ETA match)"] = None,
        destination: Annotated[str | None, "Same drop place as in search_cabs"] = None,
        city: Annotated[str | None, "Same city as in search_cabs"] = None,
    ):
        """Book a selected cab. Pass origin, destination, city from the search result so fare and ETA match the options shown."""
        start_time = time.time()
        agent.log.info(
            "🚕 TOOL CALL: book_cab_tool(cab_id=%s, passenger_name=%s)",
            cab_id, passenger_name,
        )
        try:
            await agent._ensure_travel()
            params = {"cabId": cab_id, "passengerName": passenger_name, "contact": contact}
            if origin is not None:
                params["origin"] = origin
            if destination is not None:
                params["destination"] = destination
            if city is not None:
                params["city"] = city
            agent.log.debug("Calling MCP tool: travel.book_cab with params: %s", params)
            result = await agent.travel_client.call_tool("travel.book_cab", params)
            booking = parse_mcp_text_result(result, "booking") or parse_mcp_text_result(result)
            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: book_cab_tool created booking %s (fare=₹%.0f, took %.2fs)",
                booking.get("cabBookingId", "?"), booking.get("fare", 0), elapsed,
            )
            agent.log.debug("Booking details: %s", booking)
            return booking
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error(
                "❌ TOOL ERROR: book_cab_tool failed after %.2fs - %s",
                elapsed, str(e),
            )
            raise

    async def get_cab_booking_status_tool(
        ctx: RunContext,
        cab_booking_id: Annotated[str, "Cab booking ID from book_cab_tool (e.g., CB-XXXXXXXX)"],
    ):
        """Check the status of a cab booking."""
        agent.log.info(
            "🚕 TOOL CALL: get_cab_booking_status_tool(cab_booking_id=%s)",
            cab_booking_id,
        )
        try:
            await agent._ensure_travel()
            params = {"cabBookingId": cab_booking_id}
            agent.log.debug("Calling MCP tool: travel.get_cab_booking_status with params: %s", params)
            result = await agent.travel_client.call_tool("travel.get_cab_booking_status", params)
            booking = parse_mcp_text_result(result, "booking") or parse_mcp_text_result(result)
            agent.log.info(
                "✅ TOOL SUCCESS: get_cab_booking_status_tool - status=%s",
                booking.get("status", "?"),
            )
            agent.log.debug("Booking status: %s", booking)
            return booking
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: get_cab_booking_status_tool failed - %s", str(e))
            raise

    return [
        search_cabs_tool,
        book_cab_tool,
        get_cab_booking_status_tool,
    ]
