#!/usr/bin/env python3
"""Build project context (structure + AST + dependency graph + knowledge chunks)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import SessionLocal  # noqa: E402
from app.services.context_service import ContextIndexer  # noqa: E402
from app.repositories.context_repo import ContextRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--repo", default="codingAgent")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        indexer = ContextIndexer(ContextRepository(db))
        stats = indexer.index_workspace(
            workspace=args.workspace,
            repo_name=args.repo,
            branch_name=args.branch,
        )
        print(
            f"indexed files={stats.files}, symbols={stats.symbols}, "
            f"dependencies={stats.dependencies}, chunks={stats.chunks}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
