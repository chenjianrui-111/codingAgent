"""Workspace sandboxing service."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class SandboxService:
    """Manage isolated workspace directories for agent runs."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.sandbox_workspace_root)

    def create_workspace(self, session_id: str, source_path: str | None = None) -> str:
        """Create (or reuse) a sandboxed workspace for a session.

        If *source_path* points to a git repo it will be cloned; otherwise the
        directory is copied.  When no *source_path* is given an empty workspace
        is created.
        """
        ws = self.root / session_id / "workspace"
        if ws.exists():
            return str(ws)

        ws.mkdir(parents=True, exist_ok=True)

        if source_path:
            src = Path(source_path)
            if not src.exists():
                logger.warning("source_path %s does not exist", source_path)
                return str(ws)

            if (src / ".git").is_dir():
                # Clone the repo – depth=1 for speed
                try:
                    subprocess.run(
                        ["git", "clone", "--depth", "1", str(src), str(ws)],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                    return str(ws)
                except Exception:
                    logger.warning("git clone failed, falling back to copy", exc_info=True)

            # Fallback: copy tree
            shutil.rmtree(ws, ignore_errors=True)
            shutil.copytree(src, ws, dirs_exist_ok=True)

        return str(ws)

    def destroy_workspace(self, session_id: str) -> None:
        """Remove an entire session sandbox."""
        target = self.root / session_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            logger.info("Destroyed sandbox for session %s", session_id)

    def workspace_path(self, session_id: str) -> str | None:
        """Return the workspace path if it exists, else None."""
        ws = self.root / session_id / "workspace"
        return str(ws) if ws.exists() else None
