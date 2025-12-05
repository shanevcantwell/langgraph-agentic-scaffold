import logging
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional

from .base import BaseSpecialist

logger = logging.getLogger(__name__)

class BrowseSpecialist(BaseSpecialist):
    """
    The browsing primitive of the Deep Research architecture.
    A pure worker that fetches and parses web content.
    It has NO internal LLM loop.
    """
    
    def register_mcp_services(self, registry):
        """Expose browse capability via MCP."""
        registry.register_service(self.specialist_name, {
            "browse": self._perform_browse
        })

    def _perform_browse(self, url: str) -> Dict[str, str]:
        """
        Fetches and parses the content of a URL.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
                
            text = soup.get_text(separator='\n')
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return {
                "url": url,
                "title": soup.title.string if soup.title else "No Title",
                "content": text,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Browse failed for {url}: {e}")
            return {
                "url": url,
                "title": "Error",
                "content": str(e),
                "status": "error"
            }

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Executes a browse task defined in the scratchpad.
        """
        scratchpad = state.get("scratchpad", {})
        task = scratchpad.get("browse_task", {})
        
        if not task:
            return {"error": "No browse_task found in scratchpad"}
            
        url = task.get("url")
        if not url:
            return {"error": "No URL provided in browse_task"}
            
        result = self._perform_browse(url)
        return {"browse_result": result}
