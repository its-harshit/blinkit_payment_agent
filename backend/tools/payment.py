"""Payment tools (create_payment, check_payment_status) for the unified agent."""
import uuid
from typing import Annotated, Any

from pydantic_ai import RunContext

from ..core import parse_mcp_text_result


def make_payment_tools(agent: Any):
    """Return payment tool functions that close over the given agent."""
    assert agent is not None

    async def create_payment(
        ctx: RunContext,
        amount: Annotated[float, "Amount in INR"],
        order_id: Annotated[str | None, "Optional Order ID (auto-generated if not provided)"] = None,
    ):
        """Create payment intent. Order ID is auto-generated if not provided."""
        if not order_id:
            order_id = f"ord_{uuid.uuid4().hex[:8]}"
        agent.log.info("💳 TOOL CALL: create_payment(order_id=%s, amount=₹%.2f)", order_id, amount)
        try:
            await agent._ensure_payment()
            agent.log.debug("Calling MCP tool: payment.init with params: %s", {"orderId": order_id, "amount": amount})
            result = await agent.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
            intent = parse_mcp_text_result(result)
            agent.log.info("✅ TOOL SUCCESS: create_payment - Payment ID: %s, Status: %s", intent.get("paymentId"), intent.get("status"))
            return intent
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: create_payment failed - %s", str(e))
            raise

    async def check_payment_status(ctx: RunContext, payment_id: Annotated[str, "Payment ID"]):
        agent.log.info("💳 TOOL CALL: check_payment_status(payment_id=%s)", payment_id)
        try:
            await agent._ensure_payment()
            result = await agent.payment_client.call_tool("payment.status", {"paymentId": payment_id})
            status = parse_mcp_text_result(result)
            payment_status = status.get("status", "unknown")
            agent.log.info("✅ TOOL SUCCESS: check_payment_status - Status: %s", payment_status)
            if status.get("txnId"):
                agent.log.info("   Transaction ID: %s", status.get("txnId"))
            payment_status_lower = payment_status.lower()
            has_txn_id = bool(status.get("txnId") or status.get("txn_id"))
            is_successful = (
                payment_status_lower in ["success", "successful", "succeeded", "completed", "paid", "settled", "done", "processed"]
                or has_txn_id
            )
            if is_successful:
                agent.log.info("💳 Payment successful! Clearing cart...")
                try:
                    await agent._ensure_blinkit()
                    clear_result = await agent.blinkit_client.call_tool("blinkit.clear_cart", {})
                    cleared = parse_mcp_text_result(clear_result)
                    status["cart_cleared"] = True
                    status["items_removed"] = cleared.get("itemsRemoved", 0)
                except Exception as clear_err:
                    agent.log.error("❌ Failed to clear cart after payment: %s", str(clear_err))
                    status["cart_cleared"] = False
                    status["clear_error"] = str(clear_err)
            return status
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: check_payment_status failed - %s", str(e))
            raise

    return [create_payment, check_payment_status]
