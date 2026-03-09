# app/src/llm/adapters_helpers.py
from typing import List
from langchain_core.messages import BaseMessage, HumanMessage

from google.genai import types


def format_gemini_messages(messages: List[BaseMessage], static_system_prompt: str) -> List[types.Content]:
    """
    Prepares a list of LangChain messages for the Google Gemini API (new google-genai SDK).

    This function handles the Gemini-specific requirement of not having a distinct
    'system' role. It collects all system prompts (static and dynamic) and prepends
    them to the content of the first human message. It then converts the message
    list into types.Content objects that the new SDK expects.

    Note: System prompt is also passed via config.system_instruction, but we still
    prepend to first message for compatibility with multi-turn conversations.

    Args:
        messages: The list of LangChain BaseMessage objects.
        static_system_prompt: The static system prompt configured for the specialist.

    Returns:
        A list of types.Content objects for the new google-genai SDK.
    """
    # Collect all system instructions: the static one from init and any dynamic ones from runtime.
    system_contents = [static_system_prompt] + [msg.content for msg in messages if msg.type == 'system']
    # Combine all system content into a single block, filtering out any empty strings.
    final_system_content = "\n\n".join(filter(None, system_contents))

    # Filter out SystemMessages from the main message list
    processed_lc_messages = [msg for msg in messages if msg.type != 'system']

    # Prepend the combined system content to the first HumanMessage if it exists.
    if final_system_content:
        if processed_lc_messages and processed_lc_messages[0].type == 'human':
            first_human_msg = processed_lc_messages[0]
            new_content = f"{final_system_content}\n\n---\n\n{first_human_msg.content}"
            processed_lc_messages[0] = type(first_human_msg)(content=new_content, **first_human_msg.model_dump(exclude={'content'}))
        else:
            # If there's no human message, insert the system context as the first human message.
            processed_lc_messages.insert(0, HumanMessage(content=final_system_content))

    # Convert LangChain messages to google-genai types.Content format
    gemini_contents = []
    for msg in processed_lc_messages:
        role = "user" if msg.type == 'human' else "model"
        content = types.Content(
            role=role,
            parts=[types.Part(text=str(msg.content))]
        )
        gemini_contents.append(content)

    return gemini_contents
