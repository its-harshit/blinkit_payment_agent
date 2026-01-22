# Agentic Commerce with Blinkit & UPI Payment

An AI-powered commerce agent built with pydantic-ai that can search products, manage carts, and process payments via MCP (Model Context Protocol) servers.

## Features

- 🤖 **AI Agent**: Natural language interface for shopping
- 🛒 **Blinkit Integration**: Search products, view details, manage cart
- 💳 **UPI Payment**: Process payments via UPI with Blinkit's merchant VPA
- 🔌 **MCP Servers**: Modular architecture using Model Context Protocol

## Setup

### 1. Install Dependencies

```bash
# Install Node.js dependencies (if not already done)
npm install

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set API Key

For OpenAI:
```bash
export OPENAI_API_KEY='your-openai-api-key'
```

For other models (Anthropic, Google, etc.):
```bash
export ANTHROPIC_API_KEY='your-key'  # for anthropic:claude-3-5-sonnet-20241022
export GOOGLE_API_KEY='your-key'     # for google:gemini-2.0-flash-exp
```

## Usage

### Run the AI Agent

```bash
cd mcp_tools
python example_agent.py
```

Or use the agent programmatically:

```python
import asyncio
from mcp_tools.agent import CommerceAgent

async def main():
    agent = CommerceAgent(model="openai:gpt-4o-mini")
    try:
        response = await agent.run("Search for milk and add 2 units to cart")
        print(response)
    finally:
        await agent.close()

asyncio.run(main())
```

### Example Queries

- "Search for milk"
- "Show me details of product blk-001"
- "Add 2 units of blk-001 to my cart"
- "What's in my cart?"
- "Buy everything in my cart and pay"

### Test MCP Servers

```bash
node mcp_tools/test-servers.js
```

### Run Purchase Flow (Direct)

```bash
node mcp_tools/buy-blinkit.js
```

## Project Structure

```
mcp_tools/
├── dist/                    # MCP servers (Node.js)
│   ├── blinkit-server.js    # Blinkit catalog & cart MCP
│   ├── payment-server.js    # UPI payment MCP
│   └── cli.js               # CLI for testing MCP servers
├── agent.py                 # AI Agent (pydantic-ai)
├── mcp_client.py            # MCP client for Python
├── example_agent.py         # Example usage script
├── buy-blinkit.js           # Direct purchase flow
├── test-servers.js          # Test both MCP servers
└── mcp.config.json          # MCP server configuration
```

## MCP Tools Available

### Blinkit Tools
- `blinkit.search` - Search products by name/category
- `blinkit.item` - Get product details by ID
- `blinkit.add_to_cart` - Add items to cart
- `blinkit.cart` - View cart summary

### Payment Tools
- `payment.methods` - List payment methods (UPI only)
- `payment.init` - Create payment intent
- `payment.status` - Check payment status

## License

MIT

