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


def _extract_api_key(authorization: str | None) -> str | None:
    """Extract API key from 'ApiKey ak_...' authorization header."""
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "apikey" or not parts[1].strip():
        return None
    value = parts[1].strip()
    if not value.startswith("ak_"):
        return None
    return value


def _resolve_auth_context(authorization: str | None, db: Session) -> AuthContext | None:
    """Try bearer token first, then API key."""
    service = AuthService(AgentRepository(db))

    # Try bearer token
    token = _extract_bearer_token(authorization)
    if token:
        return service.get_auth_context(token)

    # Try API key
    api_key = _extract_api_key(authorization)
    if api_key:
        return service.validate_api_key(api_key)

    return None


def get_auth_context_optional(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext | None:
    if not authorization:
        if settings.auth_required:
            raise HTTPException(status_code=401, detail="missing authorization")
        return None

    ctx = _resolve_auth_context(authorization, db)
    if not ctx:
        raise HTTPException(status_code=401, detail="invalid or expired credentials")
    return ctx


def get_auth_context_required(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization")

    ctx = _resolve_auth_context(authorization, db)
    if not ctx:
        raise HTTPException(status_code=401, detail="invalid or expired credentials")
    return ctx
