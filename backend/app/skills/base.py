"""Core skill abstractions for agent-to-agent interoperability.

A Skill wraps one or more BaseTool instances with richer metadata —
input/output JSON Schemas, usage examples, versioning, and streaming
support — so that external agents can discover and invoke capabilities
without prior knowledge of the internal tool layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel


class SkillCategory(str, Enum):
    DATA = "data"
    CODE = "code"
    FILE = "file"
    SHELL = "shell"
    GIT = "git"
    RAG = "rag"


class SkillExample(BaseModel):
    """A concrete input/output example that helps agents understand usage."""

    description: str
    input: dict[str, Any]
    expected_output_summary: str


class SkillManifest(BaseModel):
    """Machine-readable description of a skill's capabilities."""

    skill_id: str                                   # e.g. "data.analyze"
    version: str                                    # semver: "1.0.0"
    name: str                                       # human-readable name
    description: str                                # detailed description for agents
    category: SkillCategory
    input_schema: dict[str, Any]                    # JSON Schema
    output_schema: dict[str, Any]                   # JSON Schema for the result
    examples: list[SkillExample] = []
    prerequisites: list[str] = []                   # skill_ids that should run first
    estimated_duration_ms: int | None = None
    is_streaming: bool = False
    requires_session: bool = True
    requires_dataset: bool = False
    tags: list[str] = []


@dataclass
class SkillContext:
    """Runtime context passed to every skill invocation."""

    session_id: str
    tenant_id: str | None = None
    user_id: str | None = None
    workspace: str = "/tmp/codex-sandbox"


@dataclass
class SkillResult:
    """Synchronous result returned by a skill."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillEvent:
    """A single event in a streaming skill invocation."""

    type: str   # "status" | "progress" | "result" | "error" | "figure" | "code"
    data: dict[str, Any] = field(default_factory=dict)


class Skill(ABC):
    """Abstract skill — the agent-facing wrapper around internal tools."""

    @abstractmethod
    def manifest(self) -> SkillManifest:
        """Return machine-readable metadata about this skill."""
        ...

    @abstractmethod
    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        """Execute the skill synchronously and return a result."""
        ...

    async def execute_stream(
        self, params: dict[str, Any], context: SkillContext
    ) -> AsyncIterator[SkillEvent]:
        """Execute the skill with streaming.  Override for true streaming."""
        result = await self.execute(params, context)
        yield SkillEvent(type="result", data={"success": result.success, **result.data})
