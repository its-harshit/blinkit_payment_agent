"""Recipe-to-cart agent that plans a dish and orders ingredients via MCP."""
import asyncio
import json
import re
import uuid
import logging
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

try:
    from .core import McpClient
except ImportError:
    from backend.core import McpClient


class Ingredient(BaseModel):
    name: str = Field(description="Ingredient name")
    quantity: str = Field(description="Human-friendly quantity, e.g., '2 cups'")
    optional: bool = Field(default=False, description="Whether the ingredient can be skipped")


class RecipePlan(BaseModel):
    dish: str = Field(description="Dish name")
    ingredients: list[Ingredient] = Field(description="Ingredients required for the dish")
    steps: list[str] = Field(description="Ordered cooking steps")


MCP_TOOLS_DIR = Path(__file__).parent
SERVERS_DIR = MCP_TOOLS_DIR / "servers"
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]

DEFAULT_MODEL = OpenAIChatModel(
    model_name="npci",
    provider=OpenAIProvider(base_url="http://183.82.7.228:9535/v1", api_key="dummy"),
)


class RecipeAgent:
    def __init__(self, model=DEFAULT_MODEL):
        """Agent that plans a recipe then procures ingredients using MCP tools."""
        self.log = logging.getLogger("recipe_agent")
        if not self.log.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            self.log.addHandler(handler)
        self.log.setLevel(logging.INFO)
        instructions = (
            "You are a concise home-cooking planner. "
            "Return a short ingredient list with sensible quantities (Indian kitchen units when natural) "
    "and a clear ordered list of cooking steps. "
    "Prefer ingredients commonly available in raw form on Blinkit (Indian supermarket staples). Avoid exotic or hard-to-find items or ultra processes things which might be hard to exactly find; suggest nearest simple substitutes."
        )
        self.recipe_planner = Agent(
            model=model,
            output_type=RecipePlan,
            instructions=instructions,
        )
        self.blinkit_client: McpClient | None = None
        self.payment_client: McpClient | None = None
        # simple alias list to increase hit-rate against the sample Blinkit catalog
        self.search_aliases = {
            "chicken (bone-in pieces)": ["chicken", "chicken curry cut", "chicken bone-in"],
            "chicken": ["chicken", "chicken curry cut", "chicken bone-in"],
            "chicken pieces": ["chicken", "chicken curry cut", "chicken bone-in"],
            "onions": ["onion"],
            "onion": ["onion"],
            "tomatoes": ["tomato"],
            "tomato": ["tomato"],
            "ginger-garlic paste": ["ginger garlic paste", "ginger garlic", "ginger paste"],
            "green chilies": ["green chili", "green chilli", "green chillies", "chili", "chilli"],
            "green chili": ["green chili", "green chilli", "green chillies", "chili", "chilli"],
            "green chilli": ["green chili", "green chilli", "green chillies", "chili", "chilli"],
            "cooking oil": ["sunflower oil", "refined oil", "mustard oil", "ghee", "desi ghee", "oil"],
            "cooking oil or ghee": ["sunflower oil", "refined oil", "mustard oil", "ghee", "desi ghee", "oil"],
            "whole spices": ["garam masala", "biryani masala"],
            "whole spices (cloves, cinnamon, cardamom, bay leaf)": ["whole spices", "whole spices mix", "bay leaf", "cloves", "cinnamon", "cardamom"],
            "fresh coriander leaves": ["coriander leaves", "coriander", "dhania"],
            "coriander leaves": ["fresh coriander", "coriander", "dhania"],
            "fresh mint leaves": ["mint leaves", "mint", "pudina"],
            "mint leaves": ["fresh mint", "mint", "pudina"],
            "lemon juice": ["lemon", "lime"],
            "salt": ["salt", "iodized salt"],
            "chicken (cut into pieces)": ["chicken", "chicken curry cut", "chicken bone-in", "chicken pieces", "bone in pieces"],
            "chicken (bone-in pieces)": ["chicken", "chicken curry cut", "chicken bone-in", "chicken pieces", "bone in pieces"],
        }

    async def _ensure_blinkit(self):
        if self.blinkit_client is None:
            self.log.info("Starting Blinkit MCP server client")
            self.blinkit_client = McpClient("blinkit-recipe-agent", BLINKIT_CMD, cwd=str(SERVERS_DIR))
            await self.blinkit_client.initialize()

    async def _ensure_payment(self):
        if self.payment_client is None:
            self.log.info("Starting Payment MCP server client")
            self.payment_client = McpClient("payment-recipe-agent", PAYMENT_CMD, cwd=str(SERVERS_DIR))
            await self.payment_client.initialize()

    async def plan_recipe(self, dish: str) -> RecipePlan:
        self.log.info("Planning recipe for: %s", dish)
        result = await self.recipe_planner.run(dish)
        self.log.info("Recipe planned; received %d ingredients and %d steps", len(result.output.ingredients), len(result.output.steps))
        return result.output

    async def _pick_and_add(self, ingredient: Ingredient, limit: int = 3) -> dict | None:
        """Search Blinkit and add the first hit to cart."""
        await self._ensure_blinkit()
        queries = [ingredient.name]
        key = ingredient.name.lower().strip()
        if key in self.search_aliases:
            queries.extend(self.search_aliases[key])

        items = []
        tried = []
        for q in queries:
            self.log.info("Searching Blinkit for: %s", q)
            tried.append(q)
            resp = await self.blinkit_client.call_tool("blinkit.search", {"query": q, "limit": limit})
            found = json.loads(resp["content"][0]["text"])
            if found:
                items = found
                break

        if not items:
            self.log.warning("No results for ingredient after tries %s", tried)
            return None

        choice = items[0]
        qty_raw = self._quantity_to_int(ingredient.quantity)
        qty = max(1, qty_raw)
        # clamp to stock and sensible upper bound to avoid server errors/timeouts
        stock = choice.get("stock", qty)
        qty = min(qty, stock, 5)
        if qty != qty_raw:
            self.log.info("Clamped quantity for %s from %s to %s (stock=%s)", ingredient.name, qty_raw, qty, stock)

        self.log.info("Adding to cart: %s x%d (%s)", choice.get("name"), qty, choice.get("id"))
        added = await self.blinkit_client.call_tool(
            "blinkit.add_to_cart", {"id": choice["id"], "quantity": qty}
        )
        entry = json.loads(added["content"][0]["text"])
        return {
            "ingredient": ingredient.name,
            "picked": choice["name"],
            "quantity": max(1, qty),
            "unit_price": choice.get("price"),
            "line_total": choice.get("price", 0) * max(1, qty),
        }

    @staticmethod
    def _quantity_to_int(quantity: str) -> int:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", quantity)
        if not match:
            return 1
        try:
            value = float(match.group(1))
            return max(1, round(value))
        except ValueError:
            return 1

    async def build_cart_for_plan(self, plan: RecipePlan) -> dict:
        """Attempt to add each ingredient to the Blinkit cart."""
        added_items = []
        skipped = []
        for ingredient in plan.ingredients:
            picked = await self._pick_and_add(ingredient)
            if picked:
                added_items.append(picked)
            else:
                skipped.append(ingredient.name)

        cart_summary = None
        if self.blinkit_client:
            self.log.info("Fetching cart summary")
            cart = await self.blinkit_client.call_tool("blinkit.cart", {})
            cart_summary = json.loads(cart["content"][0]["text"])

        return {"added": added_items, "skipped": skipped, "cart": cart_summary}

    async def checkout(self, amount: float) -> dict:
        """Create payment intent and poll final status."""
        self.log.info("Initiating payment for ₹%s", amount)
        await self._ensure_payment()
        order_id = f"ord_{uuid.uuid4().hex[:8]}"
        init_resp = await self.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
        intent = json.loads(init_resp["content"][0]["text"])

        self.log.info("Checking payment status for %s", intent["paymentId"])
        status_resp = await self.payment_client.call_tool("payment.status", {"paymentId": intent["paymentId"]})
        status = json.loads(status_resp["content"][0]["text"])
        return {"orderId": order_id, "intent": intent, "status": status}

    async def close(self):
        if self.blinkit_client:
            self.blinkit_client.close()
        if self.payment_client:
            self.payment_client.close()


