"""Sandboxed shell execution tool."""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from app.core.config import settings
from app.tools.base import BaseTool, ToolContext, ToolResult


class ShellTool(BaseTool):
    @property
    def name(self) -> str:
        return "execute_shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command in the workspace directory. "
            "Commands are validated against an allowlist for safety. "
            f"Allowed commands: {settings.allowed_shell_commands}"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 120)",
                    "default": 120,
                },
            },
            "required": ["command"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        command = params["command"]
        timeout = min(params.get("timeout", 120), 120)

        # Validate the executable against the allowlist
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return ToolResult(False, f"Invalid command syntax: {e}")

        if not parts:
            return ToolResult(False, "Empty command")

        executable = parts[0]
        allowed = {c.strip() for c in settings.allowed_shell_commands.split(",")}
        if executable not in allowed:
            return ToolResult(
                False,
                f"Command '{executable}' not in allowlist. Allowed: {', '.join(sorted(allowed))}",
            )

        # Build a sandboxed environment
        env = self._sandboxed_env(context.workspace)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=context.workspace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(False, f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, f"Execution error: {e}")

        stdout_str = stdout.decode("utf-8", errors="replace")[:8000]
        stderr_str = stderr.decode("utf-8", errors="replace")[:2000]

        output = f"exit_code={proc.returncode}\n"
        if stdout_str:
            output += f"--- stdout ---\n{stdout_str}\n"
        if stderr_str:
            output += f"--- stderr ---\n{stderr_str}\n"

        return ToolResult(success=proc.returncode == 0, output=output)

    @staticmethod
    def _sandboxed_env(workspace: str) -> dict[str, str]:
        """Return a restricted environment dict for subprocess execution."""
        safe_keys = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL"}
        env = {k: v for k, v in os.environ.items() if k in safe_keys}
        env["HOME"] = workspace
        return env
