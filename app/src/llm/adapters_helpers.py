# app/src/llm/adapters_helpers.py
import json
from typing import List, Dict, Any
from langchain_core.messages import BaseMessage, HumanMessage


def format_gemini_messages(messages: List[BaseMessage], static_system_prompt: str) -> List[Dict[str, Any]]:
    """
    Prepares a list of LangChain messages for the Google Gemini API.

    This function handles the Gemini-specific requirement of not having a distinct
    'system' role. It collects all system prompts (static and dynamic) and prepends
    them to the content of the first human message. It then converts the message
    list into the format Gemini expects.

    Args:
        messages: The list of LangChain BaseMessage objects.
        static_system_prompt: The static system prompt configured for the specialist.

    Returns:
        A list of dictionaries formatted for the Gemini API.
    """
    # Collect all system instructions: static (from init) and dynamic (from runtime messages)
    all_system_contents = [static_system_prompt] if static_system_prompt else []
    system_contents = [msg.content for msg in messages if msg.type == 'system']
    all_system_contents.extend(system_contents)

    # Filter out SystemMessages from the main message list
    other_messages = [msg for msg in messages if msg.type != 'system']

    # Prepend all system content to the first HumanMessage
    processed_lc_messages = []
    if all_system_contents:
        system_context_str = "\n\n".join(filter(None, all_system_contents))
        if other_messages and other_messages[0].type == 'human':
            # Prepend to existing first human message
            first_human_msg = other_messages[0]
            new_content = f"{system_context_str}\n\n---\n\n{first_human_msg.content}"
            # Recreate the message to ensure immutability is respected if the original is a Pydantic model
            processed_lc_messages.append(type(first_human_msg)(content=new_content, **first_human_msg.dict(exclude={'content'})))
            processed_lc_messages.extend(other_messages[1:])
        else:
            # No human message, create one with just the system context
            processed_lc_messages.append(HumanMessage(content=system_context_str))
            processed_lc_messages.extend(other_messages)
    else:
        processed_lc_messages = other_messages  # No system content, just use other messages

    # Convert LangChain messages to Gemini API format
    gemini_api_messages = []
    for msg in processed_lc_messages:
        role = "user" if msg.type == 'human' else "model"
        gemini_api_messages.append({"role": role, "parts": [msg.content]})

    return gemini_api_messages


def format_openai_messages(messages: List[BaseMessage], static_system_prompt: str) -> List[Dict[str, Any]]:
    """
    Prepares a list of LangChain messages for an OpenAI-compatible API.

    This function converts LangChain messages into the format expected by
    OpenAI's Chat Completions API, including handling system, user, assistant,
    and tool messages correctly. It combines static and runtime system prompts
    into a single system message, which is critical for components like the
    RouterSpecialist.

    Args:
        messages: The list of LangChain BaseMessage objects.
        static_system_prompt: The static system prompt configured for the specialist.

    Returns:
        A list of dictionaries formatted for the OpenAI API.
    """
    # Collect all system instructions: static (from init) and dynamic (from runtime messages).
    all_system_contents = [static_system_prompt] if static_system_prompt else []
    runtime_system_contents = [msg.content for msg in messages if msg.type == 'system']
    all_system_contents.extend(runtime_system_contents)

    # Combine all system content into a single message, filtering out any empty strings.
    final_system_content = "\n\n".join(filter(None, all_system_contents))

    api_messages = []
    if final_system_content:
        api_messages.append({"role": "system", "content": final_system_content})

    # Process the rest of the messages, skipping the SystemMessages we've already handled.
    for msg in messages:
        if msg.type == 'system':
            continue  # Already processed
        elif msg.type == 'human':
            api_messages.append({"role": "user", "content": msg.content})
        elif msg.type == 'ai':
            ai_msg_dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                ai_msg_dict["tool_calls"] = msg.tool_calls
                ai_msg_dict["content"] = None  # Per OpenAI spec, content is null when tool_calls are present
            api_messages.append(ai_msg_dict)
        elif msg.type == 'tool':
            api_messages.append({"role": "tool", "content": msg.content, "tool_call_id": str(msg.tool_call_id)})

    return api_messages
