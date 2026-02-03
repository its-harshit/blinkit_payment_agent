"""Shopping/cart tools (Blinkit) for the unified agent."""
import time
from typing import Annotated, Any

from pydantic_ai import RunContext

from ..core import parse_mcp_text_result


def make_shopping_tools(agent: Any):
    """Return shopping tool functions that close over the given agent."""
    assert agent is not None

    async def get_product(ctx: RunContext, item_id: Annotated[str, "Product ID (e.g., blk-001)"]):
        agent.log.info("🔍 TOOL CALL: get_product(item_id=%s)", item_id)
        try:
            await agent._ensure_blinkit()
            agent.log.debug("Calling MCP tool: blinkit.item with params: %s", {"id": item_id})
            result = await agent.blinkit_client.call_tool("blinkit.item", {"id": item_id})
            item = parse_mcp_text_result(result)
            agent.log.info("✅ TOOL SUCCESS: get_product retrieved item: %s", item.get("name", item_id))
            agent.log.debug("Product details: %s", item)
            return item
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: get_product failed - %s", str(e))
            raise

    async def search_items(
        ctx: RunContext,
        item_names: Annotated[list[str], "List of item names to search (can be single item as list)"],
        quantities: Annotated[list[int] | None, "Optional list of quantities (defaults to 1 for each)"] = None,
    ):
        """Search for multiple items and return results (without adding to cart).

        Use this to search items first, show results to user, then ask for confirmation before adding.
        Returns a dict with 'found_items' array. Each item in 'found_items' has: {'id': 'blk-xxx', 'name': '...', 'price': N, 'quantity': N, 'original_name': '...'}
        IMPORTANT: When user confirms, pass the ENTIRE 'found_items' array directly to add_items_to_cart_by_ids. Do not modify or recreate the items.
        Uses the same fast sequential search method as _pick_and_add.
        """
        start_time = time.time()
        agent.log.info("🔍 TOOL CALL: search_items(%d items)", len(item_names))
        agent.log.debug("Item names: %s", item_names)
        agent.log.debug("Quantities: %s", quantities)

        try:
            await agent._ensure_blinkit()
            found_items = []
            skipped = []

            for idx, item_name in enumerate(item_names):
                agent.log.debug("Processing item %d/%d: %s", idx + 1, len(item_names), item_name)
                name = item_name.strip()
                queries = [name]
                key = name.lower()
                if key in agent.search_aliases:
                    aliases = agent.search_aliases[key]
                    queries.extend(aliases)
                    agent.log.debug("  Found aliases for '%s': %s", name, aliases)
                else:
                    agent.log.debug("  No aliases found for '%s'", name)
                agent.log.debug("  Search queries to try: %s", queries)

                items = []
                tried = []
                for q in queries:
                    agent.log.info("Searching Blinkit for: %s", q)
                    tried.append(q)
                    try:
                        resp = await agent.blinkit_client.call_tool("blinkit.search", {"query": q, "limit": 3})
                        found = parse_mcp_text_result(resp)
                        if found:
                            items = found
                            agent.log.debug("  ✅ Found %d result(s) for query '%s'", len(found), q)
                            break
                        else:
                            agent.log.debug("  ⚠️  No results for query '%s'", q)
                    except Exception as search_error:
                        agent.log.warning("  ❌ Search error for query '%s': %s", q, str(search_error))

                if not items:
                    agent.log.warning("⚠️  No results for item '%s' after trying queries: %s", name, tried)
                    skipped.append(name)
                    continue

                choice = items[0]
                original_qty = quantities[idx] if quantities and idx < len(quantities) else 1
                qty = max(1, original_qty)
                stock = choice.get("stock", qty)
                original_qty_for_clamp = qty
                qty = min(qty, stock, 5)
                if qty != original_qty_for_clamp:
                    agent.log.debug("  Quantity clamped: %d -> %d (stock=%d, max=5)", original_qty_for_clamp, qty, stock)

                found_item = {
                    "id": choice["id"],
                    "name": choice.get("name"),
                    "price": choice.get("price", 0),
                    "quantity": qty,
                    "original_name": name,
                }
                found_items.append(found_item)
                agent.log.info(
                    "✅ Found: %s x%d (%s) - ₹%.2f",
                    choice.get("name"), qty, choice.get("id"), choice.get("price", 0),
                )
                agent.log.debug("  Item details: %s", found_item)

            elapsed = time.time() - start_time
            agent.log.info(
                "✅ TOOL SUCCESS: search_items - %d found, %d skipped (took %.2fs)",
                len(found_items), len(skipped), elapsed,
            )
            agent.log.debug(
                "Found items summary: %s",
                [{"id": item["id"], "name": item["name"], "qty": item["quantity"]} for item in found_items],
            )
            if skipped:
                agent.log.debug("Skipped items: %s", skipped)

            return {"found_items": found_items, "skipped": skipped, "time_taken": elapsed}
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error("❌ TOOL ERROR: search_items failed after %.2fs - %s", elapsed, str(e))
            import traceback
            agent.log.debug("Traceback: %s", traceback.format_exc())
            raise

    async def add_items_to_cart_by_ids(
        ctx: RunContext,
        items: Annotated[
            list[dict],
            "List of items to add to cart. Each item should be a dict with at least 'id' (product ID like 'blk-101') and 'quantity' (number). Optional fields: 'name', 'price'. You can use items from search_items results or construct them with the IDs from search results.",
        ],
    ):
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
        start_time = time.time()
        agent.log.info("🛒 TOOL CALL: add_items_to_cart_by_ids(%d items)", len(items))
        received_ids = [item.get("id", "NO_ID") for item in items]
        agent.log.info("📋 Received items with IDs: %s", received_ids)
        agent.log.debug("Full received items structure: %s", items)

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                agent.log.warning("⚠️  Item %d is not a dict: %s", idx, type(item))
            elif "id" not in item:
                agent.log.warning("⚠️  Item %d missing 'id' field: %s", idx, item)

        try:
            await agent._ensure_blinkit()
            successful = []
            failed = []
            item_timings = []

            agent.log.debug("Starting sequential add process for %d items", len(items))
            agent.log.info("⏱️  Starting to add %d items to cart (sequential mode)", len(items))

            for idx, item in enumerate(items):
                item_start = time.time()
                agent.log.debug("Processing item %d/%d: %s", idx + 1, len(items), item)
                item_id = item.get("id")
                original_quantity = item.get("quantity", 1)
                quantity = max(1, original_quantity)
                item_name = item.get("name", "Unknown")
                item_price = item.get("price", 0)
                agent.log.debug(
                    "  Item details: id=%s, name=%s, qty=%d (original=%d), price=₹%.2f",
                    item_id, item_name, quantity, original_quantity, item_price,
                )

                if not item_id:
                    agent.log.error("❌ Missing item ID for item %d: %s", idx, item)
                    failed.append({"item": item, "error": "Missing ID"})
                    item_timings.append({"item": item_name, "time": time.time() - item_start, "status": "failed", "reason": "Missing ID"})
                    continue
                if not item_id.startswith("blk-"):
                    agent.log.error("❌ Invalid item ID format: '%s' (expected 'blk-xxx'). Item: %s", item_id, item)
                    failed.append({"item": item, "error": f"Invalid ID format: {item_id}"})
                    item_timings.append({"item": item_name, "time": time.time() - item_start, "status": "failed", "reason": "Invalid ID"})
                    continue

                try:
                    agent.log.debug("  📞 Calling blinkit.add_to_cart with id=%s, quantity=%d", item_id, quantity)
                    mcp_call_start = time.time()
                    added = await agent.blinkit_client.call_tool(
                        "blinkit.add_to_cart", {"id": item_id, "quantity": quantity}
                    )
                    mcp_call_time = time.time() - mcp_call_start
                    parse_start = time.time()
                    entry = parse_mcp_text_result(added)
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
                        "status": "success",
                    })
                    agent.log.info(
                        "✅ Added: %s x%d (%s) - ₹%.2f | ⏱️  Total: %.2fs (MCP: %.2fs, Parse: %.3fs)",
                        added_item_name, added_qty, item_id, added_price,
                        item_total_time, mcp_call_time, parse_time,
                    )
                    agent.log.debug("  Cart entry: %s", entry)
                    successful.append(entry)
                except Exception as e:
                    item_total_time = time.time() - item_start
                    item_timings.append({"item": item_name, "time": item_total_time, "status": "failed", "error": str(e)})
                    agent.log.warning("⚠️  Failed to add item %s (qty=%d) after %.2fs: %s", item_id, quantity, item_total_time, str(e))
                    agent.log.debug("  Error details: %s", str(e))
                    import traceback
                    agent.log.debug("  Traceback: %s", traceback.format_exc())
                    failed.append({"item": {"id": item_id, "quantity": quantity, "name": item_name}, "error": str(e)})

            elapsed = time.time() - start_time
            if item_timings:
                total_mcp_time = sum(t.get("mcp_time", 0) for t in item_timings if "mcp_time" in t)
                total_parse_time = sum(t.get("parse_time", 0) for t in item_timings if "parse_time" in t)
                avg_item_time = sum(t["time"] for t in item_timings) / len(item_timings)
                max_item_time = max(t["time"] for t in item_timings)
                min_item_time = min(t["time"] for t in item_timings)
                agent.log.info("⏱️  TIMING BREAKDOWN:")
                agent.log.info("  • Total time: %.2fs", elapsed)
                agent.log.info("  • Items processed: %d", len(item_timings))
                agent.log.info("  • Avg per item: %.2fs | Min: %.2fs | Max: %.2fs", avg_item_time, min_item_time, max_item_time)
                if total_mcp_time > 0:
                    agent.log.info("  • Total MCP call time: %.2fs (%.1f%% of total)", total_mcp_time, (total_mcp_time / elapsed * 100) if elapsed > 0 else 0)
                if total_parse_time > 0:
                    agent.log.info("  • Total parse time: %.3fs (%.1f%% of total)", total_parse_time, (total_parse_time / elapsed * 100) if elapsed > 0 else 0)
                agent.log.debug("  • Per-item timings: %s", item_timings)

            agent.log.info(
                "✅ TOOL SUCCESS: add_items_to_cart_by_ids - %d succeeded, %d failed (took %.2fs)",
                len(successful), len(failed), elapsed,
            )
            if successful:
                agent.log.debug(
                    "Successfully added items: %s",
                    [{"id": r.get("item", {}).get("id"), "name": r.get("item", {}).get("name"), "qty": r.get("quantity")} for r in successful],
                )
            if failed:
                agent.log.warning("Failed items: %s", failed)

            agent.log.debug("Fetching cart summary...")
            cart_start = time.time()
            cart_res = await agent.blinkit_client.call_tool("blinkit.cart", {})
            cart_mcp_time = time.time() - cart_start
            cart_parse_start = time.time()
            cart = parse_mcp_text_result(cart_res)
            cart_parse_time = time.time() - cart_parse_start
            cart_items_count = len(cart.get("items", []))
            cart_total = cart.get("total", 0)
            cart_total_time = time.time() - cart_start
            agent.log.info(
                "📊 Cart summary fetched: %d items, Total: ₹%.2f (took %.2fs: MCP=%.2fs, Parse=%.3fs)",
                cart_items_count, cart_total, cart_total_time, cart_mcp_time, cart_parse_time,
            )
            agent.log.debug("Cart details: %s", cart)

            return {
                "successful": successful,
                "failed": failed,
                "successful_items": [{"name": r.get("item", {}).get("name"), "quantity": r.get("quantity")} for r in successful],
                "failed_items": failed,
                "cart": cart,
                "time_taken": elapsed,
            }
        except Exception as e:
            elapsed = time.time() - start_time
            agent.log.error("❌ TOOL ERROR: add_items_to_cart_by_ids failed after %.2fs - %s", elapsed, str(e))
            import traceback
            agent.log.debug("Traceback: %s", traceback.format_exc())
            raise

    async def view_cart(ctx: RunContext):
        agent.log.info("🛒 TOOL CALL: view_cart()")
        try:
            await agent._ensure_blinkit()
            agent.log.debug("Calling MCP tool: blinkit.cart")
            result = await agent.blinkit_client.call_tool("blinkit.cart", {})
            cart = parse_mcp_text_result(result)
            item_count = len(cart.get("items", []))
            total = cart.get("total", 0)
            agent.log.info("✅ TOOL SUCCESS: view_cart - %d items, Total: ₹%.2f", item_count, total)
            agent.log.debug("Cart contents: %s", cart)
            return cart
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: view_cart failed - %s", str(e))
            raise

    async def clear_cart(ctx: RunContext):
        """Clear all items from the cart (typically called after successful payment)."""
        agent.log.info("🗑️  TOOL CALL: clear_cart()")
        try:
            await agent._ensure_blinkit()
            agent.log.debug("Calling MCP tool: blinkit.clear_cart")
            result = await agent.blinkit_client.call_tool("blinkit.clear_cart", {})
            cleared = parse_mcp_text_result(result)
            items_removed = cleared.get("itemsRemoved", 0)
            agent.log.info("✅ TOOL SUCCESS: clear_cart - Removed %d item(s) from cart", items_removed)
            agent.log.debug("Clear cart result: %s", cleared)
            return cleared
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: clear_cart failed - %s", str(e))
            raise

    async def list_blinkit_discounts_tool(
        ctx: RunContext,
        amount: Annotated[float, "Cart/order total in INR"],
        order_id: Annotated[str | None, "Optional order id"] = None,
    ):
        """List Blinkit promo codes eligible for this cart total. Call before create_payment at checkout; show options to user and use apply_blinkit_discount_tool if they pick one."""
        agent.log.info("🏷️  TOOL CALL: list_blinkit_discounts_tool(amount=₹%.2f)", amount)
        try:
            await agent._ensure_blinkit()
            params = {"amount": amount}
            if order_id:
                params["orderId"] = order_id
            result = await agent.blinkit_client.call_tool("blinkit.list_discounts", params)
            data = parse_mcp_text_result(result)
            discounts = data.get("discounts", [])
            agent.log.info("✅ TOOL SUCCESS: list_blinkit_discounts_tool - %d eligible", len(discounts))
            return data
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: list_blinkit_discounts_tool failed - %s", str(e))
            raise

    async def apply_blinkit_discount_tool(
        ctx: RunContext,
        code: Annotated[str, "Discount code (e.g. FIRST50, BLINK10)"],
        amount: Annotated[float, "Order total in INR before discount"],
        order_id: Annotated[str | None, "Optional order id"] = None,
    ):
        """Apply a Blinkit discount code; returns valid, finalAmount, message. Use finalAmount in create_payment if valid."""
        agent.log.info("🏷️  TOOL CALL: apply_blinkit_discount_tool(code=%s, amount=₹%.2f)", code, amount)
        try:
            await agent._ensure_blinkit()
            params = {"code": code, "amount": amount}
            if order_id:
                params["orderId"] = order_id
            result = await agent.blinkit_client.call_tool("blinkit.apply_discount", params)
            data = parse_mcp_text_result(result)
            agent.log.info("✅ TOOL SUCCESS: apply_blinkit_discount_tool - valid=%s, finalAmount=₹%.2f", data.get("valid"), data.get("finalAmount", 0))
            return data
        except Exception as e:
            agent.log.error("❌ TOOL ERROR: apply_blinkit_discount_tool failed - %s", str(e))
            raise

    async def plan_recipe_ingredients_tool(
        ctx: RunContext,
        recipe_text: Annotated[str, "Recipe or dish name (e.g., 'biryani', 'dosa', 'chole bhature')"],
    ):
        """Plan ingredients needed for a recipe. Returns the ingredient list and asks user to confirm before buying.

        Use this tool when user asks to buy items for a recipe/dish. This is step 1 - it only plans, doesn't add to cart.
        After showing the plan, ask user if they want to buy these items from supermarket.
        """
        tool_start = time.time()
        agent.log.info("📝 TOOL CALL: plan_recipe_ingredients_tool(recipe=%s)", recipe_text[:50])
        agent.log.debug("Full recipe text: %s", recipe_text)
        try:
            result = await agent.plan_recipe_ingredients(recipe_text)
            ingredients_count = len(result.get("ingredients", []))
            tool_time = time.time() - tool_start
            agent.log.info(
                "✅ TOOL SUCCESS: plan_recipe_ingredients_tool - Planned %d ingredients (took %.2fs)",
                ingredients_count, tool_time,
            )
            agent.log.debug(
                "Result structure: message length=%d, ingredients count=%d, step=%s",
                len(result.get("message", "")), ingredients_count, result.get("step"),
            )
            return result
        except Exception as e:
            tool_time = time.time() - tool_start
            agent.log.error("❌ TOOL ERROR: plan_recipe_ingredients_tool failed after %.2fs - %s", tool_time, str(e))
            import traceback
            agent.log.debug("Traceback: %s", traceback.format_exc())
            raise

    return [
        get_product,
        search_items,
        add_items_to_cart_by_ids,
        view_cart,
        clear_cart,
        list_blinkit_discounts_tool,
        apply_blinkit_discount_tool,
        plan_recipe_ingredients_tool,
    ]
