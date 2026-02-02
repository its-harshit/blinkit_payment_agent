"""Hybrid NPCI info + commerce agent that only calls tools for shopping/payment."""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import ToolRetryError
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic import BaseModel, Field, model_validator

try:
    from .core import McpClient, parse_mcp_text_result as _parse_mcp_text_result
except ImportError:
    from backend.core import McpClient, parse_mcp_text_result as _parse_mcp_text_result


MCP_TOOLS_DIR = Path(__file__).parent
SERVERS_DIR = MCP_TOOLS_DIR / "servers"
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]
TRAVEL_CMD = ["node", "travel-server.js"]

DEFAULT_MODEL = OpenAIChatModel(
    model_name="/model",
    provider=OpenAIProvider(base_url="http://183.82.7.228:9532/v1", api_key="dummy"),
)


class UnifiedAgent:
    """Answers NPCI grievance FAQs by default, but uses MCP tools for shopping/checkout."""

    def __init__(self, model=DEFAULT_MODEL, log_level=logging.INFO):
        self.log = logging.getLogger("unified_agent")
        if not self.log.handlers:
            handler = logging.StreamHandler()
            # Format: [LEVEL] timestamp - message
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s", datefmt="%H:%M:%S"))
            self.log.addHandler(handler)
        self.log.setLevel(log_level)

        from .instructions import get_full_instructions
        instructions = get_full_instructions()

        self.blinkit_client: McpClient | None = None
        self.payment_client: McpClient | None = None
        self.travel_client: McpClient | None = None
        self.conversation_history: list[tuple[str, str]] = []  # Store (user_msg, assistant_msg) pairs
        self.max_history_exchanges = 3  # When no summary: keep last 3-4 exchanges in context
        self.max_history_for_summariser = 12  # Keep up to 12 exchanges so we can run summariser every 3
        self.conversation_summary: str = ""  # Updated every 3 turns by summariser; passed to main LLM when set

        # Summariser agent: multi-domain (travel, shopping, NPCI, etc.), incremental merge
        SUMMARISER_SYSTEM = (
            "You are a conversation summariser for a support agent that handles **travel** (flights, hotels, cabs), "
            "**shopping** (Blinkit, recipe ingredients, cart), **NPCI/UPI** (grievances, txn details), and **payments**. "
            "Your goal is to extract the important and concrete details/facts from the conversation that need to be remembered for the context and output a summary that the main LLM can refer to for info. "
            "You will receive either (A) a conversation excerpt only, or (B) a previous summary and new set of conversation turns. "
            "If (A), extract the details from the convo and output a structured summary. "
            "If (B), merge the previous summary with the new details from the turns; output an updated summary. "
            "Include whatever is relevant to the context: **Travel** – trip type, guests, duration_days, start_date (YYYY-MM-DD), origin/destination city, "
            "what's booked (flight/hotel/cab + IDs), what's pending, for next step (e.g. for hotel: check_in, check_out, guests, city). "
            "**Shopping** – recipe/dish, ingredients or cart state, checkout intent. "
            "**NPCI/UPI** – txn ID, VPA, bank, issue. **Other** – names, contact, preferences. "
            "Keep key-value or short bullet style; use section labels (Travel:, Shopping:, etc.) when multiple domains appear; "
            "overwrite or add as new info appears; do not duplicate."
        )
        self._summariser_agent = Agent(model=model, instructions=SUMMARISER_SYSTEM)
        # lightweight planner for ingredient extraction
        class IngredientItem(BaseModel):
            name: str = Field(description="Ingredient name")
            quantity: str | None = Field(default=None, description="Human-friendly quantity, e.g., '2 cups'")
            optional: bool = Field(default=False, description="Whether the ingredient can be skipped")
        self.IngredientItem = IngredientItem
        
        # Create a wrapper model that accepts both list and dict formats
        class IngredientListResponse(BaseModel):
            """Wrapper that accepts both list format and dict format with 'ingredients' key."""
            ingredients: list[IngredientItem] = Field(default_factory=list)
            
            @model_validator(mode='before')
            @classmethod
            def handle_multiple_formats(cls, data):
                """Handle multiple LLM output formats and extract ingredients."""
                if isinstance(data, list):
                    # Direct list format - wrap it
                    return {'ingredients': data}
                elif isinstance(data, dict):
                    # Check various possible wrapper formats the LLM might use
                    
                    # Format 1: Direct {'ingredients': [...]}
                    if 'ingredients' in data and isinstance(data['ingredients'], list):
                        return data
                    
                    # Format 2: {'response': {'ingredients': [...]}}
                    if 'response' in data and isinstance(data.get('response'), dict):
                        resp = data['response']
                        if 'ingredients' in resp and isinstance(resp['ingredients'], list):
                            return resp
                    
                    # Format 3: {'name': 'final_result', 'parameters': {'ingredients': [...]}}
                    # This is a tool-call style response
                    if 'parameters' in data and isinstance(data.get('parameters'), dict):
                        params = data['parameters']
                        if 'ingredients' in params and isinstance(params['ingredients'], list):
                            return params
                    
                    # Format 4: {'result': {'ingredients': [...]}} or similar
                    for key in ['result', 'data', 'output']:
                        if key in data and isinstance(data.get(key), dict):
                            inner = data[key]
                            if 'ingredients' in inner and isinstance(inner['ingredients'], list):
                                return inner
                    
                    # Format 5: Dict with a list value that looks like ingredients
                    for key, value in data.items():
                        if isinstance(value, list) and len(value) > 0:
                            # Check if it looks like a list of ingredient dicts
                            if all(isinstance(item, dict) and 'name' in item for item in value):
                                return {'ingredients': value}
                    
                    # No valid ingredients found
                    return {'ingredients': []}
                else:
                    # Unknown format
                    return {'ingredients': []}
        
        # Use wrapper model that accepts both formats
        self.plan_agent = Agent(
            model=model,
            output_type=IngredientListResponse,  # type: ignore[arg-type]
            instructions=(
                "You are a recipe ingredient planner. Plan ALL essential ingredients for the given dish.\n"
                "\n"
                "**CRITICAL RULES:**\n"
                "- Do NOT extract words from input. PLAN the complete ingredient list.\n"
                "- Use simple, common names (e.g., 'onion', not 'yellow onion' or 'red onion').\n"
                "- Return 6-7 essential ingredients maximum.\n"
                "- ONLY return the JSON object in the exact format shown below. No extra text or wrapping.\n"
                "\n"
                "**REQUIRED OUTPUT FORMAT:**\n"
                "Return a JSON object with an 'ingredients' key containing an array:\n"
                "```json\n"
                "{\"ingredients\": [\n"
                "  {\"name\": \"ingredient1\", \"quantity\": \"amount\", \"optional\": false},\n"
                "  {\"name\": \"ingredient2\", \"quantity\": \"amount\", \"optional\": false}\n"
                "]}\n"
                "```\n"
                "\n"
                "Each ingredient object must have:\n"
                "- name: string (simple ingredient name)\n"
                "- quantity: string or null (e.g., '2 cups', '1 kg', or null)\n"
                "- optional: boolean (true only if can be skipped)\n"
                "\n"
                "**CORRECT EXAMPLE:**\n"
                "Input: 'egg biryani'\n"
                "Output:\n"
                "{\"ingredients\": [\n"
                "  {\"name\": \"basmati rice\", \"quantity\": \"1 cup\", \"optional\": false},\n"
                "  {\"name\": \"eggs\", \"quantity\": \"6 pieces\", \"optional\": false},\n"
                "  {\"name\": \"onion\", \"quantity\": \"2 medium\", \"optional\": false},\n"
                "  {\"name\": \"tomato\", \"quantity\": \"2 medium\", \"optional\": false},\n"
                "  {\"name\": \"ginger-garlic paste\", \"quantity\": \"1 tbsp\", \"optional\": false},\n"
                "  {\"name\": \"biryani masala\", \"quantity\": \"1 tbsp\", \"optional\": false},\n"
                "  {\"name\": \"ghee\", \"quantity\": \"2 tbsp\", \"optional\": false}\n"
                "]}\n"
                "\n"
                "**WRONG FORMATS (NEVER USE THESE):**\n"
                "- [...] ← Raw array without wrapper\n"
                "- {\"name\": \"final_result\", \"parameters\": {...}} ← Tool call format\n"
                "- {\"response\": {...}} ← Extra wrapper\n"
                "- Any text before or after the JSON\n"
            ),
        )
        # alias map to improve match rate
        self.search_aliases = {
            "chicken (bone-in pieces)": ["chicken", "chicken curry cut", "chicken bone-in", "chicken pieces", "bone in pieces"],
            "chicken": ["chicken", "chicken curry cut", "chicken bone-in", "chicken pieces"],
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
            "ghee or oil": ["ghee", "desi ghee", "sunflower oil", "refined oil", "mustard oil", "oil"],
            "whole spices": ["whole spices mix", "biryani masala", "garam masala", "bay leaf", "cloves", "cinnamon", "cardamom"],
            "fresh coriander leaves": ["coriander leaves", "coriander", "dhania"],
            "coriander leaves": ["coriander leaves", "coriander", "dhania"],
            "fresh mint leaves": ["mint leaves", "mint", "pudina"],
            "mint leaves": ["mint leaves", "mint", "pudina"],
            "lemon juice": ["lemon", "lime"],
            "salt": ["salt", "iodized salt"],
        }

        self.agent = Agent(model=model, instructions=instructions)
        # Register tools from modules
        from .tools import make_shopping_tools, make_payment_tools, make_travel_tools, make_cab_tools
        for tool in make_shopping_tools(self):
            self.agent.tool(tool)
        for tool in make_payment_tools(self):
            self.agent.tool(tool)
        for tool in make_travel_tools(self):
            self.agent.tool(tool)
        for tool in make_cab_tools(self):
            self.agent.tool(tool)

    async def _ensure_blinkit(self):
        if self.blinkit_client is None:
            self.log.info("🔌 Initializing Blinkit MCP client...")
            try:
                self.blinkit_client = McpClient("blinkit-unified", BLINKIT_CMD, cwd=str(SERVERS_DIR), timeout=5.0)
                await self.blinkit_client.initialize()
                self.log.info("✅ Blinkit MCP client initialized successfully")
            except Exception as e:
                self.log.error("❌ Failed to initialize Blinkit MCP client: %s", str(e))
                raise

    async def _ensure_payment(self):
        if self.payment_client is None:
            self.log.info("🔌 Initializing Payment MCP client...")
            try:
                self.payment_client = McpClient("payment-unified", PAYMENT_CMD, cwd=str(SERVERS_DIR), timeout=30.0)
                await self.payment_client.initialize()
                self.log.info("✅ Payment MCP client initialized successfully")
            except Exception as e:
                self.log.error("❌ Failed to initialize Payment MCP client: %s", str(e))
                raise

    async def _ensure_travel(self):
        if self.travel_client is None:
            self.log.info("🔌 Initializing Travel MCP client...")
            try:
                self.travel_client = McpClient("travel-unified", TRAVEL_CMD, cwd=str(SERVERS_DIR), timeout=30.0)
                await self.travel_client.initialize()
                self.log.info("✅ Travel MCP client initialized successfully")
            except Exception as e:
                self.log.error("❌ Failed to initialize Travel MCP client: %s", str(e))
                raise

    def _format_exchanges(self, exchanges: list[tuple[str, str]]) -> str:
        """Format conversation exchanges as plain text for the summariser."""
        lines = []
        for i, (user_msg, assistant_msg) in enumerate(exchanges, 1):
            lines.append(f"User: {user_msg}")
            lines.append(f"Assistant: {assistant_msg}")
        return "\n\n".join(lines)

    async def _run_summariser(self) -> str:
        """Run the summariser on last 3 exchanges; merge with previous summary if present. Returns new summary."""
        if len(self.conversation_history) < 3:
            return self.conversation_summary
        last_three = self.conversation_history[-3:]
        new_turns_text = self._format_exchanges(last_three)
        if not self.conversation_summary.strip():
            # First run: summarise the 3 exchanges only
            prompt = f"Summarise this conversation. Extract concrete details (travel, shopping, NPCI, other as relevant).\n\n{new_turns_text}"
        else:
            # Incremental: merge previous summary with new turns
            prompt = (
                "Merge the previous summary below with the new conversation turns.\n"
                f"**Previous summary:**\n{self.conversation_summary}\n\n**New conversation turns:**\n{new_turns_text}"
            )
        try:
            result = await self._summariser_agent.run(prompt)
            print("\n\nresult: ", result)
            summary = getattr(result, "output", getattr(result, "data", str(result)))
            if summary and isinstance(summary, str):
                self.log.info("📋 Summariser updated (length=%d chars)", len(summary))
                return summary.strip()
        except Exception as e:
            self.log.warning("⚠️ Summariser failed: %s – keeping previous summary", str(e))
        return self.conversation_summary

    # === MCP tool wrappers ===
    async def search_products(self, query: Annotated[str, "Product name or category"], limit: Annotated[int, "Max results"] = 5):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.search", {"query": query, "limit": limit})
        return _parse_mcp_text_result(result)

    async def get_product(self, item_id: Annotated[str, "Product ID (e.g., blk-001)"]):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.item", {"id": item_id})
        return _parse_mcp_text_result(result)

    async def add_to_cart(self, item_id: Annotated[str, "Product ID"], quantity: Annotated[int, "Quantity (min 1)"] = 1):
        await self._ensure_blinkit()
        qty = max(1, quantity)
        result = await self.blinkit_client.call_tool("blinkit.add_to_cart", {"id": item_id, "quantity": qty})
        return _parse_mcp_text_result(result)

    async def view_cart(self):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.cart", {})
        return _parse_mcp_text_result(result)

    async def create_payment(self, order_id: Annotated[str, "Order ID"], amount: Annotated[float, "Amount in INR"]):
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
        return _parse_mcp_text_result(result)

    async def check_payment_status(self, payment_id: Annotated[str, "Payment ID"]):
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.status", {"paymentId": payment_id})
        return _parse_mcp_text_result(result)

    @staticmethod
    def _quantity_to_int(quantity: str | None) -> int:
        if not quantity:
            return 1
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", quantity)
        if not match:
            return 1
        try:
            value = float(match.group(1))
            return max(1, round(value))
        except ValueError:
            return 1

    async def _pick_and_add(self, ingredient: Any, limit: int = 3) -> dict | None:
        """Search supermarket and add the first hit to cart."""
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
            found = _parse_mcp_text_result(resp)
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
        entry = _parse_mcp_text_result(added)
        return {
            "ingredient": ingredient.name,
            "picked": choice["name"],
            "quantity": max(1, qty),
            "unit_price": choice.get("price"),
            "line_total": choice.get("price", 0) * max(1, qty),
        }

    async def build_cart_for_plan(self, ingredients: list) -> dict:
        """Attempt to add each ingredient to the supermarket cart."""
        added_items = []
        skipped = []
        for ingredient in ingredients:
            picked = await self._pick_and_add(ingredient)
            if picked:
                added_items.append(picked)
            else:
                skipped.append(ingredient.name)

        cart_summary = None
        if self.blinkit_client:
            self.log.info("Fetching cart summary")
            cart = await self.blinkit_client.call_tool("blinkit.cart", {})
            cart_summary = _parse_mcp_text_result(cart)

        return {"added": added_items, "skipped": skipped, "cart": cart_summary}


    async def plan_recipe_ingredients(self, text: str) -> dict:
        """Plan ingredients for a recipe and return the plan (without adding to cart).
        
        This is step 1 of the recipe shopping flow - just planning, no cart operations.
        """
        import time
        plan_start_time = time.time()
        self.log.info("📝 Planning recipe ingredients from text...")
        self.log.debug("Input text: %s", text[:200] + "..." if len(text) > 200 else text)
        
        try:
            plan_result = await self.plan_agent.run(text)
            raw_output = getattr(plan_result, "output", plan_result.output)
            plan_time = time.time() - plan_start_time
            
            # Extract ingredients from IngredientListResponse wrapper
            ingredients: list[self.IngredientItem] = []
            
            # The output should now be an IngredientListResponse object
            if hasattr(raw_output, 'ingredients'):
                # It's the wrapper model - extract the ingredients list
                ingredients = raw_output.ingredients
                self.log.debug("✅ Extracted ingredients from IngredientListResponse wrapper")
            elif isinstance(raw_output, list):
                # Direct list format (fallback - shouldn't happen with new wrapper)
                self.log.debug("✅ Received direct list format")
                ingredients = []
                for item in raw_output:
                    if isinstance(item, self.IngredientItem):
                        ingredients.append(item)
                    elif isinstance(item, dict):
                        try:
                            ingredients.append(self.IngredientItem(**item))
                        except Exception as e:
                            self.log.warning("⚠️  Failed to convert item to IngredientItem: %s - %s", item, e)
                            ingredients.append(self.IngredientItem(
                                name=item.get('name', 'unknown'),
                                quantity=item.get('quantity'),
                                optional=item.get('optional', False)
                            ))
                    else:
                        self.log.warning("⚠️  Unexpected item type in list: %s", type(item))
            elif isinstance(raw_output, dict):
                # Dict format (fallback handling)
                self.log.warning("⚠️  Model returned dict format. Extracting ingredients...")
                if 'ingredients' in raw_output:
                    ingredients_data = raw_output['ingredients']
                    if isinstance(ingredients_data, list):
                        ingredients = [
                            self.IngredientItem(**item) if isinstance(item, dict) else item
                            for item in ingredients_data
                        ]
                        self.log.info("✅ Extracted %d ingredients from dict format", len(ingredients))
                    else:
                        self.log.error("❌ 'ingredients' key is not a list: %s", type(ingredients_data))
                        raise ValueError("Invalid format: 'ingredients' is not a list")
                else:
                    self.log.error("❌ Dict format missing 'ingredients' key. Keys: %s", list(raw_output.keys()))
                    raise ValueError("Invalid format: dict missing 'ingredients' key")
            else:
                self.log.error("❌ Cannot extract ingredients from output type: %s", type(raw_output))
                raise ValueError(f"Cannot extract ingredients from output: {type(raw_output)}")
            
            self.log.info("📝 Got %d ingredients (took %.2fs)", len(ingredients), plan_time)
            
            # Log all ingredients for debugging
            self.log.debug("Ingredient list:")
            for idx, ing in enumerate(ingredients, 1):
                self.log.debug("  %d. %s (qty: %s, optional: %s)", idx, ing.name, ing.quantity or "N/A", ing.optional)
            
            # Warn if we got very few ingredients (might indicate planning issue)
            if len(ingredients) < 3:
                self.log.warning("⚠️  Only got %d ingredients - this might be incomplete. Expected 6-7 for a typical recipe.", len(ingredients))
            elif len(ingredients) > 10:
                self.log.warning("⚠️  Got %d ingredients - this might be too many. Consider simplifying.", len(ingredients))
            
            # Format plan for user
            response_parts = []
            response_parts.append("📋 **Here are the ingredients needed:**\n\n")
            for idx, ing in enumerate(ingredients, 1):
                qty_str = f" ({ing.quantity})" if ing.quantity else ""
                opt_str = " (optional)" if ing.optional else ""
                response_parts.append(f"{idx}. **{ing.name}**{qty_str}{opt_str}\n")
            
            # response_parts.append("\n🛒 **Would you like me to help you find and purchase these items from Blinkit?**\n")
            # response_parts.append("Just say 'yes' or 'proceed' and I'll search for them and add to your cart!\n")
            
            formatted_response = "".join(response_parts)
            self.log.debug("Formatted response length: %d chars", len(formatted_response))
            
            ingredients_data = [ing.model_dump() for ing in ingredients]
            self.log.debug("Ingredients data structure: %s", ingredients_data)
            
            return {
                "message": formatted_response,
                "ingredients": ingredients_data,
                "step": "plan_complete"  # Indicates we're waiting for user confirmation
            }
        except Exception as e:
            plan_time = time.time() - plan_start_time
            self.log.error("❌ ERROR: plan_recipe_ingredients failed after %.2fs - %s", plan_time, str(e))
            import traceback
            self.log.debug("Traceback: %s", traceback.format_exc())
            raise

    async def plan_and_shop(self, text: str):
        """Single-LLM plan, then batch search, then batch add, then cart summary."""
        import time
        plan_start_time = time.time()
        self.log.info("📝 Plan-and-shop: Starting plan-and-shop flow")
        self.log.debug("Input text length: %d chars", len(text))
        self.log.debug("Input text preview: %s", text[:200] + "..." if len(text) > 200 else text)
        
        # Step 1: Plan ingredients
        self.log.info("📝 Step 1/3: Planning ingredients from text...")
        plan_result = await self.plan_agent.run(text)
        ingredients: list = getattr(plan_result, "output", plan_result.output)
        plan_time = time.time() - plan_start_time
        self.log.info("📝 Step 1/3: Got %d ingredients (took %.2fs)", len(ingredients), plan_time)
        for idx, ing in enumerate(ingredients, 1):
            self.log.debug("  %d. %s (qty: %s, optional: %s)", idx, ing.name, ing.quantity or "N/A", ing.optional)

        # Step 2: Build cart by searching and adding ingredients
        self.log.info("🛒 Step 2/3: Building cart for %d ingredients...", len(ingredients))
        cart_build_start = time.time()
        cart_result = await self.build_cart_for_plan(ingredients)
        cart_build_time = time.time() - cart_build_start
        added_count = len(cart_result.get("added", []))
        skipped_count = len(cart_result.get("skipped", []))
        self.log.info("🛒 Step 2/3: Cart build complete - %d added, %d skipped (took %.2fs)", added_count, skipped_count, cart_build_time)


        # Step 3: Cart summary
        self.log.info("🛒 Step 3/3: Fetching cart summary...")
        cart = cart_result.get("cart") or await self.view_cart()
        cart_total = cart.get("total", 0)
        cart_items = len(cart.get("items", []))
        self.log.info("🛒 Step 3/3: Cart has %d items, Total: ₹%.2f", cart_items, cart_total)

        total_time = time.time() - plan_start_time
        self.log.info("✅ Plan-and-shop complete! Total time: %.2fs | Ingredients: %d | Added: %d | Skipped: %d | Cart Total: ₹%.2f",
                     total_time, len(ingredients), added_count, skipped_count, cart_total)

        # Format user-friendly response
        response_parts = []
        response_parts.append("✅ **Cart Updated Successfully!**\n")
        
        if added_count > 0:
            response_parts.append(f"**Added {added_count} item(s) to your cart:**\n")
            for item in cart_result.get("added", []):
                item_name = item.get("picked", "Unknown")
                qty = item.get("quantity", 1)
                price = item.get("line_total", 0)
                response_parts.append(f"  • {item_name} x{qty} - ₹{price:.2f}\n")
        
        if skipped_count > 0:
            response_parts.append(f"\n⚠️ **Could not find {skipped_count} item(s):**\n")
            response_parts.append(f"  {', '.join(cart_result.get('skipped', []))}\n")
        
        response_parts.append(f"\n**Cart Summary:**\n")
        response_parts.append(f"  • Total items: {cart_items}\n")
        response_parts.append(f"  • **Total amount: ₹{cart_total:.2f}**\n")
        
        # response_parts.append("\n💳 **Next steps:**\n")
        # response_parts.append("  Would you like to proceed to checkout and payment? Just say 'yes' or 'proceed to payment' and I'll help you complete the transaction!\n")

        formatted_response = "".join(response_parts)
        
        return {
            "message": formatted_response,
            "planned_ingredients": [ing.model_dump() for ing in ingredients],
            "added": cart_result.get("added", []),
            "skipped": cart_result.get("skipped", []),
            "cart": cart,
            "cart_total": cart_total,
        }

    async def run(self, user_message: str, writer=None):
        """Run agent with conversation history (last 3-4 exchanges).
        
        Args:
            user_message: The user's message to process
            writer: Optional callable that receives streaming chunks as dict with 'content' key.
                   If provided, enables streaming mode using stream_text().
                   If None, uses non-streaming mode (default).
        """
        import time
        run_start_time = time.time()
        self.log.info("🤖 AGENT RUN: Processing user message (history: %d exchanges, streaming=%s)", 
                     len(self.conversation_history), writer is not None)
        self.log.debug("User message: %s", user_message[:100] + "..." if len(user_message) > 100 else user_message)

        # Fast-path for "add all ingredients" / "shop them all" intent
        lower_msg = user_message.lower()
        # Check if user wants to shop/add all items
        shop_intent_keywords = [
            "shop them all", "shop for them", "shop for all", "shop all",
            "buy them all", "buy all", "buy the ingredients",
            "add them all", "add all", "add the ingredients",
            "get them all", "get all", "order them all", "order all"
        ]
        # Also check if previous conversation was about ingredients/recipe
        has_recipe_context = False
        if self.conversation_history:
            last_assistant_msg = self.conversation_history[-1][1].lower()
            has_recipe_context = any(word in last_assistant_msg for word in ["ingredient", "recipe", "biryani", "cooking", "dish"])
        
        # Trigger plan-and-shop if:
        # 1. User explicitly says to shop/add/buy all/them
        # 2. OR user says "yes" + shop-related words AND previous context was about ingredients
        # if any(keyword in lower_msg for keyword in shop_intent_keywords) or \
        #    (has_recipe_context and ("yes" in lower_msg or "i will" in lower_msg) and ("shop" in lower_msg or "buy" in lower_msg or "add" in lower_msg)):
        #     self.log.info("⚡ Detected plan-and-shop intent; running batch flow")
        if(False):
            try:
                # Use conversation history to get full ingredient list if available
                context_text = user_message
                if self.conversation_history and has_recipe_context:
                    # Include previous assistant message which likely has the ingredient list
                    context_text = self.conversation_history[-1][1] + "\n\n" + user_message
                
                result = await self.plan_and_shop(context_text)
                elapsed = time.time() - run_start_time
                self.log.info("✅ PLAN+SHOP SUCCESS (took %.2fs)", elapsed)
                # Use formatted message for user-facing response, but keep full data in history
                formatted_msg = result.get("message", str(result))
                self.conversation_history.append((user_message, formatted_msg))
                if len(self.conversation_history) > self.max_history_exchanges:
                    self.conversation_history = self.conversation_history[-self.max_history_exchanges:]
                return formatted_msg
            except Exception as e:
                self.log.error("❌ PLAN+SHOP ERROR: %s", str(e))
                # fall through to normal agent
        
        # Build context: if we have a summary, use summary + last 3 exchanges; else use last N exchanges
        context_parts = []
        if self.conversation_summary.strip():
            context_parts.append("**Conversation summary (use for info and next steps):**\n")
            context_parts.append(self.conversation_summary.strip())
            context_parts.append("\n\n")
            if self.conversation_history:
                last_three = self.conversation_history[-3:]
                context_parts.append("**Last 3 exchanges:**\n")
                for user_msg, assistant_msg in last_three:
                    context_parts.append(f"User: {user_msg}\nAssistant: {assistant_msg}")
                context_parts.append("\n\n**Current question:**\n")
        elif self.conversation_history:
            self.log.debug("Building context from %d previous exchanges", len(self.conversation_history))
            context_parts.append("**Previous conversation:**")
            last_three = self.conversation_history[-3:]
            for i, (user_msg, assistant_msg) in enumerate(last_three, 1):
                context_parts.append(f"\n{i}. User: {user_msg}")
                context_parts.append(f"\nAssistant: {assistant_msg}")
            context_parts.append("\n\n**Current question:**")

        # Combine context with current message
        full_message = "".join(context_parts) + "\n" + user_message if context_parts else user_message
        # print(f"\n\n\n\nfull_message: {full_message}\n\n\n\n")
        try:
            # Run agent (without message_history to avoid format issues)
            self.log.debug("Sending request to agent model...")
            agent_start = time.time()


            #   without streaming
            # resp = await self.agent.run(full_message)
            # agent_run_time = time.time() - agent_start
            # assistant_response = getattr(resp, "output", resp.output)
            
            # # Check if tools were used and log timing breakdown
            # tool_call_times = []
            # if hasattr(resp, 'all_messages'):
            #     messages = resp.all_messages()
            #     tool_calls = [msg for msg in messages if hasattr(msg, 'tool_calls') and msg.tool_calls]
            #     if tool_calls:
            #         self.log.info("🔧 Agent used %d tool call(s) in this run", len(tool_calls))
            #         # Try to extract tool call timing if available
            #         for msg in tool_calls:
            #             for tool_call in msg.tool_calls:
            #                 tool_name = getattr(tool_call, 'name', 'unknown')
            #                 self.log.debug("  Tool called: %s", tool_name)
            
            
            if writer is None:
                # Non-streaming path (default behavior)
                resp = await self.agent.run(full_message)
                agent_run_time = time.time() - agent_start
                assistant_response = getattr(resp, "output", resp.output)
                
                # Check if tools were used and log timing breakdown
                if hasattr(resp, 'all_messages'):
                    messages = resp.all_messages()
                    tool_calls = [msg for msg in messages if hasattr(msg, 'tool_calls') and msg.tool_calls]
                    if tool_calls:
                        self.log.info("🔧 Agent used %d tool call(s) in this run", len(tool_calls))
                        # Try to extract tool call timing if available
                        for msg in tool_calls:
                            for tool_call in msg.tool_calls:
                                tool_name = getattr(tool_call, 'name', 'unknown')
                                self.log.debug("  Tool called: %s", tool_name)
            else:
                # Streaming path using stream_text()
                import inspect

                final_output = ""
                previous_output = ""
                tool_calls_count = 0
                first_chunk_time = None
                chunk_count = 0

                async with self.agent.run_stream(full_message) as stream_result:
                    # Stream text chunks as they arrive. stream_text() may yield the
                    # full-so-far text, so we diff and only send the new suffix.
                    async for text_chunk in stream_result.stream_text():
                        if text_chunk is None:
                            continue

                        chunk_count += 1
                        if first_chunk_time is None:
                            first_chunk_time = time.time()
                            time_to_first_chunk = first_chunk_time - agent_start
                            self.log.info("📡 First chunk arrived after %.2fs", time_to_first_chunk)

                        text_str = str(text_chunk)

                        # Compute only the new part to avoid duplicates
                        if text_str.startswith(previous_output):
                            new_part = text_str[len(previous_output) :]
                        else:
                            # Fallback if something unexpected happens
                            new_part = text_str

                        final_output = text_str
                        previous_output = text_str

                        if new_part:
                            # Support both sync and async writer callbacks
                            if writer is not None:
                                if inspect.iscoroutinefunction(writer):
                                    await writer({"content": new_part})
                                else:
                                    writer({"content": new_part})
                    
                    if first_chunk_time:
                        self.log.info("📡 Streaming complete: %d chunks received, first chunk at %.2fs", 
                                     chunk_count, first_chunk_time - agent_start)

                    # Ensure we have the final full output for history
                    if not final_output:
                        final_resp = await stream_result.get_output()
                        final_output = getattr(final_resp, "output", final_resp.output) if final_resp else ""

                    # Check for tool calls in the stream result
                    if hasattr(stream_result, 'all_messages'):
                        messages = stream_result.all_messages()
                        tool_calls = [msg for msg in messages if hasattr(msg, 'tool_calls') and msg.tool_calls]
                        tool_calls_count = len(tool_calls)
                        if tool_calls:
                            self.log.info("🔧 Agent used %d tool call(s) in this run", tool_calls_count)
                            for msg in tool_calls:
                                for tool_call in msg.tool_calls:
                                    tool_name = getattr(tool_call, 'name', 'unknown')
                                    self.log.debug("  Tool called: %s", tool_name)
                
                agent_run_time = time.time() - agent_start
                assistant_response = final_output
            
            elapsed = time.time() - run_start_time
            self.log.info("✅ AGENT SUCCESS: Response generated (length: %d chars)", len(str(assistant_response)))
            self.log.info("⏱️  AGENT TIMING: Total=%.2fs | Agent.run()=%.2fs | Overhead=%.2fs", 
                         elapsed, agent_run_time, elapsed - agent_run_time)
            self.log.debug("Agent response: %s", str(assistant_response)[:200] + "..." if len(str(assistant_response)) > 200 else str(assistant_response))
            
            # Store this exchange
            self.conversation_history.append((user_message, str(assistant_response)))

            # Keep last max_history_for_summariser exchanges (so we can run summariser every 3)
            if len(self.conversation_history) > self.max_history_for_summariser:
                self.conversation_history = self.conversation_history[-self.max_history_for_summariser:]
                self.log.debug("Trimmed conversation history to last %d exchanges", self.max_history_for_summariser)

            # Run summariser every 3 turns (incremental: merge with previous summary when present)
            if len(self.conversation_history) >= 3 and len(self.conversation_history) % 3 == 0:
                try:
                    self.conversation_summary = await self._run_summariser()
                except Exception as e:
                    self.log.warning("⚠️ Summariser failed (run): %s – keeping previous summary", str(e))

            return assistant_response
        except Exception as e:
            self.log.error("❌ AGENT ERROR: Failed to process user message - %s", str(e))
            raise

    def clear_history(self):
        """Clear conversation history and summary."""
        count = len(self.conversation_history)
        self.conversation_history = []
        self.conversation_summary = ""
        self.log.info("🗑️  Cleared conversation history and summary (%d exchanges removed)", count)

    async def close(self):
        if self.blinkit_client:
            self.blinkit_client.close()
        if self.payment_client:
            self.payment_client.close()


