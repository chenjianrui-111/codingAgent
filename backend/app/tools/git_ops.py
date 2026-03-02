"""Git operation tools."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from app.tools.base import BaseTool, ToolContext, ToolResult


async def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


class GitStatusTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return "Show the working tree status (git status)."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        rc, out, err = await _run_git(["status"], context.workspace)
        return ToolResult(success=rc == 0, output=out or err)


class GitDiffTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return "Show changes in the working tree or staging area."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "Show staged changes", "default": False},
                "path": {"type": "string", "description": "Limit diff to a specific file path"},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        args = ["diff"]
        if params.get("staged"):
            args.append("--staged")
        if params.get("path"):
            args.extend(["--", params["path"]])
        rc, out, err = await _run_git(args, context.workspace)
        output = out[:8000] if out else "(no diff)"
        return ToolResult(success=rc == 0, output=output)


class GitCommitTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_commit"

    @property
    def description(self) -> str:
        return "Stage specified files and create a git commit. Push is NOT allowed."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to stage before committing",
                },
            },
            "required": ["message", "files"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        files = params.get("files", [])
        if not files:
            return ToolResult(False, "No files specified to commit")

        # Stage files
        rc, out, err = await _run_git(["add"] + files, context.workspace)
        if rc != 0:
            return ToolResult(False, f"git add failed: {err}")

        # Commit
        rc, out, err = await _run_git(
            ["commit", "-m", params["message"]], context.workspace
        )
        if rc != 0:
            return ToolResult(False, f"git commit failed: {err}")

        return ToolResult(True, out)


class GitLogTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return "Show recent git commits."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Number of commits to show", "default": 10},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        count = min(params.get("count", 10), 50)
        rc, out, err = await _run_git(
            ["log", f"-{count}", "--oneline", "--no-decorate"], context.workspace
        )
        return ToolResult(success=rc == 0, output=out or err or "(no commits)")


class GitBranchTool(BaseTool):
    @property
    def name(self) -> str:
        return "git_branch"

    @property
    def description(self) -> str:
        return "List, create, or switch git branches."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Branch name (omit to list branches)"},
                "create": {"type": "boolean", "description": "Create a new branch", "default": False},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        branch_name = params.get("name")

        if not branch_name:
            rc, out, err = await _run_git(["branch", "-a"], context.workspace)
            return ToolResult(success=rc == 0, output=out or err)

        if params.get("create"):
            rc, out, err = await _run_git(["checkout", "-b", branch_name], context.workspace)
        else:
            rc, out, err = await _run_git(["checkout", branch_name], context.workspace)

        return ToolResult(success=rc == 0, output=out or err)
