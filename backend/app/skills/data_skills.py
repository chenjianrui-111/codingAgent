"""Data analysis skills — agent-facing wrappers around data tools and services.

Each skill wraps existing internal tools (ExecutePythonTool, GenerateChartTool, etc.)
and services (DataService, DataAgentRunner, AutoEDAService) with rich metadata
for external agent discovery and invocation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.skills.base import (
    Skill,
    SkillCategory,
    SkillContext,
    SkillEvent,
    SkillExample,
    SkillManifest,
    SkillResult,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.upload
# ---------------------------------------------------------------------------
class DataUploadSkill(Skill):
    """Upload and profile a dataset file."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="data.upload",
            version="1.0.0",
            name="Upload Dataset",
            description=(
                "Upload a CSV, Excel, JSON, or Parquet file and automatically "
                "profile its schema, statistics, and sample rows. Returns a "
                "dataset_id that can be used with other data.* skills."
            ),
            category=SkillCategory.DATA,
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Local path to the file to upload",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Original filename (used to detect file type)",
                    },
                },
                "required": ["file_path", "filename"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "string"},
                    "name": {"type": "string"},
                    "file_type": {"type": "string"},
                    "row_count": {"type": "integer"},
                    "column_count": {"type": "integer"},
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "dtype": {"type": "string"},
                                "null_count": {"type": "integer"},
                                "unique_count": {"type": "integer"},
                            },
                        },
                    },
                },
            },
            examples=[
                SkillExample(
                    description="Upload a CSV sales report",
                    input={"file_path": "/data/sales.csv", "filename": "sales.csv"},
                    expected_output_summary=(
                        "Returns dataset_id, schema with 8 columns, 1200 rows"
                    ),
                ),
            ],
            is_streaming=False,
            requires_session=True,
            requires_dataset=False,
            tags=["upload", "ingest", "profile"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        from app.services.data_service import DataService

        file_path = params.get("file_path", "")
        filename = params.get("filename", "")
        if not file_path or not filename:
            return SkillResult(success=False, error="file_path and filename are required")

        try:
            service = DataService()
            with open(file_path, "rb") as f:
                profile = service.ingest_file(
                    file_data=f,
                    filename=filename,
                    session_id=context.session_id,
                    tenant_id=context.tenant_id,
                )
        except (ValueError, FileNotFoundError) as exc:
            return SkillResult(success=False, error=str(exc))

        return SkillResult(
            success=True,
            data={
                "dataset_id": profile.dataset_id,
                "name": profile.name,
                "file_type": profile.file_type,
                "file_size_bytes": profile.file_size_bytes,
                "row_count": profile.row_count,
                "column_count": profile.column_count,
                "columns": [
                    {
                        "name": c.name,
                        "dtype": c.dtype,
                        "nullable": c.nullable,
                        "unique_count": c.unique_count,
                        "null_count": c.null_count,
                        "min_value": c.min_value,
                        "max_value": c.max_value,
                        "mean_value": c.mean_value,
                    }
                    for c in profile.columns
                ],
            },
        )


# ---------------------------------------------------------------------------
# data.analyze
# ---------------------------------------------------------------------------
class DataAnalyzeSkill(Skill):
    """Run natural language data analysis on a dataset."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="data.analyze",
            version="1.0.0",
            name="Natural Language Data Analysis",
            description=(
                "Analyze a dataset using a natural language query. The AI agent "
                "generates and executes Python code (pandas/matplotlib), produces "
                "charts, and returns structured insights. Requires a dataset to be "
                "uploaded first via data.upload."
            ),
            category=SkillCategory.DATA,
            input_schema={
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "description": "ID of the dataset to analyze (from data.upload)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language analysis question",
                    },
                },
                "required": ["dataset_id", "query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "analysis_text": {"type": "string"},
                    "code_executed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
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
                },
            },
            examples=[
                SkillExample(
                    description="Analyze monthly sales trends",
                    input={
                        "dataset_id": "d-123",
                        "query": "Show monthly sales trends and identify the top-selling month",
                    },
                    expected_output_summary=(
                        "Line chart of monthly sales, text analysis identifying peak month"
                    ),
                ),
                SkillExample(
                    description="Find correlations between variables",
                    input={
                        "dataset_id": "d-123",
                        "query": "What are the strongest correlations in this dataset?",
                    },
                    expected_output_summary=(
                        "Correlation heatmap with top correlated pairs listed"
                    ),
                ),
            ],
            prerequisites=["data.upload"],
            is_streaming=True,
            requires_session=True,
            requires_dataset=True,
            estimated_duration_ms=30000,
            tags=["analysis", "nlq", "charts", "insights"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        """Synchronous execution — collects all streaming events into a result."""
        analysis_text_parts: list[str] = []
        code_parts: list[str] = []
        figures: list[dict] = []

        async for event in self.execute_stream(params, context):
            if event.type == "text_delta":
                analysis_text_parts.append(event.data.get("text", ""))
            elif event.type == "tool_call":
                code_parts.append(event.data.get("input", {}).get("code", ""))
            elif event.type == "figures":
                figures.extend(event.data.get("figures", []))
            elif event.type == "error":
                return SkillResult(success=False, error=event.data.get("message", "Unknown error"))

        return SkillResult(
            success=True,
            data={
                "analysis_text": "".join(analysis_text_parts),
                "code_executed": code_parts,
                "figures": figures,
            },
        )

    async def execute_stream(
        self, params: dict[str, Any], context: SkillContext
    ) -> AsyncIterator[SkillEvent]:
        from app.services.data_agent_service import DataAgentRunner
        from app.services.data_service import DataService
        from app.services.python_kernel_service import kernel_manager
        from app.db import SessionLocal
        from app.models import DatasetEntity

        dataset_id = params.get("dataset_id", "")
        query = params.get("query", "")
        if not dataset_id or not query:
            yield SkillEvent(type="error", data={"message": "dataset_id and query are required"})
            return

        # Fetch dataset from DB
        db = SessionLocal()
        try:
            dataset = db.query(DatasetEntity).filter(
                DatasetEntity.dataset_id == dataset_id
            ).first()
            if not dataset:
                yield SkillEvent(type="error", data={"message": f"Dataset {dataset_id} not found"})
                return

            # Build context
            dataset_context = DataService.build_dataset_context(
                name=dataset.name,
                schema_json=dataset.schema_json,
                summary_json=dataset.summary_json,
                sample_rows_json=dataset.sample_rows_json,
                row_count=dataset.row_count,
                column_count=dataset.column_count,
            )

            # Pre-load dataset into kernel
            from app.api.data_routes import _build_load_code
            load_code = _build_load_code(dataset)
            await kernel_manager.execute(context.session_id, load_code)
        finally:
            db.close()

        # Run agent stream
        runner = DataAgentRunner()
        async for event in runner.run_data_stream(
            session_id=context.session_id,
            query=query,
            dataset_context=dataset_context,
        ):
            yield SkillEvent(type=event.type, data=event.data)


# ---------------------------------------------------------------------------
# data.visualize
# ---------------------------------------------------------------------------
class DataVisualizeSkill(Skill):
    """Generate a chart from Python matplotlib/seaborn code."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="data.visualize",
            version="1.0.0",
            name="Generate Visualization",
            description=(
                "Generate a chart/visualization by executing matplotlib or seaborn "
                "code in a stateful Python kernel. The dataset should already be "
                "loaded into the kernel (via data.analyze or code.execute)."
            ),
            category=SkillCategory.DATA,
            input_schema={
                "type": "object",
                "properties": {
                    "chart_type": {
                        "type": "string",
                        "description": "Type of chart (bar, line, scatter, histogram, pie, heatmap, box)",
                    },
                    "code": {
                        "type": "string",
                        "description": "Python code using matplotlib/seaborn to create the chart",
                    },
                    "title": {
                        "type": "string",
                        "description": "Chart title (optional)",
                    },
                },
                "required": ["chart_type", "code"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string"},
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
                },
            },
            examples=[
                SkillExample(
                    description="Bar chart of category counts",
                    input={
                        "chart_type": "bar",
                        "code": "df['category'].value_counts().plot(kind='bar')\nplt.title('Category Distribution')\nplt.tight_layout()\nplt.show()",
                        "title": "Category Distribution",
                    },
                    expected_output_summary="Bar chart PNG as base64, 1 figure generated",
                ),
            ],
            is_streaming=False,
            requires_session=True,
            tags=["visualization", "chart", "matplotlib", "seaborn"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        from app.tools.data_tools import GenerateChartTool
        from app.tools.base import ToolContext

        tool = GenerateChartTool()
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
                "chart_type": params.get("chart_type", "unknown"),
                "output": result.output,
                "figures": (result.metadata or {}).get("figures", []),
            },
        )


