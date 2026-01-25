"""
Standalone dummy agent using Pydantic AI.
This agent can answer normal questions and perform basic tool calls.
"""
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from datetime import datetime


# Create the provider with custom base URL
provider = OpenAIProvider(
    base_url="http://183.82.7.228:9532/v1",
    api_key="dummy"
)

# Create the model with custom provider
model = OpenAIChatModel(
    model_name="/model",
    provider=provider
)

# Create the agent with the model
agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant. Answer questions clearly and concisely. Use tools when needed to provide accurate information.",
)


# Define a basic tool for getting current time (using tool_plain for simpler tools)
@agent.tool_plain
def get_current_time() -> str:
    """Get the current date and time in a readable format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Define a basic calculator tool (using tool_plain for simpler tools)
@agent.tool_plain
def calculate(operation: str, a: float, b: float) -> float:
    """
    Perform basic mathematical operations.
    
    Args:
        operation: One of 'add', 'subtract', 'multiply', 'divide'
        a: First number
        b: Second number
    
    Returns:
        The result of the operation
    """
    if operation == "add":
        return a + b
    elif operation == "subtract":
        return a - b
    elif operation == "multiply":
        return a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b
    else:
        raise ValueError(f"Unknown operation: {operation}. Use 'add', 'subtract', 'multiply', or 'divide'")


def main():
    """Main function to demonstrate the agent's capabilities."""
    print("=" * 60)
    print("Dummy Agent - Basic Q&A and Tool Calls")
    print("=" * 60)
    print()
    
    # Example 1: Simple question that doesn't require tools
    print("Example 1: General Question")
    print("-" * 60)
    try:
        result = agent.run_sync("What is artificial intelligence?")
        print(f"Q: What is artificial intelligence?")
        print(f"A: {result.output}\n")
    except Exception as e:
        print(f"Error: {e}")
        print("This appears to be a server-side issue with the LLM API.\n")
    
    # Example 2: Question that requires a tool call (time)
    print("Example 2: Question requiring tool call (time)")
    print("-" * 60)
    result = agent.run_sync("What time is it right now?")
    print(f"Q: What time is it right now?")
    print(f"A: {result.output}\n")
    
    # Example 3: Question that requires a tool call (calculation)
    print("Example 3: Question requiring tool call (calculation)")
    print("-" * 60)
    result = agent.run_sync("What is 25 multiplied by 4?")
    print(f"Q: What is 25 multiplied by 4?")
    print(f"A: {result.output}\n")
    
    # Example 4: Another general question
    print("Example 4: Another general question")
    print("-" * 60)
    result = agent.run_sync("Explain what Python is in one sentence")
    print(f"Q: Explain what Python is in one sentence")
    print(f"A: {result.output}\n")
    
    print("=" * 60)
    print("Agent demonstration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

