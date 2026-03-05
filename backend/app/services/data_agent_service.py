"""Data Analysis Agent service.

Extends the existing AgentRunner with data-specific capabilities:
- Dataset-aware system prompt with schema injection
- Specialized data analysis tools (execute_python, generate_chart, etc.)
- Auto EDA workflow
- Visualization streaming via SSE
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.core.config import settings
from app.services.llm_service import LLMService
from app.services.agent_runner import AgentRunner, StreamEvent
from app.services.data_service import DataService
from app.tools.base import ToolContext, ToolRegistry
from app.tools.data_tools import (
    AnalyzeDatasetTool,
    ExecutePythonTool,
    GenerateChartTool,
    QueryDataTool,
)

logger = logging.getLogger(__name__)

# Data analyst system prompt
DATA_AGENT_SYSTEM_PROMPT = """You are an expert Data Analyst AI Agent. You help users analyze datasets,
discover insights, generate visualizations, and answer data-related questions.

## Your Capabilities
- Load and explore datasets (CSV, Excel, JSON, Parquet)
- Perform exploratory data analysis (EDA)
- Generate statistical summaries and correlations
- Create professional visualizations (charts, plots, heatmaps)
- Clean and transform data
- Answer natural language questions about data
- Build predictive models with scikit-learn

## Workflow Guidelines
1. **Understand first**: Always start by examining the dataset schema and sample data
2. **Plan your analysis**: Before writing code, explain your approach
3. **Iterate**: Run code step by step, checking results at each stage
4. **Visualize**: Use charts to illustrate key findings
5. **Summarize**: Provide clear, actionable insights in natural language

## Code Style
- Use pandas (pd) for data manipulation
- Use matplotlib.pyplot (plt) for charts, seaborn (sns) for statistical visualizations
- Always add titles, labels, and legends to charts
- Use descriptive variable names
- Handle missing data gracefully
- Print intermediate results for verification

## Chart Guidelines
- Choose appropriate chart types:
  * Bar/Column: comparing categories
  * Line: trends over time
  * Scatter: relationships between variables
  * Histogram: distribution of a single variable
  * Box: distribution comparison across categories
  * Heatmap: correlations or matrix data
  * Pie: proportions (use sparingly)
- Always use plt.figure(figsize=(10, 6)) for readability
- Use color palettes from seaborn for consistency
- Add plt.tight_layout() to prevent label cutoff

## Safety
- Never modify or delete the original dataset files
- Handle large datasets efficiently (use sampling if > 100k rows)
- Catch and report errors clearly
"""


def create_data_tool_registry() -> ToolRegistry:
    """Create a ToolRegistry with data analysis tools."""
    registry = ToolRegistry()
    for tool in [
        ExecutePythonTool(),
        AnalyzeDatasetTool(),
        GenerateChartTool(),
        QueryDataTool(),
    ]:
        registry.register(tool)
    return registry


def create_full_data_registry() -> ToolRegistry:
    """Create a ToolRegistry with BOTH data tools and standard file/shell tools."""
    from app.tools import create_default_registry

    registry = create_default_registry()
    # Add data-specific tools
    for tool in [
        ExecutePythonTool(),
        AnalyzeDatasetTool(),
        GenerateChartTool(),
        QueryDataTool(),
    ]:
        registry.register(tool)
    return registry


class DataAgentRunner(AgentRunner):
    """Extended AgentRunner with data analysis capabilities."""

    def __init__(
        self,
        llm: LLMService | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        llm = llm or LLMService()
        registry = tool_registry or create_data_tool_registry()
        super().__init__(llm=llm, tool_registry=registry)

    async def run_data_stream(
        self,
        session_id: str,
        query: str,
        dataset_context: str | None = None,
        workspace: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Run a data analysis agent session with dataset-aware context.

        Extends the standard agent stream with:
        - Dataset schema/stats injected into system prompt
        - Figure streaming events for chart visualization
        """
        workspace = workspace or settings.sandbox_workspace_root

        # Pre-load dataset into kernel
        init_code = None
        if dataset_context:
            # The dataset context will be injected into the system prompt
            pass

        async for event in self.run_stream(
            session_id=session_id,
            query=query,
            workspace=workspace,
            rag_context=dataset_context,
        ):
            # Intercept tool_result events to extract figures
            if event.type == "tool_result":
                tool_name = event.data.get("tool")
                if tool_name in ("execute_python", "generate_chart"):
                    # Check if there are figures in the metadata
                    # The figures are stored in the ToolResult metadata
                    pass

            yield event

    def _build_system_prompt(
        self,
        workspace: str,
        current_file: str | None,
        rag_context: str | None,
        memory_context: str | None,
    ) -> str:
        """Override to use the data analyst system prompt."""
        parts = [DATA_AGENT_SYSTEM_PROMPT]
        parts.append(f"\n## Workspace\nWorking directory: {workspace}\n")

        if rag_context:
            parts.append(f"\n## Dataset Information\n{rag_context}\n")

        if memory_context:
            parts.append(f"\n## Conversation History\n{memory_context}\n")

        return "\n".join(parts)


