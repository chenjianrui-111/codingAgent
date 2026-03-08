"""Skill registry with discovery support."""

from __future__ import annotations

from app.skills.base import Skill, SkillCategory, SkillManifest


class SkillRegistry:
    """Central registry of skills available to external agents."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        manifest = skill.manifest()
        self._skills[manifest.skill_id] = skill

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def list_skills(self, category: SkillCategory | None = None) -> list[SkillManifest]:
        manifests = [s.manifest() for s in self._skills.values()]
        if category:
            manifests = [m for m in manifests if m.category == category]
        return manifests

    def get_manifest(self, skill_id: str) -> SkillManifest | None:
        skill = self._skills.get(skill_id)
        return skill.manifest() if skill else None

    def capability_manifest(self) -> dict:
        """Full agent capability manifest for discovery by external agents."""
        return {
            "agent_name": "dataToAi",
            "version": "1.0.0",
            "description": (
                "AI-powered data analysis and code generation agent. "
                "Upload datasets, run natural language analysis, generate "
                "visualizations, and execute Python code in a stateful kernel."
            ),
            "skills": [s.manifest().model_dump() for s in self._skills.values()],
            "categories": sorted(
                set(s.manifest().category.value for s in self._skills.values())
            ),
            "auth_methods": ["bearer_token", "api_key"],
            "transport": ["rest", "sse", "mcp"],
        }
