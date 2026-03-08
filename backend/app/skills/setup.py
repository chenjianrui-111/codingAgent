"""Skill registry setup — initializes and provides the global registry."""

from __future__ import annotations

from app.skills.registry import SkillRegistry

_registry: SkillRegistry | None = None


def create_skill_registry() -> SkillRegistry:
    """Create a SkillRegistry pre-loaded with all built-in skills."""
    from app.skills.data_skills import (
        DataAnalyzeSkill,
        DataAutoEDASkill,
        DataQuerySkill,
        DataUploadSkill,
        DataVisualizeSkill,
    )
    from app.skills.code_skills import (
        CodeExecuteSkill,
        CodebaseSearchSkill,
    )

    registry = SkillRegistry()

    # Data skills
    for skill in [
        DataUploadSkill(),
        DataAnalyzeSkill(),
        DataVisualizeSkill(),
        DataAutoEDASkill(),
        DataQuerySkill(),
    ]:
        registry.register(skill)

    # Code skills
    for skill in [
        CodeExecuteSkill(),
        CodebaseSearchSkill(),
    ]:
        registry.register(skill)

    return registry


def get_skill_registry() -> SkillRegistry:
    """Get or lazily create the global skill registry singleton."""
    global _registry
    if _registry is None:
        _registry = create_skill_registry()
    return _registry
