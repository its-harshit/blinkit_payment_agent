"""Hybrid NPCI info + commerce agent that only calls tools for shopping/payment - LangChain version."""
import asyncio
import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, List, Optional

from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field

try:
    from .mcp_client import McpClient
except ImportError:
    from mcp_client import McpClient


MCP_TOOLS_DIR = Path(__file__).parent
BLINKIT_CMD = ["node", "dist/blinkit-server.js"]
PAYMENT_CMD = ["node", "dist/payment-server.js"]

DEFAULT_MODEL = ChatOpenAI(
    model="NPCI_Greviance",
    base_url="http://183.82.7.228:9519/v1",
    api_key="dummy",
    temperature=0,
)


class IngredientItem(BaseModel):
    """Single ingredient item for recipe planning."""
    name: str = Field(description="Ingredient name")
    quantity: Optional[str] = Field(default=None, description="Human-friendly quantity, e.g., '2 cups'")
    optional: bool = Field(default=False, description="Whether the ingredient can be skipped")


class IngredientList(BaseModel):
    """List of ingredients for recipe planning."""
    ingredients: List[IngredientItem] = Field(description="List of ingredients needed for the recipe")


class UnifiedAgent:
    """Answers NPCI grievance FAQs by default, but uses MCP tools for shopping/checkout."""

    def __init__(self, model=None, log_level=logging.INFO):
        if model is None:
            model = DEFAULT_MODEL
        self.model = model
        # Store model for plan_agent compatibility
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
            "The search_items_for_cart result is a dict like: {{'found_items': [{{'id': 'blk-101', 'name': 'Chicken', 'price': 320, 'quantity': 1}}, ...], 'skipped': [...]}}. "
            "Display the found items in a formatted table showing: item name, price, quantity, and total from the 'found_items' array. "
            "Also mention any items that were not found (from the 'skipped' list). Then STOP and ask: 'Would you like me to add these items to your cart?' Wait for user confirmation.\n"
            "5. If user confirms adding to cart (says 'yes', 'add them', 'proceed'), use add_items_to_cart_by_ids with the items from the search results. "
            "You can use the 'found_items' array from the search_items_for_cart result, or construct items with the IDs and quantities from the search results. "
            "Each item should have at least 'id' (like 'blk-101') and 'quantity' fields. Use the actual item IDs from the search results, not placeholder IDs.\n"
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

        self.blinkit_client: Optional[McpClient] = None
        self.payment_client: Optional[McpClient] = None
        self.conversation_history: List[tuple[str, str]] = []  # Store (user_msg, assistant_msg) pairs
        self.max_history_exchanges = 4  # Keep last 3-4 exchanges
        
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

        # Create tools - these need to be methods that can access self
        tools = self._create_tools()
        
        # Create prompt template
        # Note: Using a simpler template that works with custom model endpoints
        prompt = ChatPromptTemplate.from_messages([
            ("system", instructions),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent - use ReAct agent as custom endpoint may not support OpenAI tools format
        # ReAct agent uses text-based tool invocation instead of function calling
        from langchain import hub
        try:
            react_prompt = hub.pull("hwchase17/react")
        except Exception:
            # If hub pull fails, create a simple ReAct prompt
            react_prompt = ChatPromptTemplate.from_messages([
                ("system", "You are a helpful assistant. Use the following tools to answer questions.\n\nTools:\n{tools}\n\nTool names: {tool_names}"),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])
        
        agent = create_react_agent(self.model, tools, react_prompt)
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=15,
        )
        
        # Create plan agent for recipe planning (with structured output)
        plan_instructions = (
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
        )
        
        # Use structured output for plan agent
        # Request JSON format from the model
        self.plan_prompt = ChatPromptTemplate.from_messages([
            ("system", plan_instructions + "\n\nIMPORTANT: You must return ONLY a valid JSON object with this exact structure:\n"
                     '{{"ingredients": [{{"name": "ingredient name", "quantity": "optional quantity string or null", "optional": false}}, ...]}}\n'
                     "Do not include any other text, explanations, or markdown formatting. Only the JSON object."),
            ("human", "{input}"),
        ])

    def _create_tools(self):
        """Create LangChain tools that can access self."""
        tools = []
        
        # Helper to create async tool
        def make_tool(name, description, func):
            return StructuredTool.from_function(
                name=name,
                description=description,
                func=func,
                coroutine=func,
            )
        
        # search_products
        async def search_products(query: str, limit: int = 5) -> str:
            start_time = time.time()
            self.log.info("🔍 TOOL CALL: search_products(query=%s, limit=%d)", query, limit)
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.search with params: %s", {"query": query, "limit": limit})
                result = await self.blinkit_client.call_tool("blinkit.search", {"query": query, "limit": limit})
                items = json.loads(result["content"][0]["text"])
                elapsed = time.time() - start_time
                self.log.info("✅ TOOL SUCCESS: search_products found %d items (took %.2fs)", len(items), elapsed)
                self.log.debug("Search results: %s", items[:2] if len(items) > 2 else items)
                return json.dumps(items)
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_products failed after %.2fs - %s", elapsed, str(e))
                raise
        
        tools.append(make_tool(
            "search_products",
            "Search for products by name or category. Returns a JSON array of product items.",
            search_products
        ))
        
        # get_product
        async def get_product(item_id: str) -> str:
            self.log.info("🔍 TOOL CALL: get_product(item_id=%s)", item_id)
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.item with params: %s", {"id": item_id})
                result = await self.blinkit_client.call_tool("blinkit.item", {"id": item_id})
                item = json.loads(result["content"][0]["text"])
                self.log.info("✅ TOOL SUCCESS: get_product retrieved item: %s", item.get("name", item_id))
                self.log.debug("Product details: %s", item)
                return json.dumps(item)
            except Exception as e:
                self.log.error("❌ TOOL ERROR: get_product failed - %s", str(e))
                raise
        
        tools.append(make_tool(
            "get_product",
            "Get product details by product ID (e.g., 'blk-001'). Returns a JSON object with product information.",
            get_product
        ))
        
        # add_to_cart
        async def add_to_cart(item_id: str, quantity: int = 1) -> str:
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
                return json.dumps(entry)
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: add_to_cart failed after %.2fs - %s", elapsed, str(e))
                raise
        
        tools.append(make_tool(
            "add_to_cart",
            "Add a single item to cart by product ID. Returns a JSON object with the cart entry.",
            add_to_cart
        ))
        
        # search_items_for_cart
        async def search_items_for_cart(item_names: str, quantities: Optional[str] = None) -> str:
            """Search for multiple items and return results (without adding to cart)."""
            start_time = time.time()
            
            # Helper function to clean and parse JSON from ReAct agent input
            def parse_json_input(input_str: str):
                """Parse JSON input, handling markdown code fences and various formats."""
                if not isinstance(input_str, str):
                    return input_str
                
                # Strip markdown code fences if present
                cleaned = input_str.strip()
                
                # Handle triple backticks (```json ... ```)
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()
                # Handle single backticks (`...`)
                elif cleaned.startswith("`") and cleaned.endswith("`"):
                    cleaned = cleaned[1:-1].strip()
                
                # Try to parse as JSON
                try:
                    parsed = json.loads(cleaned)
                    return parsed
                except json.JSONDecodeError:
                    # If not valid JSON, return original string
                    return cleaned
            
            # Parse input - LangChain ReAct agent may pass JSON object or separate parameters
            try:
                # First, try to parse item_names as a JSON object that might contain both item_names and quantities
                self.log.debug("Raw item_names input: %s", repr(item_names[:200] if len(str(item_names)) > 200 else item_names))
                parsed_input = parse_json_input(item_names)
                self.log.debug("Parsed input type: %s, value: %s", type(parsed_input).__name__, str(parsed_input)[:200] if len(str(parsed_input)) > 200 else str(parsed_input))
                
                if isinstance(parsed_input, dict):
                    # If it's a JSON object, extract item_names and quantities
                    item_names_list = parsed_input.get("item_names", [])
                    if not isinstance(item_names_list, list):
                        item_names_list = [item_names_list] if item_names_list else []
                    
                    # Also check for quantities in the same object
                    if quantities is None and "quantities" in parsed_input:
                        quantities = parsed_input.get("quantities")
                        self.log.debug("Extracted quantities from JSON object: %s", quantities)
                elif isinstance(parsed_input, list):
                    # If it's a JSON array, use it directly
                    item_names_list = parsed_input
                else:
                    # Try to parse as JSON array string
                    try:
                        item_names_list = json.loads(str(parsed_input))
                        if not isinstance(item_names_list, list):
                            item_names_list = [item_names_list]
                    except (json.JSONDecodeError, TypeError):
                        # Fallback: try comma-separated or single value
                        item_names_str = str(parsed_input)
                        if "," in item_names_str:
                            item_names_list = [n.strip() for n in item_names_str.split(",")]
                        else:
                            item_names_list = [item_names_str.strip()]
            except Exception as e:
                self.log.warning("Failed to parse item_names, using as single item: %s", str(e))
                item_names_list = [str(item_names)]
            
            # Parse quantities
            quantities_list = None
            if quantities:
                try:
                    parsed_quantities = parse_json_input(quantities)
                    
                    if isinstance(parsed_quantities, list):
                        quantities_list = parsed_quantities
                    elif isinstance(parsed_quantities, (int, float, str)):
                        # Single value - try to convert to int, but keep as string if it has units
                        try:
                            # If it's a number, convert to int
                            if isinstance(parsed_quantities, (int, float)):
                                quantities_list = [int(parsed_quantities)]
                            else:
                                # If it's a string with units (e.g., "2 cups"), keep as string
                                quantities_list = [parsed_quantities]
                        except (ValueError, TypeError):
                            quantities_list = [str(parsed_quantities)]
                    else:
                        # Try JSON parsing
                        try:
                            quantities_list = json.loads(str(parsed_quantities))
                            if not isinstance(quantities_list, list):
                                quantities_list = [quantities_list]
                        except (json.JSONDecodeError, TypeError):
                            # Fallback: comma-separated
                            if "," in str(parsed_quantities):
                                quantities_list = [q.strip() for q in str(parsed_quantities).split(",")]
                            else:
                                quantities_list = [str(parsed_quantities).strip()]
                except Exception as e:
                    self.log.warning("Failed to parse quantities: %s", str(e))
                    quantities_list = None
            
            self.log.info("🔍 TOOL CALL: search_items_for_cart(%d items)", len(item_names_list))
            self.log.debug("Item names: %s", item_names_list)
            self.log.debug("Quantities: %s", quantities_list)
            
            try:
                await self._ensure_blinkit()
                
                found_items = []
                skipped = []
                
                # Search each item sequentially (like _pick_and_add) - faster than parallel chunking
                for idx, item_name in enumerate(item_names_list):
                    self.log.debug("Processing item %d/%d: %s", idx + 1, len(item_names_list), item_name)
                    name = str(item_name).strip()
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
                    original_qty_str = quantities_list[idx] if quantities_list and idx < len(quantities_list) else "1"
                    
                    # Convert quantity string to int for cart operations
                    # Handle strings like "2 cups", "1 kg" by extracting the number
                    original_qty = self._quantity_to_int(original_qty_str) if isinstance(original_qty_str, str) else (int(original_qty_str) if original_qty_str else 1)
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
                self.log.info("✅ TOOL SUCCESS: search_items_for_cart - %d found, %d skipped (took %.2fs)",
                             len(found_items), len(skipped), elapsed)
                self.log.debug("Found items summary: %s", [{"id": item["id"], "name": item["name"], "qty": item["quantity"]} for item in found_items])
                if skipped:
                    self.log.debug("Skipped items: %s", skipped)
                
                return json.dumps({
                    "found_items": found_items,
                    "skipped": skipped,
                    "time_taken": elapsed
                })
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: search_items_for_cart failed after %.2fs - %s", elapsed, str(e))
                raise
        
        tools.append(make_tool(
            "search_items_for_cart",
            "Search for multiple items by name and return results without adding to cart. Takes a JSON array of item names and optional quantities. Returns a JSON object with 'found_items' array and 'skipped' list.",
            search_items_for_cart
        ))
        
        # add_items_to_cart_by_ids
        async def add_items_to_cart_by_ids(items: str) -> str:
            """Add multiple items to cart by their IDs (after user confirms search results).
            
            Use this after search_items_for_cart when user confirms they want to add items.
            Each item should be a dict with:
            - 'id' (required): Product ID from search results (e.g., 'blk-101', 'blk-029')
            - 'quantity' (required): Number of items to add (defaults to 1 if not provided)
            - 'name' (optional): Item name for reference
            - 'price' (optional): Item price for reference
            
            You can pass the 'found_items' array from search_items_for_cart, or construct items using the IDs from the search results.
            Uses sequential processing for reliability.
            """
            import time
            start_time = time.time()
            
            # Helper function to clean and parse JSON from ReAct agent input
            def parse_json_input(input_str: str):
                """Parse JSON input, handling markdown code fences and various formats."""
                if not isinstance(input_str, str):
                    return input_str
                
                # Strip markdown code fences if present
                cleaned = input_str.strip()
                
                # Handle triple backticks (```json ... ```)
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()
                # Handle single backticks (`...`)
                elif cleaned.startswith("`") and cleaned.endswith("`"):
                    cleaned = cleaned[1:-1].strip()
                
                # Try to parse as JSON
                try:
                    parsed = json.loads(cleaned)
                    return parsed
                except json.JSONDecodeError:
                    # If not valid JSON, return original string
                    return cleaned
            
            # Parse JSON input
            try:
                self.log.debug("Raw items input: %s", repr(items[:200] if len(str(items)) > 200 else items))
                parsed_input = parse_json_input(items)
                self.log.debug("Parsed input type: %s", type(parsed_input).__name__)
                
                if isinstance(parsed_input, list):
                    items_list = parsed_input
                elif isinstance(parsed_input, dict):
                    # If it's a dict, try to extract a list from common keys
                    items_list = parsed_input.get("items", parsed_input.get("found_items", [parsed_input]))
                else:
                    # Try to parse as JSON string
                    items_list = json.loads(str(parsed_input)) if isinstance(parsed_input, str) else parsed_input
            except Exception as e:
                self.log.error("❌ Failed to parse items JSON: %s", items)
                self.log.debug("Parse error: %s", str(e))
                raise ValueError(f"Invalid items format: {items}")
            
            self.log.info("🛒 TOOL CALL: add_items_to_cart_by_ids(%d items)", len(items_list))
            
            # Log what we received for debugging
            received_ids = [item.get("id", "NO_ID") if isinstance(item, dict) else "NO_ID" for item in items_list]
            self.log.info("📋 Received items with IDs: %s", received_ids)
            self.log.debug("Full received items structure: %s", items_list)
            
            # Validate structure
            for idx, item in enumerate(items_list):
                if not isinstance(item, dict):
                    self.log.warning("⚠️  Item %d is not a dict: %s", idx, type(item))
                elif "id" not in item:
                    self.log.warning("⚠️  Item %d missing 'id' field: %s", idx, item)
            
            try:
                await self._ensure_blinkit()
                
                successful = []
                failed = []
                
                self.log.debug("Starting sequential add process for %d items", len(items_list))
                self.log.info("⏱️  Starting to add %d items to cart (sequential mode)", len(items_list))
                
                # Track timing for each item
                item_timings = []
                
                # Add items sequentially (like _pick_and_add) - faster and more reliable
                for idx, item in enumerate(items_list):
                    item_start = time.time()
                    self.log.debug("Processing item %d/%d: %s", idx + 1, len(items_list), item)
                    item_id = item.get("id") if isinstance(item, dict) else None
                    original_quantity = item.get("quantity", 1) if isinstance(item, dict) else 1
                    quantity = max(1, int(original_quantity) if isinstance(original_quantity, (int, float, str)) else 1)
                    item_name = item.get("name", "Unknown") if isinstance(item, dict) else "Unknown"
                    item_price = item.get("price", 0) if isinstance(item, dict) else 0
                    
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
                
                return json.dumps({
                    "successful": successful,
                    "failed": failed,
                    "successful_items": [{"name": r.get("item", {}).get("name"), "quantity": r.get("quantity")} for r in successful],
                    "failed_items": failed,
                    "cart": cart,
                    "time_taken": elapsed
                })
            except Exception as e:
                elapsed = time.time() - start_time
                self.log.error("❌ TOOL ERROR: add_items_to_cart_by_ids failed after %.2fs - %s", elapsed, str(e))
                import traceback
                self.log.debug("Traceback: %s", traceback.format_exc())
                raise
        
        tools.append(make_tool(
            "add_items_to_cart_by_ids",
            "Add multiple items to cart by their IDs. Takes a JSON array of items, each with 'id' and 'quantity' fields. Returns a JSON object with results and cart summary.",
            add_items_to_cart_by_ids
        ))
        
        # view_cart
        async def view_cart() -> str:
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
                return json.dumps(cart)
            except Exception as e:
                self.log.error("❌ TOOL ERROR: view_cart failed - %s", str(e))
                raise
        
        tools.append(make_tool(
            "view_cart",
            "View the current cart contents. Returns a JSON object with cart items and total.",
            view_cart
        ))
        
        # clear_cart
        async def clear_cart() -> str:
            self.log.info("🗑️  TOOL CALL: clear_cart()")
            try:
                await self._ensure_blinkit()
                self.log.debug("Calling MCP tool: blinkit.clear_cart")
                result = await self.blinkit_client.call_tool("blinkit.clear_cart", {})
                cleared = json.loads(result["content"][0]["text"])
                items_removed = cleared.get("itemsRemoved", 0)
                self.log.info("✅ TOOL SUCCESS: clear_cart - Removed %d item(s) from cart", items_removed)
                self.log.debug("Clear cart result: %s", cleared)
                return json.dumps(cleared)
            except Exception as e:
                self.log.error("❌ TOOL ERROR: clear_cart failed - %s", str(e))
                raise
        
        tools.append(make_tool(
            "clear_cart",
            "Clear all items from the cart. Returns a JSON object with the number of items removed.",
            clear_cart
        ))
        
        # plan_recipe_ingredients_tool
        async def plan_recipe_ingredients_tool(recipe_text: str) -> str:
            """Plan ingredients needed for a recipe. Returns the ingredient list and asks user to confirm before buying.
            
            Use this tool when user asks to buy items for a recipe/dish. This is step 1 - it only plans, doesn't add to cart.
            After showing the plan, ask user if they want to buy these items from Blinkit.
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
                return json.dumps(result)
            except Exception as e:
                tool_time = time.time() - tool_start
                self.log.error("❌ TOOL ERROR: plan_recipe_ingredients_tool failed after %.2fs - %s", tool_time, str(e))
                import traceback
                self.log.debug("Traceback: %s", traceback.format_exc())
                raise
        
        tools.append(make_tool(
            "plan_recipe_ingredients_tool",
            "Plan ingredients needed for a recipe or dish. Takes a recipe/dish name and returns a JSON object with ingredient list and formatted message.",
            plan_recipe_ingredients_tool
        ))
        
        # create_payment
        async def _create_payment_impl(amount: float, order_id: Optional[str] = None) -> str:
            """Internal implementation of create_payment."""
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
                return json.dumps(intent)
            except Exception as e:
                self.log.error("❌ TOOL ERROR: create_payment failed - %s", str(e))
                raise
        
        async def create_payment(amount: str, order_id: Optional[str] = None) -> str:
            """Create payment intent. Accepts amount as JSON string or float."""
            # Helper to parse JSON input
            def parse_json_input(input_str):
                if not isinstance(input_str, str):
                    return input_str
                cleaned = input_str.strip()
                
                # Handle triple backticks (```json ... ```)
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned = "\n".join(lines).strip()
                # Handle single backticks (`...`)
                elif cleaned.startswith("`") and cleaned.endswith("`"):
                    cleaned = cleaned[1:-1].strip()
                
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return cleaned
            
            # Parse amount - could be JSON string or direct value
            try:
                parsed_amount = parse_json_input(amount)
                if isinstance(parsed_amount, dict):
                    # If it's a JSON object, extract amount and order_id
                    actual_amount = parsed_amount.get("amount")
                    if order_id is None and "order_id" in parsed_amount:
                        order_id = parsed_amount.get("order_id")
                elif isinstance(parsed_amount, (int, float)):
                    actual_amount = float(parsed_amount)
                else:
                    # Try to parse as float directly
                    actual_amount = float(parsed_amount)
            except (ValueError, TypeError, AttributeError):
                # If parsing fails, try to convert amount directly
                try:
                    actual_amount = float(amount)
                except (ValueError, TypeError):
                    self.log.error("❌ Failed to parse amount: %s", amount)
                    raise ValueError(f"Invalid amount format: {amount}")
            
            return await _create_payment_impl(actual_amount, order_id)
        
        tools.append(make_tool(
            "create_payment",
            "Create a payment intent. Takes amount in INR and optional order_id. Returns a JSON object with payment_id and status.",
            create_payment
        ))
        
        # check_payment_status
        async def check_payment_status(payment_id: str) -> str:
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
                
                return json.dumps(status)
            except Exception as e:
                self.log.error("❌ TOOL ERROR: check_payment_status failed - %s", str(e))
                raise
        
        tools.append(make_tool(
            "check_payment_status",
            "Check the status of a payment by payment_id. Returns a JSON object with payment status and transaction details.",
            check_payment_status
        ))
        
        return tools

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

    @staticmethod
    def _quantity_to_int(quantity: Optional[str]) -> int:
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

    async def _pick_and_add(self, ingredient: Any, limit: int = 3) -> Optional[dict]:
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

    async def build_cart_for_plan(self, ingredients: List) -> dict:
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
        """Plan ingredients for a recipe and return the plan (without adding to cart)."""
        plan_start_time = time.time()
        self.log.info("📝 Planning recipe ingredients from text...")
        self.log.debug("Input text: %s", text[:200] + "..." if len(text) > 200 else text)
        
        try:
            # Use LangChain chain
            chain = self.plan_prompt | self.model
            response = await chain.ainvoke({"input": text})
            
            # Parse JSON from response
            content = response.content if hasattr(response, 'content') else str(response)
            # Try to extract JSON from response (might have markdown code blocks)
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            parsed = json.loads(content)
            ingredient_list = IngredientList(**parsed)
            ingredients = ingredient_list.ingredients
            plan_time = time.time() - plan_start_time
            self.log.info("📝 Got %d ingredients (took %.2fs)", len(ingredients), plan_time)
            
            # Log all ingredients for debugging
            self.log.debug("Ingredient list:")
            for idx, ing in enumerate(ingredients, 1):
                self.log.debug("  %d. %s (qty: %s, optional: %s)", idx, ing.name, ing.quantity or "N/A", ing.optional)
            
            # Warn if we got very few ingredients
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
            
            response_parts.append("\n🛒 **Would you like me to help you find and purchase these items from Blinkit?**\n")
            response_parts.append("Just say 'yes' or 'proceed' and I'll search for them and add to your cart!\n")
            
            formatted_response = "".join(response_parts)
            self.log.debug("Formatted response length: %d chars", len(formatted_response))
            
            # Convert to dict format matching original (using model_dump equivalent)
            ingredients_data = [{"name": ing.name, "quantity": ing.quantity, "optional": ing.optional} for ing in ingredients]
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
        plan_result = await self.plan_recipe_ingredients(text)
        ingredients_data = plan_result.get("ingredients", [])
        
        # Convert to IngredientItem objects for build_cart_for_plan
        ingredients = [IngredientItem(**ing) for ing in ingredients_data]
        
        plan_time = time.time() - plan_start_time
        self.log.info("📝 Step 1/3: Got %d ingredients (took %.2fs)", len(ingredients), plan_time)
        for idx, ing in enumerate(ingredients, 1):
            self.log.debug("  %d. %s (qty: %s, optional: %s)", idx, ing.name, ing.quantity or "N/A", ing.optional)

        # Step 2: Build cart
        self.log.info("🛒 Step 2/3: Building cart for %d ingredients...", len(ingredients))
        cart_build_start = time.time()
        cart_result = await self.build_cart_for_plan(ingredients)
        cart_build_time = time.time() - cart_build_start
        added_count = len(cart_result.get("added", []))
        skipped_count = len(cart_result.get("skipped", []))
        self.log.info("🛒 Step 2/3: Cart build complete - %d added, %d skipped (took %.2fs)", added_count, skipped_count, cart_build_time)


        # Step 3: Cart summary
        self.log.info("🛒 Step 3/3: Fetching cart summary...")
        cart = cart_result.get("cart")
        if not cart:
            await self._ensure_blinkit()
            cart_res = await self.blinkit_client.call_tool("blinkit.cart", {})
            cart = json.loads(cart_res["content"][0]["text"])
        
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
            "planned_ingredients": ingredients_data,  # Already in dict format from plan_recipe_ingredients
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
            # Run agent executor
            self.log.debug("Sending request to agent executor...")
            agent_start = time.time()
            result = await self.agent_executor.ainvoke({
                "input": full_message,
            })
            agent_run_time = time.time() - agent_start
            
            assistant_response = result.get("output", "")
            
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
            import traceback
            self.log.debug("Traceback: %s", traceback.format_exc())
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
    agent.log.info("🚀 Unified Agent (LangChain) initialized")
    agent.log.info("Log level: %s", logging.getLevelName(log_level))
    if log_level == logging.DEBUG:
        agent.log.debug("Debug mode enabled - detailed logs will be shown")
    
    print("Unified NPCI + Shopping Agent (LangChain). Type 'exit' to quit.")
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
