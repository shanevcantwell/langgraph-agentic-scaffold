# src/utils/prompt_loader.py

from pathlib import Path

class PromptLoader:
    """
    A utility class to load prompt templates from the filesystem.
    """
    @staticmethod
    def load(prompt_name: str) -> str:
        """
        Loads a prompt from the 'src/prompts' directory.

        Args:
            prompt_name (str): The base name of the prompt file (e.g., 'data_extractor_specialist').

        Returns:
            str: The content of the prompt file.
        
        Raises:
            FileNotFoundError: If the prompt file does not exist.
        """
        # Use _specialist_prompt.md as the standard format for prompt files
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / prompt_name
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")
            
        return prompt_path.read_text().strip()

# Create a function-like alias for the static method to align with the
# DEVELOPERS_GUIDE.md template and specialist implementations.
load_prompt = PromptLoader.load
