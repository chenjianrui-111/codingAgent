"""Tool system for the Codex-like AI coding agent."""

from app.tools.base import BaseTool, ToolContext, ToolRegistry, ToolResult
from app.tools.file_ops import EditFileTool, ListDirectoryTool, ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.shell import ShellTool
from app.tools.git_ops import GitBranchTool, GitCommitTool, GitDiffTool, GitLogTool, GitStatusTool
from app.tools.rag_tool import SearchCodebaseTool
from app.tools.data_tools import AnalyzeDatasetTool, ExecutePythonTool, GenerateChartTool, QueryDataTool


def create_default_registry() -> ToolRegistry:
    """Create a ToolRegistry pre-loaded with all built-in tools."""
    registry = ToolRegistry()
    for tool in [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        ListDirectoryTool(),
        SearchFilesTool(),
        ShellTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitCommitTool(),
        GitLogTool(),
        GitBranchTool(),
        SearchCodebaseTool(),
    ]:
        registry.register(tool)
    return registry


def create_data_registry() -> ToolRegistry:
    """Create a ToolRegistry with data analysis tools + standard tools."""
    registry = create_default_registry()
    for tool in [
        ExecutePythonTool(),
        AnalyzeDatasetTool(),
        GenerateChartTool(),
        QueryDataTool(),
    ]:
        registry.register(tool)
    return registry
