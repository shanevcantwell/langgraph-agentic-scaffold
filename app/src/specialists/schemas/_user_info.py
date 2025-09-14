from pydantic import BaseModel, Field

class UserInfo(BaseModel):
    """A model to hold extracted user information."""
    name: str = Field(..., description="The user's full name.")
    age: int = Field(..., description="The user's age in years.")