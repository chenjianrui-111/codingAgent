"""Pydantic schemas for the Agent Gateway API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SkillInvokeRequest(BaseModel):
    """Request body for invoking a skill."""

    params: dict[str, Any]
    session_id: str | None = None


class SkillInvokeResponse(BaseModel):
    """Response from a skill invocation."""

    skill_id: str
    success: bool
    data: dict[str, Any] = {}
    error: str | None = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = {}
