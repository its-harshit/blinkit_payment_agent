# Using unified_agent_langchain.py

This guide explains how to use the LangChain version of the unified agent.

## Installation

First, install the required dependencies:

```bash
pip install -r requirements.txt
```

The LangChain dependencies are already included in `requirements.txt`:
- `langchain>=0.1.0`
- `langchain-openai>=0.1.0`
- `langchain-core>=0.1.0`

## Basic Usage

### 1. Simple Example

```python
import asyncio
from unified_agent_langchain import UnifiedAgent

async def main():
    # Create agent
    agent = UnifiedAgent()
    
    # Run a query
    response = await agent.run("Hello, what can you help me with?")
    print(response)
    
    # Clean up
    await agent.close()

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Interactive CLI

Run the built-in interactive CLI:

```bash
cd mcp_tools
python unified_agent_langchain.py
```

Or with debug logging:

```bash
python unified_agent_langchain.py --debug
```

### 3. Programmatic Usage with Conversation History

```python
import asyncio
from unified_agent_langchain import UnifiedAgent

async def main():
    agent = UnifiedAgent()
    
    try:
        # First message
        response1 = await agent.run("I want to buy ingredients for biryani")
        print(f"Agent: {response1}")
        
        # Follow-up message (agent remembers previous conversation)
        response2 = await agent.run("Yes, please help me find them")
        print(f"Agent: {response2}")
        
        # Clear history if needed
        agent.clear_history()
        
    finally:
        await agent.close()

asyncio.run(main())
```

### 4. Custom Model Configuration

```python
from langchain_openai import ChatOpenAI
from unified_agent_langchain import UnifiedAgent

# Create custom model
custom_model = ChatOpenAI(
    model="your-model-name",
    base_url="http://your-api-endpoint/v1",
    api_key="your-api-key",
    temperature=0,
)

# Use with agent
agent = UnifiedAgent(model=custom_model)
```

### 5. Using in API Server

To use the LangChain version in your API server, update `api_server.py`:

```python
# Change this import:
# from .unified_agent import UnifiedAgent
from .unified_agent_langchain import UnifiedAgent

# Rest of the code remains the same
```

## Key Features

### Available Tools

The agent has access to these tools:

1. **search_products** - Search for products by name/category
2. **get_product** - Get product details by ID
3. **add_to_cart** - Add single item to cart
4. **search_items_for_cart** - Search multiple items (returns results)
5. **add_items_to_cart_by_ids** - Add multiple items to cart by IDs
6. **view_cart** - View current cart
7. **clear_cart** - Clear all items from cart
8. **plan_recipe_ingredients_tool** - Plan ingredients for a recipe
9. **create_payment** - Create payment intent
10. **check_payment_status** - Check payment status

### Conversation History

The agent maintains conversation history automatically (last 4 exchanges). You can:

```python
# Clear history manually
agent.clear_history()

# History is automatically trimmed to last 4 exchanges
```

### Logging

Control logging level:

```python
import logging

# INFO level (default)
agent = UnifiedAgent(log_level=logging.INFO)

# DEBUG level (detailed logs)
agent = UnifiedAgent(log_level=logging.DEBUG)

# WARNING level (minimal logs)
agent = UnifiedAgent(log_level=logging.WARNING)
```

## Example Use Cases

### Recipe Shopping Flow

```python
async def recipe_shopping_example():
    agent = UnifiedAgent()
    
    # Step 1: Plan ingredients
    response1 = await agent.run("I want to buy ingredients for dosa")
    print(response1)  # Shows ingredient list
    
    # Step 2: Confirm and search
    response2 = await agent.run("Yes, please find them")
    print(response2)  # Shows search results
    
    # Step 3: Add to cart
    response3 = await agent.run("Yes, add them to cart")
    print(response3)  # Shows cart summary
    
    # Step 4: Checkout
    response4 = await agent.run("Proceed to checkout")
    print(response4)  # Processes payment
    
    await agent.close()
```

### Simple Product Search

```python
async def product_search_example():
    agent = UnifiedAgent()
    
    response = await agent.run("Search for milk")
    print(response)
    
    await agent.close()
```

### Cart Management

```python
async def cart_example():
    agent = UnifiedAgent()
    
    # Add item
    await agent.run("Add 2 units of blk-001 to cart")
    
    # View cart
    response = await agent.run("What's in my cart?")
    print(response)
    
    # Clear cart
    await agent.run("Clear my cart")
    
    await agent.close()
```

## Differences from pydantic_ai Version

### Key Differences:

1. **Framework**: Uses LangChain instead of pydantic_ai
2. **Agent Type**: Uses ReAct agent (text-based tool invocation) instead of OpenAI function calling
3. **Tool Format**: Tools return JSON strings instead of Python objects
4. **Model Compatibility**: Better compatibility with custom model endpoints that don't support OpenAI function calling

### When to Use Which:

- **Use `unified_agent.py` (pydantic_ai)**: If you want type-safe tool definitions and prefer pydantic_ai's approach
- **Use `unified_agent_langchain.py`**: If you need LangChain ecosystem integration or your model endpoint doesn't support function calling

## Troubleshooting

### Import Errors

If you get import errors, make sure LangChain is installed:

```bash
pip install langchain langchain-openai langchain-core
```

### Model Endpoint Errors

If you get API errors, check:
1. Model endpoint URL is correct
2. API key is set (even if it's "dummy")
3. Model name matches what the endpoint expects

### Tool Execution Errors

If tools fail:
1. Check that MCP servers are running (blinkit-server.js, payment-server.js)
2. Check logs with `--debug` flag
3. Verify MCP client initialization in logs

## Advanced Usage

### Custom Tool Creation

You can extend the agent with custom tools by modifying `_create_tools()` method:

```python
# In unified_agent_langchain.py, add to _create_tools():

async def my_custom_tool(param: str) -> str:
    # Your tool logic
    return json.dumps({"result": "success"})

tools.append(make_tool(
    "my_custom_tool",
    "Description of what the tool does",
    my_custom_tool
))
```

### Error Handling

```python
async def safe_run():
    agent = UnifiedAgent()
    try:
        response = await agent.run("your query")
        print(response)
    except Exception as e:
        print(f"Error: {e}")
        # Handle error
    finally:
        await agent.close()
```

## Integration with Existing Code

The LangChain version maintains the same interface as the pydantic_ai version, so you can swap them:

```python
# Easy to switch between versions
# from unified_agent import UnifiedAgent
from unified_agent_langchain import UnifiedAgent

# Rest of your code works the same
agent = UnifiedAgent()
response = await agent.run("query")
```
