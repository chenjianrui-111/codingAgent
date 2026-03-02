from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.repositories.agent_repo import AgentRepository
from app.services.auth_service import AuthContext, AuthService


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def get_auth_context_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext | None:
    token = _extract_bearer_token(authorization)
    if not token:
        if settings.auth_required:
            raise HTTPException(status_code=401, detail="missing bearer token")
        return None

    service = AuthService(AgentRepository(db))
    ctx = service.get_auth_context(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return ctx


def get_auth_context_required(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    service = AuthService(AgentRepository(db))
    ctx = service.get_auth_context(token)
    if not ctx:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return ctx
