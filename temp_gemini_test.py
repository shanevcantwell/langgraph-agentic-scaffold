import os
import google.generativeai as genai
from pydantic import BaseModel, Field
from langchain_core.tools import Tool

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY") # Assuming GEMINI_API_KEY is set in .env
if not API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
genai.configure(api_key=API_KEY)

# Define a simple Pydantic model for tool arguments
class SimpleToolArgs(BaseModel):
    name: str = Field(..., description="The name to greet.")
    age: int = Field(..., description="The age of the person.")

# Define a simple tool
def greet_person(name: str, age: int) -> str:
    return f"Hello, {name}! You are {age} years old."

simple_tool = Tool(name="greet_person", func=greet_person, description="Greets a person with their name and age.", args_schema=SimpleToolArgs)

# Get the schema from the Pydantic model
pydantic_schema = simple_tool.args_schema.schema()
print("Pydantic Schema (tool_obj.args_schema.schema()):")
print(json.dumps(pydantic_schema, indent=2))

# Manually construct the Gemini-compatible tool schema
gemini_tool_schema = {
    "function_declarations": [
        {
            "name": simple_tool.name,
            "description": simple_tool.description,
            "parameters": {
                "type": "object",
                "properties": {
                    prop_name: {
                        "type": prop_details["type"],
                        "description": prop_details.get("description", "")
                    }
                    for prop_name, prop_details in pydantic_schema["properties"].items()
                },
                "required": pydantic_schema.get("required", [])
            }
        }
    ]
}

print("\nGemini-compatible Tool Schema:")
print(json.dumps(gemini_tool_schema, indent=2))

# Attempt to call Gemini with the tool
model = genai.GenerativeModel("gemini-1.5-flash") # Or your preferred model

try:
    response = model.generate_content(
        "Greet John who is 30 years old.",
        tools=gemini_tool_schema["function_declarations"],
        tool_config=genai.types.ToolConfig(
            function_calling_config=genai.types.FunctionCallingConfig(
                mode=genai.types.FunctionCallingConfig.Mode.ANY
            )
        )
    )

    print("\nGemini API Response:")
    print(response.text)
    if response.parts:
        for part in response.parts:
            if part.function_call:
                print(f"Function Call: {part.function_call.name}({part.function_call.args})")
            else:
                print(f"Text Response: {part.text}")
    else:
        print("No parts in response.")

except Exception as e:
    print(f"An error occurred during Gemini API call: {e}")
