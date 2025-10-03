# app/src/specialists/schemas/_open_interpreter.py
from pydantic import BaseModel, Field

class CodeExecutionParams(BaseModel):
    """
    The parameters for executing a block of code in a specified language.
    """
    language: str = Field(
        ...,
        description="The programming language of the code to execute (e.g., 'python', 'bash').",
    )
    code: str = Field(
        ...,
        description="The block of code to be executed.",
    )