async def main():
    dish = input("What dish do you want to cook? ").strip()
    if not dish:
        print("No dish provided. Exiting.")
        return

    agent = RecipeAgent()
    try:
        plan = await agent.plan_recipe(dish)

        print(f"\nDish: {plan.dish}")
        print("\nIngredients:")
        for ing in plan.ingredients:
            opt = " (optional)" if ing.optional else ""
            print(f"- {ing.quantity} {ing.name}{opt}")

        print("\nSteps:")
        for idx, step in enumerate(plan.steps, start=1):
            print(f"{idx}. {step}")

        consent = input("\nShould I order these on Blinkit? (y/N): ").strip().lower()
        if consent != "y":
            print("Okay, not ordering. Happy cooking!")
            return
        
        print(f"\n\n\nPlan: {plan}\n\n\n")
        
        print("\nBuilding cart on Blinkit...")
        cart_result = await agent.build_cart_for_plan(plan)
        if cart_result["skipped"]:
            print("Could not find:", ", ".join(cart_result["skipped"]))

        cart = cart_result.get("cart") or {}
        print("Cart items:", cart.get("items", []))
        print("Cart total: ₹", cart.get("total", 0))

        pay_consent = input("Proceed to UPI payment? (y/N): ").strip().lower()
        if pay_consent != "y":
            print("Cart ready but payment skipped.")
            return

        print("\nCreating payment intent...")
        payment = await agent.checkout(cart.get("total", 0))
        print("Payment intent:", payment["intent"])
        print("Payment status:", payment["status"])
        print("All set. 🎉")
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
