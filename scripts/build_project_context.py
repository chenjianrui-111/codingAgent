#!/usr/bin/env python3
"""Build project-level graph and vector context for the coding agent."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal  # noqa: E402
from app.repositories.context_repo import ContextRepository  # noqa: E402
from app.services.project_context_service import ProjectContextManager  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--repo", default="codingAgent")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--module-path", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        manager = ProjectContextManager(ContextRepository(db))
        stats = manager.initialize_project(
            workspace=args.workspace,
            repo_name=args.repo,
            branch_name=args.branch,
            module_path=args.module_path,
        )
        print(
            f"scoped={stats.scoped_workspace} indexed_files={stats.indexed_files} "
            f"graph_nodes={stats.graph_nodes} graph_edges={stats.graph_edges} vectors={stats.vectors}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
