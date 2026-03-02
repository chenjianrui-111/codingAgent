import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
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


app.include_router(api_router, prefix=settings.api_prefix)

# ---------------------------------------------------------------------------
# Serve frontend static build in production
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
