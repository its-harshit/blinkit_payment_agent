"""
Example usage of unified_agent_langchain.py

This demonstrates how to use the LangChain version of the unified agent.
"""
import asyncio
import logging
from unified_agent_langchain import UnifiedAgent


async def example_1_simple_query():
    """Example 1: Simple query"""
    print("\n" + "="*60)
    print("Example 1: Simple Query")
    print("="*60)
    
    agent = UnifiedAgent()
    try:
        response = await agent.run("Hello, what can you help me with?")
        print(f"\nAgent: {response}\n")
    finally:
        await agent.close()


async def example_2_recipe_shopping():
    """Example 2: Recipe shopping flow"""
    print("\n" + "="*60)
    print("Example 2: Recipe Shopping Flow")
    print("="*60)
    
    agent = UnifiedAgent()
    try:
        # Step 1: Plan ingredients
        print("\nStep 1: Planning ingredients...")
        response1 = await agent.run("I want to buy ingredients for biryani")
        print(f"Agent: {response1}\n")
        
        # Note: In a real scenario, you would wait for user confirmation
        # For this example, we'll simulate the flow
        
    finally:
        await agent.close()


async def example_3_product_search():
    """Example 3: Product search"""
    print("\n" + "="*60)
    print("Example 3: Product Search")
    print("="*60)
    
    agent = UnifiedAgent()
    try:
        response = await agent.run("Search for milk products")
        print(f"\nAgent: {response}\n")
    finally:
        await agent.close()


async def example_4_conversation_history():
    """Example 4: Conversation with history"""
    print("\n" + "="*60)
    print("Example 4: Conversation with History")
    print("="*60)
    
    agent = UnifiedAgent()
    try:
        # First message
        print("\nUser: What is UPI?")
        response1 = await agent.run("What is UPI?")
        print(f"Agent: {response1}\n")
        
        # Follow-up (agent remembers context)
        print("User: How do I use it?")
        response2 = await agent.run("How do I use it?")
        print(f"Agent: {response2}\n")
        
        # Clear history
        agent.clear_history()
        print("(History cleared)\n")
        
    finally:
        await agent.close()


async def example_5_custom_logging():
    """Example 5: Custom logging level"""
    print("\n" + "="*60)
    print("Example 5: Custom Logging Level")
    print("="*60)
    
    # Use DEBUG level for detailed logs
    agent = UnifiedAgent(log_level=logging.DEBUG)
    try:
        response = await agent.run("Hello")
        print(f"\nAgent: {response}\n")
    finally:
        await agent.close()


async def main():
    """Run all examples"""
    print("\n" + "="*60)
    print("LangChain Unified Agent - Usage Examples")
    print("="*60)
    
    # Run examples
    await example_1_simple_query()
    
    # Uncomment to run other examples:
    # await example_2_recipe_shopping()
    # await example_3_product_search()
    # await example_4_conversation_history()
    # await example_5_custom_logging()
    
    print("\n" + "="*60)
    print("Examples completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
