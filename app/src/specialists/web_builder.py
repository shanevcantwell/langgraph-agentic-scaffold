# src/specialists/web_builder.py

from .base import BaseSpecialist

class WebBuilder(BaseSpecialist):
    """
    A specialist that takes Mermaid.js code from the state and embeds it
    in a complete HTML document.
    This version correctly implements the execute(state) method.
    """
    def __init__(self, llm_provider: str):
        system_prompt = (
            "You are a Web Builder. Your task is to take a block of Mermaid.js "
            "code and embed it within a clean, self-contained HTML document."
        )
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)

    def execute(self, state: dict) -> dict:
        """
        Takes Mermaid code from the state, invokes the LLM to embed it in HTML,
        and returns the final HTML to update the state.
        """
        print("---WEB BUILDER: Generating HTML Artifact---")
        mermaid_code = state.get("mermaid_code")
        if not mermaid_code:
            return {"error": "Mermaid code not found in state."}

        # Invoke the LLM with the mermaid code as the user prompt
        messages_to_send = [HumanMessage(content=mermaid_code)]
        ai_response = self.invoke({"messages": messages_to_send})
        
        # Extract the HTML from the response
        final_html = ai_response["messages"][0].content
        return {"final_html": final_html}
