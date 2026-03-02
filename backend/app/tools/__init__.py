"""Tool system for the Codex-like AI coding agent."""

from app.tools.base import BaseTool, ToolContext, ToolRegistry, ToolResult
from app.tools.file_ops import EditFileTool, ListDirectoryTool, ReadFileTool, SearchFilesTool, WriteFileTool
from app.tools.shell import ShellTool
from app.tools.git_ops import GitBranchTool, GitCommitTool, GitDiffTool, GitLogTool, GitStatusTool
from app.tools.rag_tool import SearchCodebaseTool


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
