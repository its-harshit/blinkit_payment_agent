"""Hybrid NPCI info + commerce agent that only calls tools for shopping/payment."""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic import BaseModel, Field

try:
    from .mcp_client import McpClient
except ImportError:
    from mcp_client import McpClient


MCP_TOOLS_DIR = Path(__file__).parent
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]

DEFAULT_MODEL = OpenAIChatModel(
    model_name="npci",
    provider=OpenAIProvider(base_url="http://183.82.7.228:9535/v1", api_key="dummy"),
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
            "You are an NPCI CUSTOMER SUPPORT BOT which also has some generic worldly information, u also have the capabilities to be a payment shopping assistant.\n"
            "- Your primary role is NPCI customer support. You help users with UPI payment queries, grievances, and general information.\n"
            "- You also have access to shopping tools that can help users find and purchase items, but you are NOT affiliated with any specific shopping platform.\n"
            "- Default behavior: answer user queries clearly and concisely. "
            "If you don't have specific case data, provide general guidance (e.g., collect UPI txn ID, VPA, time, bank). "
            "- Only invoke shopping/Payment tools when the user explicitly wants to search products, view items, add to cart, "
            "or pay. Otherwise, just reply normally.\n"
            "- IMPORTANT: Never mention that you work for Blinkit or any specific shopping company. You are an NPCI support agent with shopping capabilities.\n"
            "\n"
            "**RECIPE SHOPPING FLOW (when user asks to buy items for a dish/recipe):**\n"
            "1. When user asks to buy items for a recipe (e.g., 'buy items for biryani', 'get ingredients for dosa'), "
            "FIRST plan the ingredients using the plan_recipe_ingredients_tool with the recipe/dish name. This will return a plan with ingredient names.\n"
            "2. Display the ingredient list from the plan result to the user, then STOP and ask: 'Would you like me to help you find and purchase these items?' Wait for user confirmation.\n"
            "3. If user confirms (says 'yes', 'proceed', 'go ahead', 'buy them'), extract the ingredient NAMES from the plan result (the 'ingredients' array, use the 'name' field of each ingredient). "
            "Then use search_items_for_cart tool with a list of those ingredient names (as strings) to search for them.\n"
            "4. After search_items_for_cart completes, the tool returns a dict with 'found_items' array and 'skipped' list. "
            "Display the found items in a formatted table showing: item name, price, quantity, and total from the 'found_items' array. "
            "Also mention any items that were not found (from the 'skipped' list). Then STOP and ask: 'Would you like me to add these items to your cart?' Wait for user confirmation.\n"
            "5. If user confirms adding to cart (says 'yes', 'add them', 'proceed'), you MUST use the EXACT 'found_items' array from the search_items_for_cart tool result. "
            "The search_items_for_cart result is a dict like: {'found_items': [{'id': 'blk-101', 'name': 'Chicken', 'price': 320, 'quantity': 1}, ...], 'skipped': [...]}. "
            "Extract the 'found_items' array and pass it DIRECTLY to add_items_to_cart_by_ids. "
            "DO NOT create new items, DO NOT use placeholder IDs like 'blk-001', 'blk-002'. Use ONLY the actual IDs from 'found_items'.\n"
            "6. After add_items_to_cart_by_ids completes, show the cart summary from the result and STOP. Ask: 'Would you like to add more items or proceed to checkout?'\n"
            "7. If user says 'proceed to checkout', 'checkout', 'pay', 'proceed to payment', or similar, first call view_cart to get the cart total, then use create_payment with the amount (order_id is optional, will be auto-generated), then immediately call check_payment_status with the payment_id from create_payment result to complete the transaction.\n"
            "8. If user wants to add more items, let them specify the item names and use search_items_for_cart again, then add_items_to_cart_by_ids after confirmation.\n"
            "\n"
            "- IMPORTANT: Always wait for user confirmation before proceeding to the next step in recipe shopping flow.\n"
            "- IMPORTANT: After searching items, show results and get confirmation BEFORE adding to cart.\n"
            "- IMPORTANT: After adding items to cart, always show cart summary before asking about checkout.\n"
            "- IMPORTANT: When user confirms checkout/payment, process payment directly without asking again.\n"
            "- After successful payment (when check_payment_status returns success/completed), the cart is automatically cleared. "
            "You don't need to manually clear it.\n"
            "- PREFERRED FLOW: For multiple items, use search_items_for_cart first (to show results), then add_items_to_cart_by_ids after user confirms. "
            "This gives better UX as user can review items before adding to cart.\n"
            "- When adding a single item to cart (if you already have the item ID), use add_to_cart tool.\n"
            "- When planning ingredients, prefer only 6-7 most basic common ingredients available in raw form at Blinkit(Indian supermarkets/grocery stores). Avoid exotic or hard-to-find items or ultra processed things which might be hard to exactly find; suggest nearest simple substitutes.\n"
            "- For single item searches (without adding to cart), use search_products tool.\n"
        )

        self.blinkit_client: McpClient | None = None
        self.payment_client: McpClient | None = None
        self.conversation_history: list[tuple[str, str]] = []  # Store (user_msg, assistant_msg) pairs
        self.max_history_exchanges = 4  # Keep last 3-4 exchanges
        # lightweight planner for ingredient extraction
        class IngredientItem(BaseModel):
            name: str = Field(description="Ingredient name")
            quantity: str | None = Field(description="Human-friendly quantity, e.g., '2 cups'")
            optional: bool = Field(default=False, description="Whether the ingredient can be skipped")
        self.IngredientItem = IngredientItem
        self.plan_agent = Agent(
            model=model,
            output_type=list[IngredientItem],  # type: ignore[arg-type]
            instructions=(
                "You are a recipe ingredient planner. Your task is to plan ALL essential ingredients needed to make a given dish.\n"
                "\n"
                "CRITICAL: Do NOT just extract words from the input. You must PLAN the complete ingredient list for the recipe.\n"
                "\n"
                "Examples:\n"
                "- Input: 'egg biryani' → Output: [basmati rice, eggs, onion, tomato, yogurt, ginger-garlic paste, green chili, turmeric powder, red chili powder, garam masala, ghee, salt, mint leaves, coriander leaves]\n"
                "- Input: 'dosa' → Output: [rice, urad dal, fenugreek seeds, salt, oil]\n"
                "- Input: 'chole bhature' → Output: [kabuli chana, onion, tomato, chole masala, garam masala, maida, yogurt, salt, oil]\n"
                "\n"
                "Return 6-7 most essential ingredients. Each ingredient should have:\n"
                "- name: simple, commonly available name (e.g., 'onion', 'basmati rice', 'eggs', 'turmeric powder')\n"
                "- quantity: human-friendly quantity if relevant (e.g., '2 cups', '1 kg', '6 pieces') or None\n"
                "- optional: true only if ingredient can be skipped, false otherwise\n"
                "\n"
                "Prefer ingredients commonly available in raw form on Indian supermarkets. Avoid exotic or hard-to-find items."
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

        async def search_items_for_cart(ctx: RunContext, item_names: Annotated[list[str], "List of item names to search"], quantities: Annotated[list[int] | None, "Optional list of quantities (defaults to 1 for each)"] = None):
            """Search for multiple items and return results (without adding to cart). 
            
            Use this to search items first, show results to user, then ask for confirmation before adding.
            Returns a dict with 'found_items' array. Each item in 'found_items' has: {'id': 'blk-xxx', 'name': '...', 'price': N, 'quantity': N, 'original_name': '...'}
            IMPORTANT: When user confirms, pass the ENTIRE 'found_items' array directly to add_items_to_cart_by_ids. Do not modify or recreate the items.
            Uses the same fast sequential search method as _pick_and_add.
            """
            import time
            start_time = time.time()
            self.log.info("🔍 TOOL CALL: search_items_for_cart(%d items)", len(item_names))
            try:
                await self._ensure_blinkit()
                
                found_items = []
                skipped = []
                
                # Search each item sequentially (like _pick_and_add) - faster than parallel chunking
                for idx, item_name in enumerate(item_names):
                    name = item_name.strip()
                    queries = [name]
                    key = name.lower()
                    if key in self.search_aliases:
                        queries.extend(self.search_aliases[key])
                    
                    items = []
                    tried = []
                    for q in queries:
                        self.log.info("Searching Blinkit for: %s", q)
                        tried.append(q)
                        resp = await self.blinkit_client.call_tool("blinkit.search", {"query": q, "limit": 3})
                        found = json.loads(resp["content"][0]["text"])
                        if found:
                            items = found
                            break
                    
                    if not items:
                        self.log.warning("No results for item after tries %s", tried)
                        skipped.append(name)
                        continue
                    
                    choice = items[0]
                    qty = quantities[idx] if quantities and idx < len(quantities) else 1
                    qty = max(1, qty)
                    # Clamp to stock and sensible upper bound
                    stock = choice.get("stock", qty)
                    qty = min(qty, stock, 5)
                    
                    found_items.append({
                        "id": choice["id"],
                        "name": choice.get("name"),
                        "price": choice.get("price", 0),
                        "quantity": qty,
                        "original_name": name
                    })
                    self.log.info("Found: %s x%d (%s)", choice.get("name"), qty, choice.get("id"))
                
                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: search_items_for_cart - %d found, %d skipped (took %.2fs)",
                             len(found_items), len(skipped), elapsed)
                
                return {
                    "found_items": found_items,
                    "skipped": skipped,
                    "time_taken": elapsed
                }
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_items_for_cart failed after %.2fs - %s", elapsed, str(e))
                raise

        async def add_items_to_cart_by_ids(ctx: RunContext, items: Annotated[list[dict], "List of items to add, each with 'id' and 'quantity'. IMPORTANT: Use the exact 'found_items' array from search_items_for_cart result, do not create new items."]):
            """Add multiple items to cart by their IDs (after user confirms search results).
            
            Use this after search_items_for_cart when user confirms they want to add items.
            CRITICAL: Pass the EXACT 'found_items' array from the search_items_for_cart result. 
            Each item should have: {'id': 'blk-xxx', 'quantity': N, 'name': '...', 'price': ...}
            Do NOT create new items or use placeholder IDs. Use the exact IDs from the search result.
            Uses the same fast sequential method as _pick_and_add.
            """
            import time
            start_time = time.time()
            self.log.info("🛒 TOOL CALL: add_items_to_cart_by_ids(%d items)", len(items))
            
            # Log what we received for debugging
            received_ids = [item.get("id", "NO_ID") for item in items]
            self.log.info("📋 Received items with IDs: %s", received_ids)
            self.log.debug("Full received items: %s", items)
            
            try:
                await self._ensure_blinkit()
                
                successful = []
                failed = []
                
                # Add items sequentially (like _pick_and_add) - faster and more reliable
                for item in items:
                    item_id = item.get("id")
                    quantity = max(1, item.get("quantity", 1))
                    item_name = item.get("name", "Unknown")
                    
                    # Validate that we have a proper ID
                    if not item_id or not item_id.startswith("blk-"):
                        self.log.error("❌ Invalid item ID: %s. Item: %s", item_id, item)
                        failed.append({"item": item, "error": f"Invalid ID: {item_id}"})
                        continue
                    
                    try:
                        added = await self.blinkit_client.call_tool(
                            "blinkit.add_to_cart", {"id": item_id, "quantity": quantity}
                        )
                        entry = json.loads(added["content"][0]["text"])
                        added_item_name = entry.get("item", {}).get("name", item_id)
                        self.log.info("✅ Added: %s x%d (%s)", added_item_name, entry.get("quantity", quantity), item_id)
                        successful.append(entry)
                    except Exception as e:
                        self.log.warning("Failed to add item %s: %s", item_id, str(e))
                        failed.append({"item": {"id": item_id, "quantity": quantity}, "error": str(e)})

                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: add_items_to_cart_by_ids - %d succeeded, %d failed (took %.2fs)",
                             len(successful), len(failed), elapsed)

                # Get cart summary
                cart_res = await self.blinkit_client.call_tool("blinkit.cart", {})
                cart = json.loads(cart_res["content"][0]["text"])

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
                raise

        async def search_and_add_items(ctx: RunContext, item_names: Annotated[list[str], "List of item names to search and add to cart"], quantities: Annotated[list[int] | None, "Optional list of quantities (defaults to 1 for each)"] = None):
            """Search for multiple items and add them to cart in one efficient flow (similar to plan_and_shop).
            
            This tool searches all items in parallel, maps results, and adds them to cart in parallel.
            Much faster than calling search_products and add_to_cart separately.
            NOTE: For better UX, prefer using search_items_for_cart first, then add_items_to_cart_by_ids after user confirmation.
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
            After showing the plan, ask user if they want to buy these items from Blinkit.
            """
            self.log.info("📝 TOOL CALL: plan_recipe_ingredients_tool(recipe=%s)", recipe_text[:50])
            try:
                result = await self.plan_recipe_ingredients(recipe_text)
                self.log.info("✅ TOOL SUCCESS: plan_recipe_ingredients_tool - Planned %d ingredients", len(result.get("ingredients", [])))
                return result
            except Exception as e:
                self.log.error("❌ TOOL ERROR: plan_recipe_ingredients_tool failed - %s", str(e))
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
                payment_status_lower = payment_status.lower()
                if payment_status_lower in ["success", "successful", "completed", "paid", "settled"]:
                    self.log.info("💳 Payment successful! Clearing cart...")
                    try:
                        await self._ensure_blinkit()
                        clear_result = await self.blinkit_client.call_tool("blinkit.clear_cart", {})
                        cleared = json.loads(clear_result["content"][0]["text"])
                        items_removed = cleared.get("itemsRemoved", 0)
                        self.log.info("✅ Cart cleared successfully - Removed %d item(s)", items_removed)
                        status["cart_cleared"] = True
                        status["items_removed"] = items_removed
                    except Exception as clear_err:
                        self.log.warning("⚠️  Failed to clear cart after payment: %s", str(clear_err))
                        status["cart_cleared"] = False
                        status["clear_error"] = str(clear_err)
                
                return status
            except Exception as e:
                self.log.error("❌ TOOL ERROR: check_payment_status failed - %s", str(e))
                raise

        self.agent = Agent(model=model, instructions=instructions)
        
        # Register tools
        self.agent.tool(search_products)  # Single item search
        self.agent.tool(get_product)  # Get product details by ID
        self.agent.tool(add_to_cart)  # Add single item to cart by ID
        self.agent.tool(search_items_for_cart)  # Search multiple items (returns results, doesn't add)
        self.agent.tool(add_items_to_cart_by_ids)  # Add items to cart by IDs (after user confirms)
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
                self.blinkit_client = McpClient("blinkit-unified", BLINKIT_CMD, cwd=str(MCP_TOOLS_DIR), timeout=30.0)
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

    async def build_cart_for_plan(self, ingredients: list) -> dict:
        """Attempt to add each ingredient to the Blinkit cart."""
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
        
        plan_result = await self.plan_agent.run(text)
        ingredients: list = getattr(plan_result, "output", plan_result.output)
        plan_time = time.time() - plan_start_time
        self.log.info("📝 Got %d ingredients (took %.2fs)", len(ingredients), plan_time)
        
        # Log all ingredients for debugging
        for idx, ing in enumerate(ingredients, 1):
            self.log.debug("  %d. %s (qty: %s, optional: %s)", idx, ing.name, ing.quantity or "N/A", ing.optional)
        
        # Warn if we got very few ingredients (might indicate planning issue)
        if len(ingredients) < 3:
            self.log.warning("⚠️  Only got %d ingredients - this might be incomplete. Expected 6-7 for a typical recipe.", len(ingredients))
        
        # Format plan for user
        response_parts = []
        response_parts.append("📋 **Here are the ingredients needed:**\n\n")
        for idx, ing in enumerate(ingredients, 1):
            qty_str = f" ({ing.quantity})" if ing.quantity else ""
            opt_str = " (optional)" if ing.optional else ""
            response_parts.append(f"{idx}. **{ing.name}**{qty_str}{opt_str}\n")
        
        response_parts.append("\n🛒 **Would you like me to help you find and purchase these items from Blinkit?**\n")
        response_parts.append("Just say 'yes' or 'proceed' and I'll search for them and add to your cart!\n")
        
        formatted_response = "".join(response_parts)
        
        return {
            "message": formatted_response,
            "ingredients": [ing.model_dump() for ing in ingredients],
            "step": "plan_complete"  # Indicates we're waiting for user confirmation
        }

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
        
        response_parts.append("\n💳 **Next steps:**\n")
        response_parts.append("  Would you like to proceed to checkout and payment? Just say 'yes' or 'proceed to payment' and I'll help you complete the transaction!\n")

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
            resp = await self.agent.run(full_message)
            assistant_response = getattr(resp, "output", resp.output)
            
            # Check if tools were used
            if hasattr(resp, 'all_messages'):
                messages = resp.all_messages()
                tool_calls = [msg for msg in messages if hasattr(msg, 'tool_calls') and msg.tool_calls]
                if tool_calls:
                    self.log.info("🔧 Agent used %d tool call(s) in this run", len(tool_calls))
            
            elapsed = time.time() - run_start_time
            self.log.info("✅ AGENT SUCCESS: Response generated (length: %d chars, total time: %.2fs)", 
                         len(str(assistant_response)), elapsed)
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
