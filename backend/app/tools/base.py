"""Base classes for the tool system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable


@dataclass
class ToolResult:
    success: bool
    output: str
    metadata: dict[str, Any] | None = None


@dataclass
class ToolContext:
    session_id: str
    run_id: str
    workspace: str  # Sandboxed workspace root
    approval_callback: Callable[..., Awaitable[bool]] | None = None


class BaseTool(ABC):
    """Abstract base for all LLM-callable tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        ...

    def to_claude_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    # ------------------------------------------------------------------
    # Path safety helper
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_safe_path(relative_path: str, workspace: str) -> str:
        """Resolve *relative_path* within *workspace*, preventing sandbox escape."""
        ws = Path(workspace).resolve()
        resolved = (ws / relative_path).resolve()
        if not str(resolved).startswith(str(ws)):
            raise PermissionError(f"Path escapes sandbox: {relative_path}")
        return str(resolved)


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def all_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def claude_tool_definitions(self) -> list[dict[str, Any]]:
        return [t.to_claude_tool() for t in self._tools.values()]
