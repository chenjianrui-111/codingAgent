"""Agent Gateway — REST + SSE API for agent-to-agent communication.

Provides skill discovery, invocation, and streaming endpoints designed
for external AI agents to discover and use dataToAi capabilities.
"""

from __future__ import annotations

import json
import logging
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.agent_schemas import SkillInvokeRequest, SkillInvokeResponse
from app.api.auth import get_auth_context_optional, get_auth_context_required
from app.db import get_db
from app.models import DatasetEntity, SessionEntity
from app.services.auth_service import AuthContext
from app.skills.base import SkillCategory, SkillContext

logger = logging.getLogger(__name__)

agent_gw = APIRouter(prefix="/agent-api/v1", tags=["agent-gateway"])


def _get_skill_registry():
    """Lazy import to avoid circular dependencies at module load."""
    from app.skills.setup import get_skill_registry
    return get_skill_registry()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
@agent_gw.get("/.well-known/agent.json")
async def agent_manifest():
    """Agent capability manifest — machine-readable discovery endpoint.

    External agents fetch this URL to learn what skills are available,
    what authentication is required, and how to connect.
    """
    registry = _get_skill_registry()
    return registry.capability_manifest()


@agent_gw.get("/skills")
async def list_skills(category: str | None = None):
    """List available skills with full metadata."""
    registry = _get_skill_registry()
    cat = SkillCategory(category) if category else None
    manifests = registry.list_skills(cat)
    return {"skills": [m.model_dump() for m in manifests]}


@agent_gw.get("/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get detailed skill manifest including examples."""
    registry = _get_skill_registry()
    manifest = registry.get_manifest(skill_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    return manifest.model_dump()


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------
@agent_gw.post("/skills/{skill_id}/invoke", response_model=SkillInvokeResponse)
async def invoke_skill(
    skill_id: str,
    payload: SkillInvokeRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Invoke a skill synchronously and return the result."""
    registry = _get_skill_registry()
    skill = registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    # Resolve or create session
    session_id = payload.session_id
    if not session_id:
        session_id = _ensure_session(db, auth_ctx)

    context = SkillContext(
        session_id=session_id,
        tenant_id=auth_ctx.tenant_id if auth_ctx else None,
        user_id=auth_ctx.user_id if auth_ctx else None,
    )

    t0 = perf_counter()
    result = await skill.execute(payload.params, context)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    return SkillInvokeResponse(
        skill_id=skill_id,
        success=result.success,
        data=result.data,
        error=result.error,
        execution_time_ms=elapsed_ms,
        metadata=result.metadata,
    )


@agent_gw.post("/skills/{skill_id}/stream")
async def stream_skill(
    skill_id: str,
    payload: SkillInvokeRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Invoke a skill with SSE streaming for long-running operations."""
    registry = _get_skill_registry()
    skill = registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    session_id = payload.session_id
    if not session_id:
        session_id = _ensure_session(db, auth_ctx)

    context = SkillContext(
        session_id=session_id,
        tenant_id=auth_ctx.tenant_id if auth_ctx else None,
        user_id=auth_ctx.user_id if auth_ctx else None,
    )

    async def event_generator():
        try:
            async for event in skill.execute_stream(payload.params, context):
                data = json.dumps(
                    {"type": event.type, "data": event.data}, ensure_ascii=False
                )
                yield f"data: {data}\n\n"
        except Exception as exc:
            logger.exception("skill stream error for %s", skill_id)
            err = json.dumps({"type": "error", "data": {"message": str(exc)}})
            yield f"data: {err}\n\n"
        finally:
            done = json.dumps({"type": "done", "data": {"skill_id": skill_id}})
            yield f"data: {done}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Session management for agent clients
# ---------------------------------------------------------------------------
@agent_gw.post("/sessions")
async def create_agent_session(
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Create a session for an agent client."""
    session_id = _ensure_session(db, auth_ctx)
    return {"session_id": session_id}


# ---------------------------------------------------------------------------
# Dataset operations (agent-friendly)
# ---------------------------------------------------------------------------
@agent_gw.get("/datasets")
async def list_datasets_for_agent(
    session_id: str | None = None,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """List datasets accessible to the agent."""
    query = db.query(DatasetEntity)
    if auth_ctx:
        query = query.filter(DatasetEntity.tenant_id == auth_ctx.tenant_id)
    if session_id:
        query = query.filter(DatasetEntity.session_id == session_id)
    datasets = query.order_by(DatasetEntity.created_at.desc()).all()

    return {
        "datasets": [
            {
                "dataset_id": d.dataset_id,
                "name": d.name,
                "file_type": d.file_type,
                "row_count": d.row_count,
                "column_count": d.column_count,
                "file_size_bytes": d.file_size_bytes,
                "status": d.status,
            }
            for d in datasets
        ]
    }


@agent_gw.get("/datasets/{dataset_id}")
async def get_dataset_for_agent(
    dataset_id: str,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
):
    """Get dataset metadata in a structured format for agents."""
    dataset = db.query(DatasetEntity).filter(
        DatasetEntity.dataset_id == dataset_id
    ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")

    if auth_ctx and dataset.tenant_id and dataset.tenant_id != auth_ctx.tenant_id:
        raise HTTPException(status_code=403, detail="access denied")

    columns = []
    if dataset.schema_json:
        try:
            columns = json.loads(dataset.schema_json)
        except json.JSONDecodeError:
            pass

    summary = None
    if dataset.summary_json:
        try:
            summary = json.loads(dataset.summary_json)
        except json.JSONDecodeError:
            pass

    return {
        "dataset_id": dataset.dataset_id,
        "name": dataset.name,
        "file_type": dataset.file_type,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "columns": columns,
        "summary": summary,
        "status": dataset.status,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_session(db: Session, auth_ctx: AuthContext | None) -> str:
    """Create a new session for the agent client."""
    session_id = str(uuid.uuid4())
    session = SessionEntity(
        session_id=session_id,
        influencer_name="agent-client",
        category="agent",
        tenant_id=auth_ctx.tenant_id if auth_ctx else None,
        owner_user_id=auth_ctx.user_id if auth_ctx else None,
    )
    db.add(session)
    db.commit()
    return session_id