async def main():
    import sys
    
    # Allow log level to be set via environment variable or command line
    log_level = logging.INFO
    if "--debug" in sys.argv:
        log_level = logging.DEBUG
    elif "--warning" in sys.argv:
        log_level = logging.WARNING
    
    agent = UnifiedAgent(log_level=log_level)
    agent.log.info("🚀 Unified Agent initialized")
    agent.log.info("Log level: %s", logging.getLevelName(log_level))
    if log_level == logging.DEBUG:
        agent.log.debug("Debug mode enabled - detailed logs will be shown")
    
    print("Unified NPCI + Shopping Agent. Type 'exit' to quit.")
    print("(Use --debug for detailed logs, --warning for minimal logs)\n")
    
    try:
        while True:
            user = input("You: ").strip()
            if user.lower() in ("exit", "quit"):
                agent.log.info("👋 User requested exit")
                break
            if not user:
                continue
            print("Agent:", await agent.run(user))
            print()  # Empty line for readability
    except KeyboardInterrupt:
        agent.log.info("⚠️  Interrupted by user")
    except Exception as e:
        agent.log.error("💥 Fatal error: %s", str(e))
        raise
    finally:
        agent.log.info("🔌 Closing agent and cleaning up...")
        await agent.close()
        agent.log.info("✅ Agent closed successfully")


if __name__ == "__main__":
    asyncio.run(main())
