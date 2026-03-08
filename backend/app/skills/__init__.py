"""Skill system for agent-to-agent interoperability.

Builds on top of the existing BaseTool layer, adding rich metadata
(categories, versioning, examples, output schemas) so that external
AI agents can discover, understand, and invoke capabilities.
"""

from app.skills.base import (
    Skill,
    SkillCategory,
    SkillContext,
    SkillEvent,
    SkillExample,
    SkillManifest,
    SkillResult,
)
from app.skills.registry import SkillRegistry

__all__ = [
    "Skill",
    "SkillCategory",
    "SkillContext",
    "SkillEvent",
    "SkillExample",
    "SkillManifest",
    "SkillRegistry",
    "SkillResult",
]
