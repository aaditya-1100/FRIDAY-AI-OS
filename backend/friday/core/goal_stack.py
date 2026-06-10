from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class GoalStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Goal(BaseModel):
    goal_id: UUID = Field(default_factory=uuid4)
    description: str
    status: GoalStatus = GoalStatus.PENDING
    parent_id: Optional[UUID] = None

def push_goal(goal_stack: List[Dict[str, Any]], description: str, parent_id: Optional[UUID] = None) -> Goal:
    """Pushes a new goal onto the stack."""
    goal = Goal(description=description, parent_id=parent_id)
    goal_stack.append(goal.model_dump())
    return goal

def update_goal_status(goal_stack: List[Dict[str, Any]], goal_id: UUID, status: GoalStatus) -> bool:
    """Updates the status of a specific goal in the stack."""
    for g in goal_stack:
        if str(g["goal_id"]) == str(goal_id):
            g["status"] = status.value
            return True
    return False

def get_active_goal(goal_stack: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Returns the most recent active goal on the stack."""
    for g in reversed(goal_stack):
        if g["status"] == GoalStatus.ACTIVE.value:
            return g
    return None
