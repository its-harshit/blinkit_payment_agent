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
    from .mcp_client import McpClient
except ImportError:
    from mcp_client import McpClient


MCP_TOOLS_DIR = Path(__file__).parent
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]

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

        instructions = (
            "You are an NPCI CUSTOMER SUPPORT BOT with generic worldly information and shopping capabilities.\n"
            "- Default behavior: answer user queries clearly and concisely.\n"
            "\n"
            "**CORE RULES - CRITICAL:**\n"
            "1. NEVER make up or invent information. Only use data from tool results or general knowledge.\n"
            "3. For UPI queries without specific data: provide general guidance only (collect txn ID, VPA, time, bank).\n"
            "4. Use tools ONLY when user explicitly requests: plan recipe ingredients, search, add to cart, checkout, or payment.\n"
            "5. ALWAYS use actual tool results. Never invent product IDs, prices, or cart contents.\n"
            "6. When you need to use a tool, you MUST call it. Do not describe what you would do to the user- actually invoke the tool.\n"
            "\n"
            "**HOW TO USE TOOLS:**\n"
            "You have access to several tools that you MUST use when the user requests shopping or payment operations.\n"
            "When you need to use a tool, the system will automatically call it for you. You just need to:\n"
            "1. Identify when a tool is needed (e.g., user asks to search, add to cart, or pay)\n"
            "2. The tool will be called automatically with the appropriate parameters\n"
            "3. Use the tool results to respond to the user\n"
            "4. YOU DON'T NEED TO TELL THE USER THAN YOU WILL BE CALLING THIS TOOL, JUST CALL THE TOOL IMMEDIATELY.\n"
            "\n"
            "**AVAILABLE TOOLS:**\n"
            "- get_product(item_id): Get details of a specific product by ID (e.g., 'blk-001')\n"
            "- search_items(item_names, quantities): Search items (single or multiple) and return results without adding to cart. Pass a list of item names, e.g., ['milk'] or ['milk', 'bread']. Returns found_items array with IDs, names, prices.\n"
            "- add_items_to_cart_by_ids(items): Add items (single or multiple) to cart using their IDs. Pass a list of items with 'id' and 'quantity' fields, e.g., [{'id': 'blk-001', 'quantity': 2}] or [{'id': 'blk-001', 'quantity': 1}, {'id': 'blk-002', 'quantity': 2}]\n"
            "- view_cart(): View current cart contents and total\n"
            "- clear_cart(): Clear all items from cart\n"
            "- plan_recipe_ingredients_tool(recipe_text): Plan ingredients needed for a recipe (e.g., 'biryani', 'dosa')\n"
            "- create_payment(amount, order_id): Create payment intent (amount in INR, order_id optional)\n"
            "- check_payment_status(payment_id): Check payment status by payment ID. IMPORTANT: This MUST be called after create_payment to complete the transaction and automatically clear the cart.\n"
            "\n"
            "**TOOL CALLING EXAMPLES:**\n"
            "- User: 'Search for milk' → Use search_items(item_names=['milk'])\n"
            "- User: 'Add blk-001 to cart' → Use add_items_to_cart_by_ids(items=[{'id': 'blk-001', 'quantity': 1}])\n"
            "- User: 'Search for milk and bread' → Use search_items(item_names=['milk', 'bread'])\n"
            "- User: 'What's in my cart?' → Use view_cart()\n"
            "- User: 'Buy ingredients for biryani' → Use plan_recipe_ingredients_tool(recipe_text='biryani'), then search_items, then add_items_to_cart_by_ids\n"
            "- User: 'Checkout and pay' → Use view_cart() to get total, then create_payment(amount=total), then IMMEDIATELY check_payment_status(payment_id=...) to complete payment and clear cart\n"
            "\n"
            "**RECIPE SHOPPING FLOW (when user asks to buy items for a dish/recipe):**\n"
            "1. When user asks to buy items for a recipe, you should first call plan_recipe_ingredients_tool(recipe_text='...') with the recipe/dish name.\n"
            "2. Display the ingredient list from the plan result to the user and ask if they would like to find and purchase these items.\n"
            "3. If user confirms, use the search_items tool with the ingredient names from the plan result to search for them in supermarket.\n"
            "4. After search_items completes, the tool returns a dict with 'found_items' array and 'skipped' list. Display the found items in a formatted table. Also mention any items that were not found. Then ask the user if they would like to add these items to their cart.\n"
            "5. If user confirms adding to cart, use add_items_to_cart_by_ids with the items from the search results. To be sure of the ids, you can once again call the search_items tool with the item names to get the actual ids and use them to add to cart.\n"
            "Each item should have at least 'id' (like 'blk-101') and 'quantity' fields. Use the actual item IDs from the search results, not placeholder IDs.\n"
            "6. After add_items_to_cart_by_ids completes, show the cart summary from the result and STOP. Ask the user if they would like to add more items or proceed to checkout.\n"
            "7. If user wants to proceed to checkout, first call view_cart to get the cart total, then use create_payment with the amount (order_id is optional, will be auto-generated), then IMMEDIATELY call check_payment_status with the payment_id from create_payment result to complete the transaction and clear the cart.\n"
            "8. If user wants to add more items, let them specify the item names and use search_items again, then add_items_to_cart_by_ids after confirmation.\n"
            "\n"
            "- IMPORTANT: Always wait for user confirmation before proceeding to the next step in recipe shopping flow.\n"
            "- IMPORTANT: After searching items, show results and get confirmation BEFORE adding to cart.\n"
            "- IMPORTANT: After adding items to cart, always show cart summary before asking about checkout.\n"
            "- IMPORTANT: When user confirms checkout/payment, process payment directly without asking again.\n"
            "- After successful payment (when check_payment_status returns success/completed), the cart is automatically cleared. "
            "You don't need to manually clear it.\n"
            "- PREFERRED FLOW: Always use search_items first (to show results), then add_items_to_cart_by_ids after user confirms. " 
            "This gives better UX as user can review items before adding to cart. Works for both single and multiple items.\n"
            "- When planning ingredients, prefer only 6-7 most basic common ingredients available in raw form at Indian supermarkets/grocery stores. Avoid exotic or hard-to-find items or ultra processed things which might be hard to exactly find; suggest nearest simple substitutes.\n"
            
        )

        self.blinkit_client: McpClient | None = None
        self.payment_client: McpClient | None = None
        self.conversation_history: list[tuple[str, str]] = []  # Store (user_msg, assistant_msg) pairs
        self.max_history_exchanges = 3  # Keep last 3-4 exchanges
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

        # Create tool functions that access self via closure, using RunContext as first param
        async def search_products(ctx: RunContext, query: Annotated[str, "Product name or category"], limit: Annotated[int, "Max results"] = 5):
            import time
            start_time = time.time()
            self.log.info("🔍 TOOL CALL: search_products(query=%s, limit=%d)", query, limit)
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.search with params: %s", {"query": query, "limit": limit})
                result = await self.blinkit_client.call_tool("blinkit.search", {"query": query, "limit": limit})
                items = json.loads(result["content"][0]["text"])
                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: search_products found %d items (took %.2fs)", len(items), elapsed)
                self.log.debug("Search results: %s", items[:2] if len(items) > 2 else items)  # Log first 2 items
                return items
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_products failed after %.2fs - %s", elapsed, str(e))
                raise

        async def get_product(ctx: RunContext, item_id: Annotated[str, "Product ID (e.g., blk-001)"]):
            self.log.info("🔍 TOOL CALL: get_product(item_id=%s)", item_id)
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.item with params: %s", {"id": item_id})
                result = await self.blinkit_client.call_tool("blinkit.item", {"id": item_id})
                item = json.loads(result["content"][0]["text"])
                self.log.info("✅ TOOL SUCCESS: get_product retrieved item: %s", item.get("name", item_id))
                self.log.debug("Product details: %s", item)
                return item
            except Exception as e:
                self.log.error("❌ TOOL ERROR: get_product failed - %s", str(e))
                raise

        async def add_to_cart(ctx: RunContext, item_id: Annotated[str, "Product ID"], quantity: Annotated[int, "Quantity (min 1)"] = 1):
            import time
            start_time = time.time()
            qty = max(1, quantity)
            self.log.info("🛒 TOOL CALL: add_to_cart(item_id=%s, quantity=%d)", item_id, qty)
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.add_to_cart with params: %s", {"id": item_id, "quantity": qty})
                result = await self.blinkit_client.call_tool("blinkit.add_to_cart", {"id": item_id, "quantity": qty})
                entry = json.loads(result["content"][0]["text"])
                item_name = entry.get("item", {}).get("name", item_id)
                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: add_to_cart added %d x %s (took %.2fs)", entry.get("quantity", qty), item_name, elapsed)
                self.log.debug("Cart entry: %s", entry)
                return entry
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: add_to_cart failed after %.2fs - %s", elapsed, str(e))
                raise

        async def search_items(ctx: RunContext, item_names: Annotated[list[str], "List of item names to search (can be single item as list)"], quantities: Annotated[list[int] | None, "Optional list of quantities (defaults to 1 for each)"] = None):
            """Search for multiple items and return results (without adding to cart). 
            
            Use this to search items first, show results to user, then ask for confirmation before adding.
            Returns a dict with 'found_items' array. Each item in 'found_items' has: {'id': 'blk-xxx', 'name': '...', 'price': N, 'quantity': N, 'original_name': '...'}
            IMPORTANT: When user confirms, pass the ENTIRE 'found_items' array directly to add_items_to_cart_by_ids. Do not modify or recreate the items.
            Uses the same fast sequential search method as _pick_and_add.
            """
            import time
            start_time = time.time()
            self.log.info("🔍 TOOL CALL: search_items(%d items)", len(item_names))
            self.log.debug("Item names: %s", item_names)
            self.log.debug("Quantities: %s", quantities)
            
            try:
                await self._ensure_blinkit()
                
                found_items = []
                skipped = []
                
                # Search each item sequentially (like _pick_and_add) - faster than parallel chunking
                for idx, item_name in enumerate(item_names):
                    self.log.debug("Processing item %d/%d: %s", idx + 1, len(item_names), item_name)
                    name = item_name.strip()
                    queries = [name]
                    key = name.lower()
                    
                    # Check for aliases
                    if key in self.search_aliases:
                        aliases = self.search_aliases[key]
                        queries.extend(aliases)
                        self.log.debug("  Found aliases for '%s': %s", name, aliases)
                    else:
                        self.log.debug("  No aliases found for '%s'", name)
                    
                    self.log.debug("  Search queries to try: %s", queries)
                    
                    items = []
                    tried = []
                    for q in queries:
                        self.log.info("Searching Blinkit for: %s", q)
                        tried.append(q)
                        try:
                            resp = await self.blinkit_client.call_tool("blinkit.search", {"query": q, "limit": 3})
                            found = json.loads(resp["content"][0]["text"])
                            if found:
                                items = found
                                self.log.debug("  ✅ Found %d result(s) for query '%s'", len(found), q)
                                break
                            else:
                                self.log.debug("  ⚠️  No results for query '%s'", q)
                        except Exception as search_error:
                            self.log.warning("  ❌ Search error for query '%s': %s", q, str(search_error))
                    
                    if not items:
                        self.log.warning("⚠️  No results for item '%s' after trying queries: %s", name, tried)
                        skipped.append(name)
                        continue
                    
                    choice = items[0]
                    original_qty = quantities[idx] if quantities and idx < len(quantities) else 1
                    qty = max(1, original_qty)
                    
                    # Clamp to stock and sensible upper bound
                    stock = choice.get("stock", qty)
                    original_qty_for_clamp = qty
                    qty = min(qty, stock, 5)
                    
                    if qty != original_qty_for_clamp:
                        self.log.debug("  Quantity clamped: %d -> %d (stock=%d, max=5)", original_qty_for_clamp, qty, stock)
                    
                    found_item = {
                        "id": choice["id"],
                        "name": choice.get("name"),
                        "price": choice.get("price", 0),
                        "quantity": qty,
                        "original_name": name
                    }
                    found_items.append(found_item)
                    self.log.info("✅ Found: %s x%d (%s) - ₹%.2f", choice.get("name"), qty, choice.get("id"), choice.get("price", 0))
                    self.log.debug("  Item details: %s", found_item)
                
                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: search_items - %d found, %d skipped (took %.2fs)",
                             len(found_items), len(skipped), elapsed)
                self.log.debug("Found items summary: %s", [{"id": item["id"], "name": item["name"], "qty": item["quantity"]} for item in found_items])
                if skipped:
                    self.log.debug("Skipped items: %s", skipped)
                
                return {
                    "found_items": found_items,
                    "skipped": skipped,
                    "time_taken": elapsed
                }
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_items failed after %.2fs - %s", elapsed, str(e))
                import traceback
                self.log.debug("Traceback: %s", traceback.format_exc())
                raise

        async def add_items_to_cart_by_ids(ctx: RunContext, items: Annotated[list[dict], "List of items to add to cart. Each item should be a dict with at least 'id' (product ID like 'blk-101') and 'quantity' (number). Optional fields: 'name', 'price'. You can use items from search_items results or construct them with the IDs from search results."]):
            """Add multiple items to cart by their IDs (after user confirms search results).
            
            Use this after search_items when user confirms they want to add items.
            Each item should be a dict with:
            - 'id' (required): Product ID from search results (e.g., 'blk-101', 'blk-029')
            - 'quantity' (required): Number of items to add (defaults to 1 if not provided)
            - 'name' (optional): Item name for reference
            - 'price' (optional): Item price for reference
            
            You can pass the 'found_items' array from search_items, or construct items using the IDs from the search results.
            Uses sequential processing for reliability.
            """
            import time
            start_time = time.time()
            self.log.info("🛒 TOOL CALL: add_items_to_cart_by_ids(%d items)", len(items))
            
            # Log what we received for debugging
            received_ids = [item.get("id", "NO_ID") for item in items]
            self.log.info("📋 Received items with IDs: %s", received_ids)
            self.log.debug("Full received items structure: %s", items)
            
            # Validate structure
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    self.log.warning("⚠️  Item %d is not a dict: %s", idx, type(item))
                elif "id" not in item:
                    self.log.warning("⚠️  Item %d missing 'id' field: %s", idx, item)
            
            try:
                await self._ensure_blinkit()
                
                successful = []
                failed = []
                
                self.log.debug("Starting sequential add process for %d items", len(items))
                self.log.info("⏱️  Starting to add %d items to cart (sequential mode)", len(items))
                
                # Track timing for each item
                item_timings = []
                
                # Add items sequentially (like _pick_and_add) - faster and more reliable
                for idx, item in enumerate(items):
                    item_start = time.time()
                    self.log.debug("Processing item %d/%d: %s", idx + 1, len(items), item)
                    item_id = item.get("id")
                    original_quantity = item.get("quantity", 1)
                    quantity = max(1, original_quantity)
                    item_name = item.get("name", "Unknown")
                    item_price = item.get("price", 0)
                    
                    self.log.debug("  Item details: id=%s, name=%s, qty=%d (original=%d), price=₹%.2f", 
                                  item_id, item_name, quantity, original_quantity, item_price)
                    
                    # Validate that we have a proper ID
                    if not item_id:
                        self.log.error("❌ Missing item ID for item %d: %s", idx, item)
                        failed.append({"item": item, "error": "Missing ID"})
                        item_timings.append({"item": item_name, "time": time.time() - item_start, "status": "failed", "reason": "Missing ID"})
                        continue
                    
                    if not item_id.startswith("blk-"):
                        self.log.error("❌ Invalid item ID format: '%s' (expected 'blk-xxx'). Item: %s", item_id, item)
                        failed.append({"item": item, "error": f"Invalid ID format: {item_id}"})
                        item_timings.append({"item": item_name, "time": time.time() - item_start, "status": "failed", "reason": "Invalid ID"})
                        continue
                    
                    try:
                        self.log.debug("  📞 Calling blinkit.add_to_cart with id=%s, quantity=%d", item_id, quantity)
                        mcp_call_start = time.time()
                        added = await self.blinkit_client.call_tool(
                            "blinkit.add_to_cart", {"id": item_id, "quantity": quantity}
                        )
                        mcp_call_time = time.time() - mcp_call_start
                        
                        parse_start = time.time()
                        entry = json.loads(added["content"][0]["text"])
                        parse_time = time.time() - parse_start
                        
                        added_item_name = entry.get("item", {}).get("name", item_id)
                        added_qty = entry.get("quantity", quantity)
                        added_price = entry.get("item", {}).get("price", 0)
                        
                        item_total_time = time.time() - item_start
                        item_timings.append({
                            "item": added_item_name,
                            "time": item_total_time,
                            "mcp_time": mcp_call_time,
                            "parse_time": parse_time,
                            "status": "success"
                        })
                        
                        self.log.info("✅ Added: %s x%d (%s) - ₹%.2f | ⏱️  Total: %.2fs (MCP: %.2fs, Parse: %.3fs)", 
                                     added_item_name, added_qty, item_id, added_price, 
                                     item_total_time, mcp_call_time, parse_time)
                        self.log.debug("  Cart entry: %s", entry)
                        successful.append(entry)
                    except Exception as e:
                        item_total_time = time.time() - item_start
                        item_timings.append({
                            "item": item_name,
                            "time": item_total_time,
                            "status": "failed",
                            "error": str(e)
                        })
                        self.log.warning("⚠️  Failed to add item %s (qty=%d) after %.2fs: %s", item_id, quantity, item_total_time, str(e))
                        self.log.debug("  Error details: %s", str(e))
                        import traceback
                        self.log.debug("  Traceback: %s", traceback.format_exc())
                        failed.append({"item": {"id": item_id, "quantity": quantity, "name": item_name}, "error": str(e)})

                elapsed = time.time() - start_time
                
                # Log detailed timing breakdown
                if item_timings:
                    total_mcp_time = sum(t.get("mcp_time", 0) for t in item_timings if "mcp_time" in t)
                    total_parse_time = sum(t.get("parse_time", 0) for t in item_timings if "parse_time" in t)
                    avg_item_time = sum(t["time"] for t in item_timings) / len(item_timings)
                    max_item_time = max(t["time"] for t in item_timings)
                    min_item_time = min(t["time"] for t in item_timings)
                    
                    self.log.info("⏱️  TIMING BREAKDOWN:")
                    self.log.info("  • Total time: %.2fs", elapsed)
                    self.log.info("  • Items processed: %d", len(item_timings))
                    self.log.info("  • Avg per item: %.2fs | Min: %.2fs | Max: %.2fs", avg_item_time, min_item_time, max_item_time)
                    if total_mcp_time > 0:
                        self.log.info("  • Total MCP call time: %.2fs (%.1f%% of total)", total_mcp_time, (total_mcp_time / elapsed * 100) if elapsed > 0 else 0)
                    if total_parse_time > 0:
                        self.log.info("  • Total parse time: %.3fs (%.1f%% of total)", total_parse_time, (total_parse_time / elapsed * 100) if elapsed > 0 else 0)
                    self.log.debug("  • Per-item timings: %s", item_timings)
                
                self.log.info("✅ TOOL SUCCESS: add_items_to_cart_by_ids - %d succeeded, %d failed (took %.2fs)",
                             len(successful), len(failed), elapsed)
                
                if successful:
                    self.log.debug("Successfully added items: %s", 
                                  [{"id": r.get("item", {}).get("id"), "name": r.get("item", {}).get("name"), "qty": r.get("quantity")} 
                                   for r in successful])
                if failed:
                    self.log.warning("Failed items: %s", failed)

                # Get cart summary
                self.log.debug("Fetching cart summary...")
                cart_start = time.time()
                cart_res = await self.blinkit_client.call_tool("blinkit.cart", {})
                cart_mcp_time = time.time() - cart_start
                cart_parse_start = time.time()
                cart = json.loads(cart_res["content"][0]["text"])
                cart_parse_time = time.time() - cart_parse_start
                cart_items_count = len(cart.get("items", []))
                cart_total = cart.get("total", 0)
                cart_total_time = time.time() - cart_start
                self.log.info("📊 Cart summary fetched: %d items, Total: ₹%.2f (took %.2fs: MCP=%.2fs, Parse=%.3fs)", 
                             cart_items_count, cart_total, cart_total_time, cart_mcp_time, cart_parse_time)
                self.log.debug("Cart details: %s", cart)

                return {
                    "successful": successful,
                    "failed": failed,
                    "successful_items": [{"name": r.get("item", {}).get("name"), "quantity": r.get("quantity")} for r in successful],
                    "failed_items": failed,
                    "cart": cart,
                    "time_taken": elapsed
                }
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: add_items_to_cart_by_ids failed after %.2fs - %s", elapsed, str(e))
                import traceback
                self.log.debug("Traceback: %s", traceback.format_exc())
                raise

        async def search_and_add_items(ctx: RunContext, item_names: Annotated[list[str], "List of item names to search and add to cart"], quantities: Annotated[list[int] | None, "Optional list of quantities (defaults to 1 for each)"] = None):
            """Search for multiple items and add them to cart in one efficient flow (similar to plan_and_shop).
            
            This tool searches all items in parallel, maps results, and adds them to cart in parallel.
            Much faster than calling search_products and add_to_cart separately.
            NOTE: For better UX, prefer using search_items first, then add_items_to_cart_by_ids after user confirmation.
            """
            import time
            start_time = time.time()
            self.log.info("🛒 TOOL CALL: search_and_add_items(%d items)", len(item_names))
            try:
                await self._ensure_blinkit()
                
                # Prepare search queries with aliases (similar to plan_and_shop)
                queries_per_item = []
                all_queries = []
                for idx, item_name in enumerate(item_names):
                    name = item_name.strip()
                    variants = [name]
                    key = name.lower()
                    if key in self.search_aliases:
                        variants.extend(self.search_aliases[key])
                    queries_per_item.append((idx, name, variants))
                    for v in variants:
                        if v not in all_queries:
                            all_queries.append(v)
                
                self.log.info("🔍 Searching %d unique queries for %d items", len(all_queries), len(item_names))
                
                # Search all queries in parallel (chunked)
                async def search_one(q):
                    try:
                        res = await self.blinkit_client.call_tool("blinkit.search", {"query": q, "limit": 5})
                        return json.loads(res["content"][0]["text"])
                    except Exception as e:
                        return e
                
                chunk_size = 5
                search_map = {}
                for i in range(0, len(all_queries), chunk_size):
                    chunk = all_queries[i:i + chunk_size]
                    chunk_results = await asyncio.gather(*[search_one(q) for q in chunk], return_exceptions=True)
                    for q, r in zip(chunk, chunk_results):
                        if isinstance(r, Exception):
                            self.log.debug("Search failed for %s: %s", q, r)
                            search_map[q] = []
                        else:
                            search_map[q] = r
                
                # Map items to search results
                add_items = []
                skipped = []
                for idx, name, variants in queries_per_item:
                    chosen = None
                    for v in variants:
                        hits = search_map.get(v, [])
                        if hits:
                            chosen = hits[0]
                            break
                    if not chosen:
                        skipped.append(name)
                        continue
                    
                    qty = quantities[idx] if quantities and idx < len(quantities) else 1
                    qty = max(1, min(qty, chosen.get("stock", qty), 5))  # Clamp quantity
                    add_items.append({"id": chosen["id"], "quantity": qty, "name": chosen.get("name")})
                
                self.log.info("🔍 Search complete - %d found, %d skipped", len(add_items), len(skipped))
                
                # Add all items to cart in parallel (chunked)
                if add_items:
                    self.log.info("🛒 Adding %d items to cart", len(add_items))
                    async def add_one(item):
                        try:
                            res = await self.blinkit_client.call_tool("blinkit.add_to_cart", {"id": item["id"], "quantity": item["quantity"]})
                            return json.loads(res["content"][0]["text"])
                        except Exception as e:
                            return e
                    
                    chunk_size = 3
                    successful = []
                    failed = []
                    for i in range(0, len(add_items), chunk_size):
                        chunk = add_items[i:i + chunk_size]
                        chunk_results = await asyncio.gather(*[add_one(item) for item in chunk], return_exceptions=True)
                        for j, r in enumerate(chunk_results):
                            if isinstance(r, Exception):
                                failed.append({"item": chunk[j], "error": str(r)})
                            else:
                                successful.append(r)
                    
                    elapsed = time.time() - start_time
                    self.log.info("✅ TOOL SUCCESS: search_and_add_items - %d added, %d failed, %d skipped (took %.2fs)",
                                 len(successful), len(failed), len(skipped), elapsed)
                    
                    # Get cart summary
                    cart_res = await self.blinkit_client.call_tool("blinkit.cart", {})
                    cart = json.loads(cart_res["content"][0]["text"])
                    
                    return {
                        "added": len(successful),
                        "failed": len(failed),
                        "skipped": skipped,
                        "successful_items": [{"name": r.get("item", {}).get("name"), "quantity": r.get("quantity")} for r in successful],
                        "failed_items": failed,
                        "cart": cart,
                        "time_taken": elapsed
                    }
                else:
                    elapsed = time.time() - start_time
                    self.log.warning("⚠️  No items found to add")
                    return {
                        "added": 0,
                        "failed": 0,
                        "skipped": skipped,
                        "successful_items": [],
                        "failed_items": [],
                        "cart": None,
                        "time_taken": elapsed
                    }
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_and_add_items failed after %.2fs - %s", elapsed, str(e))
                raise

        async def view_cart(ctx: RunContext):
            self.log.info("🛒 TOOL CALL: view_cart()")
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.cart")
                result = await self.blinkit_client.call_tool("blinkit.cart", {})
                cart = json.loads(result["content"][0]["text"])
                item_count = len(cart.get("items", []))
                total = cart.get("total", 0)
                self.log.info("✅ TOOL SUCCESS: view_cart - %d items, Total: ₹%.2f", item_count, total)
                self.log.debug("Cart contents: %s", cart)
                return cart
            except Exception as e:
                self.log.error("❌ TOOL ERROR: view_cart failed - %s", str(e))
                raise

        async def clear_cart(ctx: RunContext):
            """Clear all items from the cart (typically called after successful payment)."""
            self.log.info("🗑️  TOOL CALL: clear_cart()")
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.clear_cart")
                result = await self.blinkit_client.call_tool("blinkit.clear_cart", {})
                cleared = json.loads(result["content"][0]["text"])
                items_removed = cleared.get("itemsRemoved", 0)
                self.log.info("✅ TOOL SUCCESS: clear_cart - Removed %d item(s) from cart", items_removed)
                self.log.debug("Clear cart result: %s", cleared)
                return cleared
            except Exception as e:
                self.log.error("❌ TOOL ERROR: clear_cart failed - %s", str(e))
                raise

        async def plan_recipe_ingredients_tool(ctx: RunContext, recipe_text: Annotated[str, "Recipe or dish name (e.g., 'biryani', 'dosa', 'chole bhature')"]):
            """Plan ingredients needed for a recipe. Returns the ingredient list and asks user to confirm before buying.
            
            Use this tool when user asks to buy items for a recipe/dish. This is step 1 - it only plans, doesn't add to cart.
            After showing the plan, ask user if they want to buy these items from supermarket.
            """
            import time
            tool_start = time.time()
            self.log.info("📝 TOOL CALL: plan_recipe_ingredients_tool(recipe=%s)", recipe_text[:50])
            self.log.debug("Full recipe text: %s", recipe_text)
            
            try:
                result = await self.plan_recipe_ingredients(recipe_text)
                ingredients_count = len(result.get("ingredients", []))
                tool_time = time.time() - tool_start
                self.log.info("✅ TOOL SUCCESS: plan_recipe_ingredients_tool - Planned %d ingredients (took %.2fs)", 
                             ingredients_count, tool_time)
                self.log.debug("Result structure: message length=%d, ingredients count=%d, step=%s", 
                              len(result.get("message", "")), ingredients_count, result.get("step"))
                return result
            except Exception as e:
                tool_time = time.time() - tool_start
                self.log.error("❌ TOOL ERROR: plan_recipe_ingredients_tool failed after %.2fs - %s", tool_time, str(e))
                import traceback
                self.log.debug("Traceback: %s", traceback.format_exc())
                raise

        async def create_payment(ctx: RunContext, amount: Annotated[float, "Amount in INR"], order_id: Annotated[str | None, "Optional Order ID (auto-generated if not provided)"] = None):
            """Create payment intent. Order ID is auto-generated if not provided."""
            import uuid
            if not order_id:
                order_id = f"ord_{uuid.uuid4().hex[:8]}"
            self.log.info("💳 TOOL CALL: create_payment(order_id=%s, amount=₹%.2f)", order_id, amount)
            try:
                await self._ensure_payment()
                self.log.debug("Calling MCP tool: payment.init with params: %s", {"orderId": order_id, "amount": amount})
                result = await self.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
                intent = json.loads(result["content"][0]["text"])
                payment_id = intent.get("paymentId", "unknown")
                status = intent.get("status", "unknown")
                self.log.info("✅ TOOL SUCCESS: create_payment - Payment ID: %s, Status: %s", payment_id, status)
                self.log.debug("Payment intent: %s", intent)
                return intent
            except Exception as e:
                self.log.error("❌ TOOL ERROR: create_payment failed - %s", str(e))
                raise

        async def check_payment_status(ctx: RunContext, payment_id: Annotated[str, "Payment ID"]):
            self.log.info("💳 TOOL CALL: check_payment_status(payment_id=%s)", payment_id)
            try:
                await self._ensure_payment()
                self.log.debug("Calling MCP tool: payment.status with params: %s", {"paymentId": payment_id})
                result = await self.payment_client.call_tool("payment.status", {"paymentId": payment_id})
                status = json.loads(result["content"][0]["text"])
                payment_status = status.get("status", "unknown")
                self.log.info("✅ TOOL SUCCESS: check_payment_status - Status: %s", payment_status)
                if status.get("txnId"):
                    self.log.info("   Transaction ID: %s", status.get("txnId"))
                self.log.debug("Payment status: %s", status)
                
                # Auto-clear cart if payment is successful
                # Check for various success status indicators
                payment_status_lower = payment_status.lower()
                has_txn_id = bool(status.get("txnId") or status.get("txn_id"))
                is_successful = (
                    payment_status_lower in ["success", "successful", "succeeded", "completed", "paid", "settled", "done", "processed"] or
                    has_txn_id  # If there's a transaction ID, payment likely succeeded
                )
                
                if is_successful:
                    self.log.info("💳 Payment successful! (status: %s, txnId: %s) Clearing cart...", 
                                 payment_status, status.get("txnId") or status.get("txn_id") or "none")
                    try:
                        await self._ensure_blinkit()
                        clear_result = await self.blinkit_client.call_tool("blinkit.clear_cart", {})
                        cleared = json.loads(clear_result["content"][0]["text"])
                        items_removed = cleared.get("itemsRemoved", 0)
                        self.log.info("✅ Cart cleared successfully - Removed %d item(s)", items_removed)
                        status["cart_cleared"] = True
                        status["items_removed"] = items_removed
                    except Exception as clear_err:
                        self.log.error("❌ Failed to clear cart after payment: %s", str(clear_err))
                        import traceback
                        self.log.debug("Cart clear error traceback: %s", traceback.format_exc())
                        status["cart_cleared"] = False
                        status["clear_error"] = str(clear_err)
                else:
                    self.log.debug("Payment status '%s' not recognized as success - cart not cleared", payment_status)
                
                return status
            except Exception as e:
                self.log.error("❌ TOOL ERROR: check_payment_status failed - %s", str(e))
                raise

        self.agent = Agent(model=model, instructions=instructions)
        
        # Register tools
        self.agent.tool(get_product)  # Get product details by ID
        self.agent.tool(search_items)  # Search items (single or multiple) - returns results without adding
        self.agent.tool(add_items_to_cart_by_ids)  # Add items (single or multiple) to cart by IDs
        # Removed redundant tools: search_products and add_to_cart (use search_items and add_items_to_cart_by_ids instead)
        # self.agent.tool(search_and_add_items)  # Efficient combined search+add (legacy, prefer two-step flow)
        self.agent.tool(plan_recipe_ingredients_tool)  # Plan ingredients for recipe shopping flow
        self.agent.tool(view_cart)  # View cart summary
        self.agent.tool(clear_cart)  # Clear cart after payment
        self.agent.tool(create_payment)  # Create payment intent
        self.agent.tool(check_payment_status)  # Check payment status

    async def _ensure_blinkit(self):
        if self.blinkit_client is None:
            self.log.info("🔌 Initializing Blinkit MCP client...")
            try:
                self.blinkit_client = McpClient("blinkit-unified", BLINKIT_CMD, cwd=str(MCP_TOOLS_DIR), timeout=5.0)
                await self.blinkit_client.initialize()
                self.log.info("✅ Blinkit MCP client initialized successfully")
            except Exception as e:
                self.log.error("❌ Failed to initialize Blinkit MCP client: %s", str(e))
                raise

    async def _ensure_payment(self):
        if self.payment_client is None:
            self.log.info("🔌 Initializing Payment MCP client...")
            try:
                self.payment_client = McpClient("payment-unified", PAYMENT_CMD, cwd=str(MCP_TOOLS_DIR), timeout=30.0)
                await self.payment_client.initialize()
                self.log.info("✅ Payment MCP client initialized successfully")
            except Exception as e:
                self.log.error("❌ Failed to initialize Payment MCP client: %s", str(e))
                raise

    # === MCP tool wrappers ===
    async def search_products(self, query: Annotated[str, "Product name or category"], limit: Annotated[int, "Max results"] = 5):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.search", {"query": query, "limit": limit})
        return json.loads(result["content"][0]["text"])

    async def get_product(self, item_id: Annotated[str, "Product ID (e.g., blk-001)"]):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.item", {"id": item_id})
        return json.loads(result["content"][0]["text"])

    async def add_to_cart(self, item_id: Annotated[str, "Product ID"], quantity: Annotated[int, "Quantity (min 1)"] = 1):
        await self._ensure_blinkit()
        qty = max(1, quantity)
        result = await self.blinkit_client.call_tool("blinkit.add_to_cart", {"id": item_id, "quantity": qty})
        return json.loads(result["content"][0]["text"])

    async def view_cart(self):
        await self._ensure_blinkit()
        result = await self.blinkit_client.call_tool("blinkit.cart", {})
        return json.loads(result["content"][0]["text"])

    async def create_payment(self, order_id: Annotated[str, "Order ID"], amount: Annotated[float, "Amount in INR"]):
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.init", {"orderId": order_id, "amount": amount})
        return json.loads(result["content"][0]["text"])

    async def check_payment_status(self, payment_id: Annotated[str, "Payment ID"]):
        await self._ensure_payment()
        result = await self.payment_client.call_tool("payment.status", {"paymentId": payment_id})
        return json.loads(result["content"][0]["text"])

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
            cart_summary = json.loads(cart["content"][0]["text"])

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

    async def run(self, user_message: str):
        """Run agent with conversation history (last 3-4 exchanges)."""
        import time
        run_start_time = time.time()
        self.log.info("🤖 AGENT RUN: Processing user message (history: %d exchanges)", len(self.conversation_history))
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
        
        # Build context from conversation history
        # Prepend previous exchanges as context to the current message
        context_parts = []
        if self.conversation_history:
            self.log.debug("Building context from %d previous exchanges", len(self.conversation_history))
            context_parts.append("Previous conversation:")
            for i, (user_msg, assistant_msg) in enumerate(self.conversation_history[-self.max_history_exchanges:], 1):
                context_parts.append(f"\n{i}. User: {user_msg}")
                context_parts.append(f"   Assistant: {assistant_msg}")
            context_parts.append("\n\nCurrent question:")
        
        # Combine context with current message
        full_message = "".join(context_parts) + "\n" + user_message if context_parts else user_message
        
        try:
            # Run agent (without message_history to avoid format issues)
            self.log.debug("Sending request to agent model...")
            agent_start = time.time()
            resp = await self.agent.run(full_message)
            agent_run_time = time.time() - agent_start
            assistant_response = getattr(resp, "output", resp.output)
            
            # Check if tools were used and log timing breakdown
            tool_call_times = []
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
            
            elapsed = time.time() - run_start_time
            self.log.info("✅ AGENT SUCCESS: Response generated (length: %d chars)", len(str(assistant_response)))
            self.log.info("⏱️  AGENT TIMING: Total=%.2fs | Agent.run()=%.2fs | Overhead=%.2fs", 
                         elapsed, agent_run_time, elapsed - agent_run_time)
            self.log.debug("Agent response: %s", str(assistant_response)[:200] + "..." if len(str(assistant_response)) > 200 else str(assistant_response))
            
            # Store this exchange
            self.conversation_history.append((user_message, str(assistant_response)))
            
            # Keep only last max_history_exchanges exchanges
            if len(self.conversation_history) > self.max_history_exchanges:
                removed = len(self.conversation_history) - self.max_history_exchanges
                self.conversation_history = self.conversation_history[-self.max_history_exchanges:]
                self.log.debug("Trimmed conversation history: removed %d old exchange(s)", removed)
            
            return assistant_response
        except Exception as e:
            self.log.error("❌ AGENT ERROR: Failed to process user message - %s", str(e))
            raise

    def clear_history(self):
        """Clear conversation history."""
        count = len(self.conversation_history)
        self.conversation_history = []
        self.log.info("🗑️  Cleared conversation history (%d exchanges removed)", count)

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
