import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.data_routes import data_router
from app.api.agent_gateway import agent_gw
from app.core.config import settings
from app.db import Base, engine, ensure_sqlite_compat_schema


app = FastAPI(title=settings.app_name)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CORS – allow the Vite dev server and any local frontends
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        Base.metadata.create_all(bind=engine)
        ensure_sqlite_compat_schema()
    except Exception as exc:  # pragma: no cover
        logger.warning("database init skipped: %s", exc)

    # Dev token bootstrap
    try:
        from app.db import SessionLocal
        from app.repositories.agent_repo import AgentRepository
        from app.services.auth_service import AuthService

        db = SessionLocal()
        try:
            AuthService(AgentRepository(db)).ensure_dev_token()
            db.commit()
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("dev token bootstrap skipped: %s", exc)

    # Pre-warm the skill registry
    try:
        from app.skills.setup import get_skill_registry
        registry = get_skill_registry()
        logger.info("skill registry loaded: %d skills", len(registry.list_skills()))
    except Exception as exc:  # pragma: no cover
        logger.warning("skill registry init skipped: %s", exc)

    # Mount MCP server (optional — requires `mcp` package)
    try:
        from app.mcp.routes import create_mcp_app
        mcp_app = create_mcp_app()
        app.mount("/mcp", mcp_app)
        logger.info("MCP server mounted at /mcp")
    except ImportError:
        logger.info("MCP server not available (install `mcp` package to enable)")
    except Exception as exc:  # pragma: no cover
        logger.warning("MCP server init skipped: %s", exc)


app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(data_router, prefix=settings.api_prefix)
app.include_router(agent_gw)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Clean up kernel processes on app shutdown."""
    try:
        from app.services.python_kernel_service import kernel_manager
        await kernel_manager.shutdown_all()
    except Exception as exc:  # pragma: no cover
        logger.warning("kernel shutdown error: %s", exc)


# ---------------------------------------------------------------------------
# Serve frontend static build in production
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
