from typing import List, Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, Field

class ProjectState(str, Enum):
    RESEARCHING = "researching"
    SYNTHESIZING = "synthesizing"
    COMPLETE = "complete"

class ProjectContext(BaseModel):
    """
    The shared state for the Emergent Project Subgraph.
    This acts as the central memory for the project, maintaining the evolving understanding.
    """
    project_goal: str = Field(..., description="The high-level goal of this research project.")
    knowledge_base: List[str] = Field(default_factory=list, description="List of confirmed facts and findings.")
    open_questions: List[str] = Field(default_factory=list, description="List of questions that still need answers.")
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="Structured outputs created during the project.")
    state: ProjectState = Field(default=ProjectState.RESEARCHING, description="Current phase of the project.")
    iteration: int = Field(default=0, description="Current iteration count.")
    
    def add_knowledge(self, fact: str):
        self.knowledge_base.append(fact)
        
    def add_question(self, question: str):
        self.open_questions.append(question)
        
    def remove_question(self, question: str):
        if question in self.open_questions:
            self.open_questions.remove(question)
            
    def update_state(self, new_state: ProjectState):
        self.state = new_state
