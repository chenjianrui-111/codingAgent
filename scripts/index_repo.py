#!/usr/bin/env python3
"""Index source code into OceanBase code_chunks table (MVP version)."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import pymysql

SUPPORTED_SUFFIX = {".py", ".ts", ".tsx", ".js", ".java", ".md", ".yaml", ".yml", ".json"}


def chunk_text(content: str, max_lines: int = 80) -> list[tuple[int, int, str]]:
    lines = content.splitlines()
    chunks: list[tuple[int, int, str]] = []
    for idx in range(0, len(lines), max_lines):
        part = lines[idx : idx + max_lines]
        start_line = idx + 1
        end_line = idx + len(part)
        chunks.append((start_line, end_line, "\n".join(part)))
    return chunks


def detect_language(path: Path) -> str:
    return path.suffix.lstrip(".") or "text"


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--repo", default="local_repo")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--host", default=os.getenv("OCEANBASE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OCEANBASE_PORT", "2881")))
    parser.add_argument("--user", default=os.getenv("OCEANBASE_USER", "root@test"))
    parser.add_argument("--password", default=os.getenv("OCEANBASE_PASSWORD", ""))
    parser.add_argument("--database", default=os.getenv("OCEANBASE_DATABASE", "coding_agent"))
    args = parser.parse_args()

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=True,
    )

    workspace = Path(args.workspace).resolve()
    inserted_files = 0
    inserted_chunks = 0

    with conn.cursor() as cur:
        for path in workspace.rglob("*"):
            if not path.is_file() or path.suffix not in SUPPORTED_SUFFIX:
                continue
            rel_path = str(path.relative_to(workspace))
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue

            file_sha = sha256_text(content)
            language = detect_language(path)

            cur.execute(
                """
                INSERT INTO repo_files (repo_name, branch_name, file_path, file_sha, language, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    file_sha = VALUES(file_sha),
                    language = VALUES(language),
                    content = VALUES(content)
                """,
                (args.repo, args.branch, rel_path, file_sha, language, content),
            )

            cur.execute(
                "DELETE FROM code_chunks WHERE repo_name=%s AND branch_name=%s AND file_path=%s",
                (args.repo, args.branch, rel_path),
            )

            for start_line, end_line, chunk in chunk_text(content):
                if not chunk.strip():
                    continue
                cur.execute(
                    """
                    INSERT INTO code_chunks (repo_name, branch_name, file_path, chunk_text, start_line, end_line)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (args.repo, args.branch, rel_path, chunk, start_line, end_line),
                )
                inserted_chunks += 1

            inserted_files += 1

    conn.close()
    print(f"indexed files={inserted_files}, chunks={inserted_chunks}, workspace={workspace}")


if __name__ == "__main__":
    main()
