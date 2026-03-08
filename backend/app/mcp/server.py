"""MCP server implementation using FastMCP.

Registers each Skill from the SkillRegistry as an MCP tool, and
exposes datasets as MCP resources.  Designed to be mounted as a
sub-application inside the main FastAPI app.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.skills.base import SkillContext

logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """Build and return a configured FastMCP server instance."""

    mcp = FastMCP(
        name="dataToAi",
        instructions=(
            "AI-powered data analysis and code generation agent. "
            "Use data.* tools for dataset operations and code.* tools "
            "for Python execution.  Create a session first, then upload "
            "datasets and run analyses."
        ),
    )

    # ------------------------------------------------------------------
    # Register skills as MCP tools
    # ------------------------------------------------------------------
    _register_skill_tools(mcp)

    # ------------------------------------------------------------------
    # Register dataset resources
    # ------------------------------------------------------------------
    _register_dataset_resources(mcp)

    # ------------------------------------------------------------------
    # Register prompt templates
    # ------------------------------------------------------------------
    _register_prompts(mcp)

    return mcp


# ------------------------------------------------------------------
# Skill → MCP tool bridge
# ------------------------------------------------------------------
def _register_skill_tools(mcp: FastMCP) -> None:
    """Convert each registered Skill into an MCP tool."""

    from app.skills.setup import get_skill_registry

    registry = get_skill_registry()

    for manifest in registry.list_skills():
        skill = registry.get(manifest.skill_id)
        if not skill:
            continue

        # Build parameter descriptions for the MCP tool
        props = manifest.input_schema.get("properties", {})
        required = manifest.input_schema.get("required", [])

        # We create a closure to capture the current skill reference
        _skill = skill
        _skill_id = manifest.skill_id

        @mcp.tool(
            name=_skill_id,
            description=manifest.description,
        )
        async def _tool_handler(
            # MCP passes params as kwargs; we accept **kwargs and forward
            __bound_skill=_skill,
            __bound_id=_skill_id,
            **kwargs: Any,
        ) -> str:
            context = SkillContext(
                session_id=kwargs.pop("session_id", "mcp-default"),
                tenant_id=kwargs.pop("tenant_id", None),
                user_id=kwargs.pop("user_id", None),
            )
            result = await __bound_skill.execute(kwargs, context)
            return json.dumps(
                {"success": result.success, "data": result.data, "error": result.error},
                ensure_ascii=False,
                default=str,
            )


# ------------------------------------------------------------------
# Dataset resources
# ------------------------------------------------------------------
def _register_dataset_resources(mcp: FastMCP) -> None:

    @mcp.resource("datasets://list")
    async def list_datasets_resource() -> str:
        """List all available datasets."""
        from app.db import SessionLocal
        from app.models import DatasetEntity

        db = SessionLocal()
        try:
            datasets = db.query(DatasetEntity).order_by(
                DatasetEntity.created_at.desc()
            ).limit(50).all()
            items = [
                {
                    "dataset_id": d.dataset_id,
                    "name": d.name,
                    "file_type": d.file_type,
                    "row_count": d.row_count,
                    "column_count": d.column_count,
                    "status": d.status,
                }
                for d in datasets
            ]
            return json.dumps({"datasets": items}, ensure_ascii=False)
        finally:
            db.close()

    @mcp.resource("dataset://{dataset_id}")
    async def get_dataset_resource(dataset_id: str) -> str:
        """Get dataset metadata including schema and statistics."""
        from app.db import SessionLocal
        from app.models import DatasetEntity

        db = SessionLocal()
        try:
            dataset = db.query(DatasetEntity).filter(
                DatasetEntity.dataset_id == dataset_id
            ).first()
            if not dataset:
                return json.dumps({"error": f"Dataset {dataset_id} not found"})

            result: dict[str, Any] = {
                "dataset_id": dataset.dataset_id,
                "name": dataset.name,
                "file_type": dataset.file_type,
                "row_count": dataset.row_count,
                "column_count": dataset.column_count,
                "status": dataset.status,
            }
            if dataset.schema_json:
                try:
                    result["columns"] = json.loads(dataset.schema_json)
                except json.JSONDecodeError:
                    pass
            if dataset.summary_json:
                try:
                    result["summary"] = json.loads(dataset.summary_json)
                except json.JSONDecodeError:
                    pass

            return json.dumps(result, ensure_ascii=False, default=str)
        finally:
            db.close()


# ------------------------------------------------------------------
# Prompt templates
# ------------------------------------------------------------------
def _register_prompts(mcp: FastMCP) -> None:

    @mcp.prompt("analyze-dataset")
    async def analyze_dataset_prompt(dataset_id: str, question: str) -> str:
        """Pre-built prompt for dataset analysis."""
        return (
            f"Please analyze the dataset with ID '{dataset_id}'. "
            f"Question: {question}\n\n"
            "Steps:\n"
            "1. First use the data.upload or data.auto_eda tool to understand the data\n"
            "2. Then use data.analyze to answer the question\n"
            "3. Generate any relevant visualizations using data.visualize"
        )

    @mcp.prompt("quick-eda")
    async def quick_eda_prompt(dataset_id: str) -> str:
        """Pre-built prompt for quick exploratory data analysis."""
        return (
            f"Run a comprehensive Exploratory Data Analysis on dataset '{dataset_id}'. "
            "Use the data.auto_eda tool to get a full overview including:\n"
            "- Data shape and types\n"
            "- Missing values analysis\n"
            "- Descriptive statistics\n"
            "- Distribution charts\n"
            "- Correlation analysis"
        )
