"""
schemas.py

Pydantic models for API request/response validation.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Request schemas  ────────────────────────────────

class CreateRunRequest(BaseModel):
    service: str
    alert_type: str    # error_rate | latency | queue_backup | dependency_failure
    severity: str      # P1 | P2 | P3
    description: str = ""
    scenario: str      # auto_fix | external_dependency | cascading_failure


class ApproveCheckpointRequest(BaseModel):
    checkpoint_id: str
    option_selected: str   # "A", "B", or "C"


class RejectCheckpointRequest(BaseModel):
    checkpoint_id: str
    reason: str = ""


# ── Response schemas  ──────────────────────────────────

class StepResponse(BaseModel):
    step_id: str
    node_name: str
    tool_name: Optional[str]
    tool_input: Optional[dict]
    tool_output: Optional[dict]
    agent_reasoning: Optional[str]
    status: str
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    run_id: str
    question: str
    options: list
    recommendation: str
    decision: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class RunResponse(BaseModel):
    run_id: str
    status: str
    service: str
    severity: str
    alert_type: str
    description: str
    scenario: str
    created_at: datetime
    completed_at: Optional[datetime]
    final_report: Optional[dict]

    class Config:
        from_attributes = True


class RunListItem(BaseModel):
    """Lightweight version for the sidebar list."""
    run_id: str
    status: str
    service: str
    severity: str
    alert_type: str
    scenario: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── WebSocket message schemas  ──────────────

class WSMessage(BaseModel):
    """
    Every WebSocket message has this shape:
      type: "step" | "checkpoint" | "complete" | "error"
      data: varies by type
    """
    type: str
    data: dict
