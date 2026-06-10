import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator

class EventPriority(str, Enum):
    P0 = "P0"  # Interrupt signals (wake word, system alarm) - bypasses queues
    P1 = "P1"  # Critical (LLM result, STT final output)
    P2 = "P2"  # Normal (tool results, agent results)
    P3 = "P3"  # Background (memory consolidation, health ticks)

    def to_int(self) -> int:
        mapping = {
            EventPriority.P0: 0,
            EventPriority.P1: 1,
            EventPriority.P2: 2,
            EventPriority.P3: 3
        }
        return mapping[self]

class AgentType(str, Enum):
    WEB_AGENT = "WEB_AGENT"
    PC_AGENT = "PC_AGENT"
    MEMORY_AGENT = "MEMORY_AGENT"
    KNOWLEDGE_AGENT = "KNOWLEDGE_AGENT"
    VOICE_AGENT = "VOICE_AGENT"

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    BUSY = "BUSY"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"

class AgentTrustLevel(str, Enum):
    SYSTEM = "SYSTEM"
    ELEVATED = "ELEVATED"
    STANDARD = "STANDARD"
    SANDBOXED = "SANDBOXED"

class PermissionEnum(str, Enum):
    READ_ONLY = "READ_ONLY"
    WRITE_SAFE = "WRITE_SAFE"
    ELEVATED = "ELEVATED"
    PRIVILEGED = "PRIVILEGED"
    HUMAN_CONFIRMED = "HUMAN_CONFIRMED"

class TaskStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"

class ToolCallRecord(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str
    result: Optional[str] = None

class TaskDispatch(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    agent_type: AgentType
    intent: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 10000
    priority: EventPriority = EventPriority.P2
    requires_permission: List[PermissionEnum] = Field(default_factory=list)
    correlation_id: UUID

class TaskResult(BaseModel):
    task_id: UUID
    agent_id: UUID
    status: TaskStatus
    payload: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    latency_ms: int = 0
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    correlation_id: UUID

class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    topic: str
    priority: EventPriority
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    source: str
    correlation_id: UUID
    session_id: UUID
    payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        if not re.match(r"^friday\.[a-zA-Z0-9_\-*]+(\.[a-zA-Z0-9_\-*]+)*$", v):
            raise ValueError("Topic must match format friday.{layer}.{event_name}")
        return v
