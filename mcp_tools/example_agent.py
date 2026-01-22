"""Example usage of the Commerce Agent."""
import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from agent import CommerceAgent


async def example_usage():
    """Example of using the commerce agent."""
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Please set OPENAI_API_KEY environment variable")
        print("   Example: export OPENAI_API_KEY='your-key-here'")
        print("\n   You can also use other models:")
        print("   - anthropic:claude-3-5-sonnet-20241022 (requires ANTHROPIC_API_KEY)")
        print("   - google:gemini-2.0-flash-exp (requires GOOGLE_API_KEY)")
        return

    agent = CommerceAgent(model="openai:gpt-4o-mini")
    
    try:
        print("🤖 Commerce Agent ready!\n")
        print("Example queries:")
        print("  - 'Search for milk'")
        print("  - 'Add 2 units of blk-001 to cart'")
        print("  - 'Show my cart'")
        print("  - 'Buy everything in my cart and pay'")
        print("\nType your requests (or 'exit' to quit)\n")
        
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
    asyncio.run(example_usage())