class AutoEDAService:
    """Automated Exploratory Data Analysis.

    Generates a comprehensive EDA report by running a sequence of
    pre-defined analysis steps on a dataset.
    """

    # Steps for auto EDA
    EDA_STEPS = [
        {
            "name": "load_data",
            "description": "Load the dataset and display basic info",
            "code_template": """
import pandas as pd
df = pd.read_{file_type}('{file_path}')
print("Shape:", df.shape)
print("\\nColumn types:")
print(df.dtypes)
print("\\nFirst 5 rows:")
df.head()
""",
        },
        {
            "name": "missing_values",
            "description": "Analyze missing values",
            "code_template": """
missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(2)
missing_report = pd.DataFrame({{'missing': missing, 'pct': missing_pct}})
missing_report = missing_report[missing_report['missing'] > 0].sort_values('pct', ascending=False)
if len(missing_report) > 0:
    print("Missing Values Report:")
    print(missing_report)
else:
    print("No missing values found!")
""",
        },
        {
            "name": "descriptive_stats",
            "description": "Generate descriptive statistics",
            "code_template": """
print("Descriptive Statistics (Numeric):")
print(df.describe().round(4))
print("\\nDescriptive Statistics (Categorical):")
cat_cols = df.select_dtypes(include=['object', 'category']).columns
for col in cat_cols[:5]:
    print(f"\\n--- {{col}} ---")
    print(df[col].value_counts().head(10))
""",
        },
        {
            "name": "distribution_charts",
            "description": "Plot distributions of numeric columns",
            "code_template": """
import matplotlib.pyplot as plt
import numpy as np

numeric_cols = df.select_dtypes(include='number').columns[:6]
if len(numeric_cols) > 0:
    n = len(numeric_cols)
    rows = (n + 2) // 3
    fig, axes = plt.subplots(rows, min(3, n), figsize=(14, 4*rows))
    if n == 1:
        axes = [axes]
    else:
        axes = axes.flatten() if hasattr(axes, 'flatten') else [axes]

    for i, col in enumerate(numeric_cols):
        ax = axes[i] if i < len(axes) else axes[-1]
        df[col].dropna().hist(bins=30, ax=ax, color='steelblue', edgecolor='white')
        ax.set_title(col, fontsize=12)
        ax.set_xlabel('')

    for j in range(i+1, len(axes)):
        axes[j].set_visible(False)

    plt.suptitle('Distribution of Numeric Columns', fontsize=14, y=1.02)
    plt.tight_layout()
    plt.show()
else:
    print("No numeric columns for distribution analysis")
""",
        },
        {
            "name": "correlation",
            "description": "Compute and visualize correlations",
            "code_template": """
import matplotlib.pyplot as plt
import numpy as np

numeric_df = df.select_dtypes(include='number')
if numeric_df.shape[1] >= 2:
    corr = numeric_df.corr().round(3)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(corr, cmap='RdBu_r', vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_yticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha='right', fontsize=9)
    ax.set_yticklabels(corr.columns, fontsize=9)
    for i in range(len(corr)):
        for j in range(len(corr)):
            val = corr.iloc[i, j]
            ax.text(j, i, f'{{val:.2f}}', ha='center', va='center',
                   color='white' if abs(val) > 0.5 else 'black', fontsize=8)
    fig.colorbar(im)
    plt.title('Correlation Matrix', fontsize=14)
    plt.tight_layout()
    plt.show()
    print("\\nTop correlations (absolute):")
    pairs = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            pairs.append((corr.columns[i], corr.columns[j], abs(corr.iloc[i,j])))
    pairs.sort(key=lambda x: x[2], reverse=True)
    for a, b, v in pairs[:10]:
        print(f"  {{a}} <-> {{b}}: {{v:.3f}}")
else:
    print("Not enough numeric columns for correlation analysis")
""",
        },
    ]

    def __init__(self):
        from app.services.python_kernel_service import kernel_manager
        self.kernel_manager = kernel_manager

    async def run_eda(
        self,
        session_id: str,
        file_path: str,
        file_type: str,
    ) -> AsyncIterator[dict]:
        """Run automated EDA steps, yielding results for each step."""
        for step in self.EDA_STEPS:
            code = step["code_template"]
            # Replace template variables
            read_func = "csv"
            if file_type in ("xlsx", "xls", "excel"):
                read_func = "excel"
            elif file_type == "json":
                read_func = "json"
            elif file_type == "parquet":
                read_func = "parquet"

            code = code.replace("{file_type}", read_func)
            code = code.replace("{file_path}", file_path)

            result = await self.kernel_manager.execute(session_id, code)

            yield {
                "step": step["name"],
                "description": step["description"],
                "code": code.strip(),
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "display": result.display,
                "figures": result.figures,
                "execution_time_ms": result.execution_time_ms,
            }
