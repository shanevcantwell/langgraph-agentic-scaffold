from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    """
    Encapsulates the parameters for a search request.
    """
    query: str
    max_results: int = 5
    extra_params: Dict[str, Any] = Field(default_factory=dict)

class BaseSearchStrategy(ABC):
    """
    Abstract base class for search strategies.
    Defines the interface that all search providers must implement.
    """

    @abstractmethod
    def execute(self, request: SearchRequest) -> List[Dict[str, str]]:
        """
        Execute a search query.

        Args:
            request: The search request object.

        Returns:
            A list of dictionaries, where each dictionary represents a search result
            and contains at least 'title', 'url', and 'snippet' keys.
        """
        pass
