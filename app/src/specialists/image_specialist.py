import logging
from typing import Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class ImageSpecialist(BaseSpecialist):
    """
    ImageSpecialist - Vision capabilities via MCP.

    Provides image analysis through LLM vision models.
    Currently supports:
    - describe(base64): Analyze and describe image content

    Future capabilities:
    - generate(prompt): Text-to-image generation (deferred)
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # LLM adapter is injected by GraphBuilder

    def register_mcp_services(self, registry):
        """Expose image analysis capabilities via MCP."""
        registry.register_service(self.specialist_name, {
            "describe": self._describe_image
        })

    def _describe_image(self, base64_image: str, prompt: str = None) -> str:
        """
        Analyzes an image and returns a description.

        Args:
            base64_image: Base64-encoded image data (with or without data URL prefix)
            prompt: Optional custom prompt for analysis. If not provided, uses default.

        Returns:
            Text description of the image

        Example MCP call:
            description = mcp_client.call(
                "image_specialist",
                "describe",
                base64_image="data:image/png;base64,iVBOR...",
                prompt="Describe this image in detail"
            )
        """
        if not self.llm_adapter:
            raise ValueError(f"LLM Adapter not attached to {self.specialist_name}")

        logger.info(f"ImageSpecialist analyzing image ({len(base64_image)} chars)")

        # Load system prompt if available
        prompt_file = self.specialist_config.get("prompt_file")
        system_prompt = ""
        if prompt_file:
            try:
                system_prompt = load_prompt(prompt_file)
            except Exception as e:
                logger.warning(f"Failed to load prompt file '{prompt_file}': {e}. Using default.")
                system_prompt = "You are an expert image analyst. Provide detailed, accurate descriptions of images."
        else:
            system_prompt = "You are an expert image analyst. Provide detailed, accurate descriptions of images."

        # Default user prompt if not provided
        if not prompt:
            prompt = "Please describe this image in detail. Include what you see, the context, any text visible, colors, composition, and notable features."

        # Build request with image
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]

        request = StandardizedLLMRequest(
            messages=messages,
            image_data=base64_image
        )

        # Invoke LLM with vision
        try:
            response_data = self.llm_adapter.invoke(request)
            description = response_data.get("text_response", "")

            if not description:
                logger.warning("Empty response from LLM vision model")
                return "No description available - the model returned an empty response."

            logger.info(f"Image description generated ({len(description)} chars)")
            return description

        except Exception as e:
            logger.error(f"Error in ImageSpecialist.describe: {e}", exc_info=True)
            raise ValueError(f"Image analysis failed: {str(e)}")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Graph execution mode: Analyzes image from artifacts.

        This is called if ImageSpecialist is invoked as a graph node.
        Typically, it will be called via MCP instead.
        """
        if not self.llm_adapter:
            raise ValueError(f"LLM Adapter not attached to {self.specialist_name}")

        artifacts = state.get("artifacts", {})

        # Look for image in artifacts
        image_data = artifacts.get("uploaded_image.png") or artifacts.get("image_to_process")

        if not image_data:
            logger.warning("ImageSpecialist: No image found in artifacts.")
            return {"error": "No image to process."}

        # Get optional custom prompt from artifacts
        custom_prompt = artifacts.get("image_analysis_prompt")

        try:
            description = self._describe_image(image_data, custom_prompt)

            # "Not me" pattern: add self to forbidden_specialists after completing
            # Prevents router from looping back to image_specialist
            return {
                "artifacts": {
                    "image_description": description
                },
                "scratchpad": {
                    "image_analysis_complete": True,
                    "forbidden_specialists": [self.specialist_name]
                }
            }
        except Exception as e:
            # BUG-SPECIALIST-001: Set forbidden_specialists on failure
            # Prevents router from looping back to failing image_specialist
            logger.error(f"Error in ImageSpecialist graph execution: {e}")
            return {
                "error": str(e),
                "scratchpad": {
                    "forbidden_specialists": [self.specialist_name]
                }
            }