# ---------------------------------------------------------------------------
# data.auto_eda
# ---------------------------------------------------------------------------
class DataAutoEDASkill(Skill):
    """Run automated Exploratory Data Analysis on a dataset."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="data.auto_eda",
            version="1.0.0",
            name="Auto Exploratory Data Analysis",
            description=(
                "Run a comprehensive automated EDA pipeline on a dataset. "
                "Steps: load data → missing values → descriptive statistics → "
                "distribution charts → correlation analysis. Returns code, "
                "outputs, and chart figures for each step."
            ),
            category=SkillCategory.DATA,
            input_schema={
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "string",
                        "description": "ID of the dataset (from data.upload)",
                    },
                },
                "required": ["dataset_id"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step": {"type": "string"},
                                "description": {"type": "string"},
                                "success": {"type": "boolean"},
                                "stdout": {"type": "string"},
                                "figures": {"type": "array"},
                            },
                        },
                    },
                },
            },
            examples=[
                SkillExample(
                    description="Full EDA on uploaded CSV",
                    input={"dataset_id": "d-123"},
                    expected_output_summary=(
                        "5 EDA steps with statistics, distribution histograms, "
                        "and correlation heatmap"
                    ),
                ),
            ],
            prerequisites=["data.upload"],
            is_streaming=True,
            requires_session=True,
            requires_dataset=True,
            estimated_duration_ms=60000,
            tags=["eda", "statistics", "distributions", "correlations"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        steps = []
        async for event in self.execute_stream(params, context):
            if event.type == "eda_result":
                steps.append(event.data)
            elif event.type == "error":
                return SkillResult(success=False, error=event.data.get("message"))
        return SkillResult(success=True, data={"steps": steps})

    async def execute_stream(
        self, params: dict[str, Any], context: SkillContext
    ) -> AsyncIterator[SkillEvent]:
        from app.services.data_agent_service import AutoEDAService
        from app.db import SessionLocal
        from app.models import DatasetEntity

        dataset_id = params.get("dataset_id", "")
        if not dataset_id:
            yield SkillEvent(type="error", data={"message": "dataset_id is required"})
            return

        db = SessionLocal()
        try:
            dataset = db.query(DatasetEntity).filter(
                DatasetEntity.dataset_id == dataset_id
            ).first()
            if not dataset:
                yield SkillEvent(type="error", data={"message": f"Dataset {dataset_id} not found"})
                return
            file_path = dataset.file_path
            file_type = dataset.file_type
        finally:
            db.close()

        eda_service = AutoEDAService()

        yield SkillEvent(type="status", data={"message": "Starting Auto EDA..."})

        async for step_result in eda_service.run_eda(
            session_id=context.session_id,
            file_path=file_path,
            file_type=file_type,
        ):
            yield SkillEvent(
                type="status",
                data={"message": f"Running: {step_result['description']}"},
            )
            yield SkillEvent(
                type="eda_code",
                data={"step": step_result["step"], "code": step_result["code"]},
            )
            event_data = {
                "step": step_result["step"],
                "success": step_result["success"],
                "stdout": step_result.get("stdout", ""),
                "display": step_result.get("display"),
                "execution_time_ms": step_result.get("execution_time_ms", 0),
            }
            if step_result.get("figures"):
                event_data["figures"] = step_result["figures"]
            if not step_result["success"]:
                event_data["stderr"] = step_result.get("stderr", "")
            yield SkillEvent(type="eda_result", data=event_data)

        yield SkillEvent(type="status", data={"message": "Auto EDA completed"})


# ---------------------------------------------------------------------------
# data.query
# ---------------------------------------------------------------------------
class DataQuerySkill(Skill):
    """Execute a pandas expression on the loaded dataset."""

    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="data.query",
            version="1.0.0",
            name="Query Data",
            description=(
                "Execute a pandas expression (e.g. df.groupby('col').mean()) "
                "on a dataset already loaded in the Python kernel. Returns the "
                "query result as text. Use data.analyze for natural language queries."
            ),
            category=SkillCategory.DATA,
            input_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Pandas expression to evaluate",
                    },
                    "description": {
                        "type": "string",
                        "description": "Human-readable description of the query",
                    },
                },
                "required": ["expression"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "result_type": {"type": "string"},
                },
            },
            examples=[
                SkillExample(
                    description="Group by city and sum sales",
                    input={
                        "expression": "df.groupby('city')['sales'].sum().sort_values(ascending=False)",
                        "description": "Total sales by city, sorted descending",
                    },
                    expected_output_summary="DataFrame with city index and summed sales column",
                ),
            ],
            is_streaming=False,
            requires_session=True,
            tags=["query", "pandas", "filter", "aggregate"],
        )

    async def execute(self, params: dict[str, Any], context: SkillContext) -> SkillResult:
        from app.tools.data_tools import QueryDataTool
        from app.tools.base import ToolContext

        tool = QueryDataTool()
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
            data={"result": result.output},
        )
