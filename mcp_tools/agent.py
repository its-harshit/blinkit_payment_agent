"""AI Agent using pydantic-ai for agentic commerce with Blinkit and Payment MCP servers."""
import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field
from pydantic_ai import Agent

try:
    from .mcp_client import McpClient
except ImportError:
    from mcp_client import McpClient


# Tool result models
class SearchResult(BaseModel):
    """Result from Blinkit search."""
    items: list[dict] = Field(description="List of matching items")
    count: int = Field(description="Number of items found")


class ItemResult(BaseModel):
    """Result from getting a single item."""
    item: dict = Field(description="Item details")


class CartItem(BaseModel):
    """Item added to cart."""
    id: str = Field(description="Item ID")
    name: str = Field(description="Item name")
    quantity: int = Field(description="Quantity added")
    unit_price: float = Field(description="Unit price")
    line_total: float = Field(description="Line total")


class CartSummary(BaseModel):
    """Cart summary."""
    items: list[dict] = Field(description="Cart items")
    total: float = Field(description="Total amount in INR")


class PaymentIntent(BaseModel):
    """Payment intent created."""
    payment_id: str = Field(description="Payment ID")
    order_id: str = Field(description="Order ID")
    amount: float = Field(description="Amount in INR")
    total: float = Field(description="Total including fees")
    merchant_vpa: str = Field(description="Merchant UPI VPA")
    status: str = Field(description="Payment status")


class PaymentStatus(BaseModel):
    """Payment status."""
    payment_id: str = Field(description="Payment ID")
    status: str = Field(description="Payment status")
    txn_id: str | None = Field(default=None, description="Transaction ID if succeeded")


# Initialize MCP clients
MCP_TOOLS_DIR = Path(__file__).parent
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]


class CommerceAgent:
    """AI Agent for agentic commerce using Blinkit and Payment MCP servers."""

    def __init__(self, model: str = "openai:gpt-4o-mini"):
        """Initialize the commerce agent.
        
        Args:
            model: Model to use (e.g., "openai:gpt-4o-mini" or "anthropic:claude-3-5-sonnet-20241022")
        """
        self.blinkit_client: McpClient | None = None
        self.payment_client: McpClient | None = None
        self.agent = Agent(
            model,
            system_prompt="""You are a helpful shopping assistant for Blinkit, an Indian grocery delivery service.
You can help users:
1. Search for products in the Blinkit catalog
2. View product details
3. Add items to cart
4. View cart summary
5. Process payments via UPI

Always be helpful, clear, and confirm actions before proceeding with payments.
When showing prices, use ₹ symbol for Indian Rupees.""",
        )
        # Register tools once
        self.agent.tool(self.search_products)
        self.agent.tool(self.get_product)
        self.agent.tool(self.add_to_cart)
        self.agent.tool(self.view_cart)
        self.agent.tool(self.create_payment)
        self.agent.tool(self.check_payment_status)

    async def _ensure_blinkit(self):
        """Ensure Blinkit client is initialized."""
        if self.blinkit_client is None:
            self.blinkit_client = McpClient("blinkit-agent", BLINKIT_CMD, cwd=str(MCP_TOOLS_DIR))
            await self.blinkit_client.initialize()

    async def _ensure_payment(self):
        """Ensure Payment client is initialized."""
        if self.payment_client is None:
            self.payment_client = McpClient("payment-agent", PAYMENT_CMD, cwd=str(MCP_TOOLS_DIR))
            await self.payment_client.initialize()

    async def search_products(
        self, query: Annotated[str, "Search query (product name or category)"], limit: Annotated[int, "Maximum results"] = 5
    ) -> SearchResult:
        """Search for products in Blinkit catalog."""
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.search", {"query": query, "limit": limit})
        items = json.loads(result["content"][0]["text"])
        return SearchResult(items=items, count=len(items))

    async def get_product(
        self, item_id: Annotated[str, "Product ID (e.g., blk-001)"]
    ) -> ItemResult:
        """Get details of a specific product."""
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.item", {"id": item_id})
        item = json.loads(result["content"][0]["text"])
        return ItemResult(item=item)

    async def add_to_cart(
        self, item_id: Annotated[str, "Product ID"], quantity: Annotated[int, "Quantity to add (minimum 1)"]
    ) -> CartItem:
        """Add a product to the shopping cart."""
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.add_to_cart", {"id": item_id, "quantity": quantity})
        entry = json.loads(result["content"][0]["text"])
        return CartItem(
            id=entry["item"]["id"],
            name=entry["item"]["name"],
            quantity=entry["quantity"],
            unit_price=entry["item"]["price"],
            line_total=entry["item"]["price"] * entry["quantity"]
        )

    async def view_cart(self) -> CartSummary:
        """View the current shopping cart."""
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.cart", {})
        cart = json.loads(result["content"][0]["text"])
        return CartSummary(items=cart["items"], total=cart["total"])

    async def create_payment(
        self, order_id: Annotated[str, "Order ID"], amount: Annotated[float, "Amount in INR"]
    ) -> PaymentIntent:
        """Create a payment intent for an order."""
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
        intent = json.loads(result["content"][0]["text"])
        return PaymentIntent(
            payment_id=intent["paymentId"],
            order_id=intent["orderId"],
            amount=intent["amount"],
            total=intent["total"],
            merchant_vpa=intent["merchantVpa"],
            status=intent["status"]
        )

    async def check_payment_status(
        self, payment_id: Annotated[str, "Payment ID"]
    ) -> PaymentStatus:
        """Check the status of a payment."""
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.status", {"paymentId": payment_id})
        status = json.loads(result["content"][0]["text"])
        return PaymentStatus(
            payment_id=status["paymentId"],
            status=status["status"],
            txn_id=status.get("txnId")
        )

    async def run(self, user_message: str) -> str:
        """Run the agent with a user message."""
        result = await self.agent.run(user_message)
        return result.data

    async def close(self):
        """Close all MCP clients."""
        if self.blinkit_client:
            self.blinkit_client.close()
        if self.payment_client:
            self.payment_client.close()


async def main():
    """Example usage of the commerce agent."""
    import os
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Please set OPENAI_API_KEY environment variable")
        print("   You can also use other models like 'anthropic:claude-3-5-sonnet-20241022'")
        return

    agent = CommerceAgent(model="openai:gpt-4o-mini")
    
    try:
        print("🤖 Commerce Agent ready! Type your requests (or 'exit' to quit)\n")
        
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ["exit", "quit"]:
                break
            
            if not user_input:
                continue
            
            print("\n🤖 Agent: ", end="", flush=True)
            response = await agent.run(user_input)
            print(response)
            print()
    
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())

