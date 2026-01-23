"""Test script to verify plan_agent output schema with the new LLM."""
import asyncio
import json
import logging
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# Define the expected schema
class IngredientItem(BaseModel):
    name: str = Field(description="Ingredient name")
    quantity: str | None = Field(description="Human-friendly quantity, e.g., '2 cups'")
    optional: bool = Field(default=False, description="Whether the ingredient can be skipped")

# Create the model
model = OpenAIChatModel(
    model_name="/model",
    provider=OpenAIProvider(base_url="http://183.82.7.228:9532/v1", api_key="dummy"),
)

# Create the plan agent
plan_agent = Agent(
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

async def test_plan_agent(test_input: str):
    """Test the plan_agent with a given input and show detailed output."""
    log.info("=" * 80)
    log.info(f"Testing plan_agent with input: '{test_input}'")
    log.info("=" * 80)
    
    try:
        log.info("Calling plan_agent.run()...")
        result = await plan_agent.run(test_input)
        
        log.info("✅ Agent run completed successfully")
        log.info(f"Result type: {type(result)}")
        log.info(f"Result attributes: {dir(result)}")
        
        # Try to get the output
        if hasattr(result, 'output'):
            output = result.output
        elif hasattr(result, 'data'):
            output = result.data
        else:
            output = result
        
        log.info(f"Output type: {type(output)}")
        log.info(f"Output value: {output}")
        
        # Try to validate as list[IngredientItem]
        if isinstance(output, list):
            log.info(f"✅ Output is a list with {len(output)} items")
            validated_items = []
            for idx, item in enumerate(output):
                log.info(f"\nItem {idx + 1}:")
                log.info(f"  Type: {type(item)}")
                log.info(f"  Value: {item}")
                
                # Try to validate as IngredientItem
                try:
                    if isinstance(item, dict):
                        validated = IngredientItem(**item)
                    elif isinstance(item, IngredientItem):
                        validated = item
                    else:
                        # Try to convert
                        validated = IngredientItem.model_validate(item)
                    validated_items.append(validated)
                    log.info(f"  ✅ Validated successfully: {validated.model_dump()}")
                except Exception as e:
                    log.error(f"  ❌ Validation failed: {e}")
                    log.error(f"  Item structure: {item}")
            
            # Try to create the full list
            try:
                full_list = [IngredientItem.model_validate(item) for item in output]
                log.info(f"\n✅ All {len(full_list)} items validated successfully!")
                log.info("Final validated output:")
                for item in full_list:
                    log.info(f"  - {item.model_dump()}")
                return True
            except Exception as e:
                log.error(f"\n❌ Failed to validate full list: {e}")
                return False
        else:
            log.error(f"❌ Output is not a list! Got: {type(output)}")
            log.error(f"Output value: {output}")
            return False
            
    except Exception as e:
        log.error(f"❌ Error during agent run: {e}")
        import traceback
        log.error(f"Traceback:\n{traceback.format_exc()}")
        return False

async def test_raw_llm_response():
    """Test what the raw LLM returns without pydantic_ai validation."""
    log.info("\n" + "=" * 80)
    log.info("Testing raw LLM response (without pydantic_ai)")
    log.info("=" * 80)
    
    try:
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(
            base_url="http://183.82.7.228:9532/v1",
            api_key="dummy"
        )
        
        # Get the JSON schema that pydantic_ai would send
        schema = IngredientItem.model_json_schema()
        list_schema = {
            "type": "array",
            "items": schema
        }
        
        log.info("JSON Schema that would be sent:")
        log.info(json.dumps(list_schema, indent=2))
        
        prompt = (
            "You are a recipe ingredient planner. Plan ALL essential ingredients for 'egg biryani'.\n"
            "Return a JSON array of objects. Each object should have:\n"
            "- name: string (ingredient name)\n"
            "- quantity: string or null (e.g., '2 cups', '1 kg', or null)\n"
            "- optional: boolean (default false)\n"
            "\n"
            "Return 6-7 essential ingredients for egg biryani."
        )
        
        log.info(f"\nSending prompt to LLM...")
        response = await client.chat.completions.create(
            model="/model",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that returns valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"} if False else None,  # Try without structured output first
            temperature=0.7
        )
        
        log.info("✅ Raw LLM response received")
        log.info(f"Response type: {type(response)}")
        log.info(f"Response content: {response.choices[0].message.content}")
        
        # Try to parse as JSON
        try:
            content = response.choices[0].message.content
            # Try to extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            parsed = json.loads(content)
            log.info(f"✅ Parsed JSON successfully: {type(parsed)}")
            log.info(f"Parsed value: {json.dumps(parsed, indent=2)}")
            
            # Try to validate
            if isinstance(parsed, list):
                log.info(f"✅ It's a list with {len(parsed)} items")
                for idx, item in enumerate(parsed):
                    try:
                        validated = IngredientItem(**item)
                        log.info(f"  Item {idx + 1}: ✅ Valid - {validated.model_dump()}")
                    except Exception as e:
                        log.error(f"  Item {idx + 1}: ❌ Invalid - {e}")
                        log.error(f"    Item data: {item}")
            elif isinstance(parsed, dict):
                log.warning(f"⚠️  Got a dict instead of list. Keys: {list(parsed.keys())}")
                # Check if it has an 'ingredients' key
                if 'ingredients' in parsed:
                    log.info("Found 'ingredients' key, trying that...")
                    ingredients = parsed['ingredients']
                    if isinstance(ingredients, list):
                        for idx, item in enumerate(ingredients):
                            try:
                                validated = IngredientItem(**item)
                                log.info(f"  Item {idx + 1}: ✅ Valid - {validated.model_dump()}")
                            except Exception as e:
                                log.error(f"  Item {idx + 1}: ❌ Invalid - {e}")
            else:
                log.error(f"❌ Unexpected type: {type(parsed)}")
                
        except json.JSONDecodeError as e:
            log.error(f"❌ Failed to parse JSON: {e}")
            log.error(f"Raw content: {content}")
            
    except Exception as e:
        log.error(f"❌ Error testing raw LLM: {e}")
        import traceback
        log.error(f"Traceback:\n{traceback.format_exc()}")

async def main():
    """Run all tests."""
    log.info("Starting plan_agent schema validation tests...")
    log.info(f"Model: {model.model_name}")
    # Try to get base_url from model if available
    try:
        base_url = getattr(model, 'base_url', 'N/A')
        log.info(f"Base URL: {base_url}")
    except:
        log.info("Base URL: http://183.82.7.228:9532/v1")
    
    # Test 1: Test with pydantic_ai Agent
    log.info("\n" + "=" * 80)
    log.info("TEST 1: Testing with pydantic_ai Agent")
    log.info("=" * 80)
    test1_result = await test_plan_agent("egg biryani")
    
    # Test 2: Test raw LLM response
    await test_raw_llm_response()
    
    # Test 3: Test with another recipe
    log.info("\n" + "=" * 80)
    log.info("TEST 3: Testing with 'dosa'")
    log.info("=" * 80)
    test3_result = await test_plan_agent("dosa")
    
    log.info("\n" + "=" * 80)
    log.info("SUMMARY")
    log.info("=" * 80)
    log.info(f"Test 1 (egg biryani): {'✅ PASSED' if test1_result else '❌ FAILED'}")
    log.info(f"Test 3 (dosa): {'✅ PASSED' if test3_result else '❌ FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
