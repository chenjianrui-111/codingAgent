"""Code execution and codebase analysis skills."""

from __future__ import annotations

import logging
from typing import Any

from app.skills.base import (
    Skill,
    SkillCategory,
    SkillContext,
    SkillExample,
    SkillManifest,
    SkillResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# code.execute
# ---------------------------------------------------------------------------
class CodeExecuteSkill(Skill):
    """Execute Python code in a stateful kernel."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="code.execute",
            version="1.0.0",
            name="Execute Python Code",
            description=(
                "Execute Python code in a stateful per-session kernel. Variables, "
                "imports, and DataFrames persist across calls. Pre-imported: "
                "pandas (pd), numpy (np), matplotlib.pyplot (plt). Returns stdout, "
                "display values, and any generated figures as base64 PNG."
            ),
            category=SkillCategory.CODE,
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": (
                            "Python code to execute. Use pandas for data, "
                            "matplotlib/seaborn for charts."
                        ),
                    },
                },
                "required": ["code"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "stdout": {"type": "string"},
                    "display": {"type": "string"},
                    "figures": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "data_base64": {"type": "string"},
                                "url": {"type": "string"},
                            },
                        },
                    },
                    "execution_time_ms": {"type": "integer"},
                },
            },
            examples=[
                SkillExample(
                    description="Compute basic statistics",
                    input={"code": "import pandas as pd\ndf = pd.DataFrame({'a': [1,2,3]})\nprint(df.describe())"},
                    expected_output_summary="Descriptive statistics of column 'a' printed to stdout",
                ),
                SkillExample(
                    description="Generate a simple chart",
                    input={"code": "import matplotlib.pyplot as plt\nplt.plot([1,2,3],[4,5,6])\nplt.title('Test')\nplt.show()"},
                    expected_output_summary="One figure generated as base64 PNG",
                ),
            ],
            is_streaming=False,
            requires_session=True,
            tags=["python", "execution", "kernel", "stateful"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        from app.tools.data_tools import ExecutePythonTool
        from app.tools.base import ToolContext

        tool = ExecutePythonTool()
        tool_ctx = ToolContext(
            session_id=context.session_id,
            run_id="skill-invoke",
            workspace=context.workspace,
        )
        result = await tool.execute(params, tool_ctx)

        if not result.success:
            return SkillResult(success=False, error=result.output)

        return SkillResult(
            success=True,
            data={
                "output": result.output,
                "figures": (result.metadata or {}).get("figures", []),
            },
        )


# ---------------------------------------------------------------------------
# code.search_codebase
# ---------------------------------------------------------------------------
class CodebaseSearchSkill(Skill):
    """Search the indexed codebase using RAG."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="code.search_codebase",
            version="1.0.0",
            name="Search Codebase",
            description=(
                "Semantic search over an indexed codebase using the RAG pipeline. "
                "Returns ranked code snippets, functions, classes, and files relevant "
                "to the query. Useful for understanding code structure and finding "
                "implementations."
            ),
            category=SkillCategory.RAG,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "current_file": {
                        "type": "string",
                        "description": "Optional current file path for context-aware ranking",
                    },
                },
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "Ranked code context matching the query",
                    },
                },
            },
            examples=[
                SkillExample(
                    description="Find authentication implementation",
                    input={"query": "How does user authentication work?"},
                    expected_output_summary="Code snippets from auth_service.py and auth.py",
                ),
            ],
            is_streaming=False,
            requires_session=True,
            tags=["search", "rag", "code", "semantic"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        from app.tools.rag_tool import SearchCodebaseTool
        from app.tools.base import ToolContext

        tool = SearchCodebaseTool()
        tool_ctx = ToolContext(
            session_id=context.session_id,
            run_id="skill-invoke",
            workspace=context.workspace,
        )
        result = await tool.execute(params, tool_ctx)

        if not result.success:
            return SkillResult(success=False, error=result.output)

        return SkillResult(
            success=True,
            data={"context": result.output},
        )
