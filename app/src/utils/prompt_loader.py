# src/utils/prompt_loader.py

from pathlib import Path

from .path_utils import APP_ROOT
class PromptLoader:
    """
    A utility class to load prompt templates from the filesystem.
    """
    @staticmethod
    def load(prompt_name: str) -> str:
        """
        Loads a prompt from the 'app/prompts' directory.

        Args:
            prompt_name (str): The base name of the prompt file (e.g., 'data_extractor_specialist').

        Returns:
            str: The content of the prompt file.
        
        Raises:
            FileNotFoundError: If the prompt file does not exist.
        """
        prompt_path = APP_ROOT / "prompts" / prompt_name
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")
            
        return prompt_path.read_text().strip()

# Create a function-like alias for the static method to align with the
# DEVELOPERS_GUIDE.md template and specialist implementations.
load_prompt = PromptLoader.load
