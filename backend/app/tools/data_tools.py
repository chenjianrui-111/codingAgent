"""Data analysis tools for the AI agent.

Provides tools that the LLM agent can invoke during data analysis:
- execute_python: Run Python code in a stateful kernel
- analyze_dataset: Get schema, stats, and sample data for a dataset
- generate_chart: Generate a visualization and return as base64
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.tools.base import BaseTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class ExecutePythonTool(BaseTool):
    """Execute Python code in a stateful per-session kernel.

    The kernel persists variables, imports, and DataFrames across calls,
    enabling multi-step data analysis workflows.
    """

    @property
    def name(self) -> str:
        return "execute_python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a stateful kernel. Variables and imports persist across calls. "
            "Pre-imported: pandas (pd), numpy (np), matplotlib.pyplot (plt). "
            "Use this for data loading, transformation, analysis, and visualization. "
            "When creating charts, use plt.show() or plt.savefig() -- figures are captured automatically. "
            "Print results with print() or return a value for display."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute. Use pandas for data manipulation, matplotlib/seaborn for charts.",
                },
            },
            "required": ["code"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.services.python_kernel_service import kernel_manager

        code = params.get("code", "")
        if not code.strip():
            return ToolResult(False, "No code provided")

        # Security: block dangerous imports/operations
        dangerous = ["os.system", "subprocess", "shutil.rmtree", "__import__('os')", "exec(", "eval("]
        code_lower = code.lower()
        for d in dangerous:
            if d.lower() in code_lower:
                return ToolResult(False, f"Blocked: {d} is not allowed in data analysis context")

        try:
            result = await kernel_manager.execute(
                session_id=context.session_id,
                code=code,
            )
        except Exception as e:
            logger.exception("Kernel execution error")
            return ToolResult(False, f"Kernel error: {e}")

        # Build output
        parts = []
        if result.stdout:
            parts.append(f"--- stdout ---\n{result.stdout}")
        if result.display:
            parts.append(f"--- result ---\n{result.display}")
        if result.stderr and not result.success:
            parts.append(f"--- error ---\n{result.stderr}")
        if result.figures:
            parts.append(f"--- figures ---\n{len(result.figures)} chart(s) generated")
            for i, fig in enumerate(result.figures):
                # Include a truncated preview of the base64 data
                parts.append(f"  Figure {i+1}: [base64 PNG, {len(fig.get('data_base64', ''))} chars]")

        output = "\n".join(parts) if parts else "(no output)"
        output += f"\n[execution_time: {result.execution_time_ms}ms]"

        metadata = {}
        if result.figures:
            metadata["figures"] = result.figures

        return ToolResult(
            success=result.success,
            output=output[:8000],
            metadata=metadata,
        )


class AnalyzeDatasetTool(BaseTool):
    """Inspect a dataset's schema, statistics, and sample rows."""

    @property
    def name(self) -> str:
        return "analyze_dataset"

    @property
    def description(self) -> str:
        return (
            "Get detailed information about a loaded dataset including column types, "
            "descriptive statistics, missing values, and sample rows. "
            "Use this FIRST before writing analysis code to understand the data structure."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dataset_id": {
                    "type": "string",
                    "description": "The dataset ID to analyze",
                },
            },
            "required": ["dataset_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        dataset_id = params.get("dataset_id", "")
        if not dataset_id:
            return ToolResult(False, "dataset_id is required")

        # The dataset context is injected via the data agent; we return a message
        # prompting the agent to use the context already in the system prompt
        return ToolResult(
            True,
            f"Dataset {dataset_id} schema and statistics are available in the system context above. "
            "Use execute_python to load and analyze the data with pandas.",
        )


class GenerateChartTool(BaseTool):
    """Generate a data visualization."""

    @property
    def name(self) -> str:
        return "generate_chart"

    @property
    def description(self) -> str:
        return (
            "Generate a chart/visualization from data. Specify the chart type and the Python code "
            "to produce it. The code should use matplotlib or seaborn. Figures are captured automatically. "
            "Use this when the user asks for visual analysis."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "description": "Type of chart (e.g. bar, line, scatter, histogram, pie, heatmap, box)",
                },
                "code": {
                    "type": "string",
                    "description": "Python code using matplotlib/seaborn to create the chart",
                },
                "title": {
                    "type": "string",
                    "description": "Chart title",
                },
            },
            "required": ["chart_type", "code"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.services.python_kernel_service import kernel_manager

        code = params.get("code", "")
        chart_type = params.get("chart_type", "unknown")
        title = params.get("title", "")

        if not code.strip():
            return ToolResult(False, "No chart code provided")

        # Wrap code with figure setup if not already creating a figure
        if "plt.figure" not in code and "fig," not in code and "fig =" not in code:
            code = f"import matplotlib.pyplot as plt\nplt.figure(figsize=(10, 6))\n{code}"

        if title and "plt.title" not in code:
            code += f"\nplt.title({title!r})"

        if "plt.tight_layout" not in code:
            code += "\nplt.tight_layout()"

        try:
            result = await kernel_manager.execute(
                session_id=context.session_id,
                code=code,
            )
        except Exception as e:
            return ToolResult(False, f"Chart generation error: {e}")

        if not result.success:
            return ToolResult(False, f"Chart code error:\n{result.stderr}")

        if not result.figures:
            return ToolResult(
                False,
                "No figures were generated. Make sure to call plt.show() or create a figure.",
            )

        output = f"Generated {chart_type} chart ({len(result.figures)} figure(s))"
        if result.stdout:
            output += f"\n{result.stdout}"

        return ToolResult(
            success=True,
            output=output,
            metadata={"figures": result.figures, "chart_type": chart_type},
        )


class QueryDataTool(BaseTool):
    """Query data using natural language converted to pandas operations."""

    @property
    def name(self) -> str:
        return "query_data"

    @property
    def description(self) -> str:
        return (
            "Execute a pandas query or SQL-like operation on the loaded dataset. "
            "Provide a pandas expression (e.g., df.groupby('col').mean()) or a "
            "filter expression (e.g., df[df['age'] > 30])."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Pandas expression to evaluate (e.g., 'df.groupby(\"city\").sales.sum()')",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable description of what this query does",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        from app.services.python_kernel_service import kernel_manager

        expression = params.get("expression", "")
        if not expression.strip():
            return ToolResult(False, "No expression provided")

        # Wrap in a print/display call
        code = f"_result = {expression}\nprint(type(_result).__name__)\n_result"

        try:
            result = await kernel_manager.execute(
                session_id=context.session_id,
                code=code,
            )
        except Exception as e:
            return ToolResult(False, f"Query error: {e}")

        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.display:
            parts.append(result.display)
        if not result.success:
            parts.append(f"Error: {result.stderr}")

        return ToolResult(
            success=result.success,
            output="\n".join(parts)[:8000] if parts else "(no result)",
        )
