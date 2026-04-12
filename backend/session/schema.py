from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional

class RoutingDecision(BaseModel):
    intent: str
    tier: str
    specialist: str
    context_note: Optional[str] = None

class SessionData(BaseModel):
    session_id: str
    user_id: str
    tier: str
    mode: str = "ai" # 'ai' or 'human'
    message_history: List[Dict[str, Any]] = Field(default_factory=list)
    resolved_entities: Dict[str, Any] = Field(default_factory=dict)
    tool_call_history: List[Dict[str, Any]] = Field(default_factory=list)
    tool_retry_counts: Dict[str, int] = Field(default_factory=dict)
    routing_decisions: List[RoutingDecision] = Field(default_factory=list)
    escalation_history: List[Dict[str, Any]] = Field(default_factory=list)
    relevant_memories: List[str] = Field(default_factory=list)
    state_note: Optional[str] = None

    @field_validator('state_note', mode='before')
    @classmethod
    def ensure_string_note(cls, v: Any) -> Optional[str]:
        if isinstance(v, list):
            # If it's a list of blocks, extract text
            texts = [item.get('text', '') for item in v if isinstance(item, dict)]
            return " ".join(texts)
        if v is not None and not isinstance(v, str):
            return str(v)
        return v
