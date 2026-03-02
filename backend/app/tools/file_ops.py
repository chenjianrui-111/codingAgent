"""File-system tools: read, write, edit, list, search."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from app.tools.base import BaseTool, ToolContext, ToolResult


class ReadFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file. Returns the text content with line numbers."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path within the workspace"},
                "offset": {"type": "integer", "description": "Start line (1-based)", "default": 1},
                "limit": {"type": "integer", "description": "Max lines to read", "default": 500},
            },
            "required": ["path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            abs_path = self.resolve_safe_path(params["path"], context.workspace)
        except PermissionError as e:
            return ToolResult(False, str(e))

        if not os.path.isfile(abs_path):
            return ToolResult(False, f"File not found: {params['path']}")

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return ToolResult(False, f"Error reading file: {e}")

        offset = max(params.get("offset", 1), 1) - 1
        limit = params.get("limit", 500)
        selected = lines[offset : offset + limit]

        numbered = "".join(
            f"{i + offset + 1:4d} | {line}" for i, line in enumerate(selected)
        )
        total = len(lines)
        header = f"File: {params['path']} ({total} lines total, showing {offset + 1}-{offset + len(selected)})\n"
        return ToolResult(True, header + numbered)


class WriteFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Create or overwrite a file with the given content."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path within the workspace"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            abs_path = self.resolve_safe_path(params["path"], context.workspace)
        except PermissionError as e:
            return ToolResult(False, str(e))

        try:
            Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(params["content"])
            return ToolResult(True, f"Written {len(params['content'])} chars to {params['path']}")
        except Exception as e:
            return ToolResult(False, f"Error writing file: {e}")


class EditFileTool(BaseTool):
    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Apply a targeted edit to a file by replacing an exact string match. "
            "Provide the old text to find and the new text to replace it with."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "old_text": {"type": "string", "description": "Exact text to find and replace"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            abs_path = self.resolve_safe_path(params["path"], context.workspace)
        except PermissionError as e:
            return ToolResult(False, str(e))

        if not os.path.isfile(abs_path):
            return ToolResult(False, f"File not found: {params['path']}")

        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(False, f"Error reading file: {e}")

        old_text = params["old_text"]
        new_text = params["new_text"]

        count = content.count(old_text)
        if count == 0:
            return ToolResult(False, f"old_text not found in {params['path']}")
        if count > 1:
            return ToolResult(
                False,
                f"old_text matches {count} locations – provide more context to make it unique",
            )

        new_content = content.replace(old_text, new_text, 1)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return ToolResult(
            True,
            f"Edited {params['path']}: replaced {len(old_text)} chars with {len(new_text)} chars",
        )


class ListDirectoryTool(BaseTool):
    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return "List files and directories. Use recursive=true for tree view."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path", "default": "."},
                "recursive": {"type": "boolean", "description": "List recursively", "default": False},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        rel = params.get("path", ".")
        try:
            abs_path = self.resolve_safe_path(rel, context.workspace)
        except PermissionError as e:
            return ToolResult(False, str(e))

        if not os.path.isdir(abs_path):
            return ToolResult(False, f"Directory not found: {rel}")

        entries: list[str] = []
        recursive = params.get("recursive", False)

        if recursive:
            for root, dirs, files in os.walk(abs_path):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                rel_root = os.path.relpath(root, context.workspace)
                for name in sorted(files):
                    if not name.startswith("."):
                        entries.append(os.path.join(rel_root, name))
                if len(entries) > 500:
                    entries.append("... (truncated at 500 entries)")
                    break
        else:
            for name in sorted(os.listdir(abs_path)):
                full = os.path.join(abs_path, name)
                suffix = "/" if os.path.isdir(full) else ""
                entries.append(name + suffix)

        return ToolResult(True, "\n".join(entries) if entries else "(empty directory)")


class SearchFilesTool(BaseTool):
    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "Search file contents using grep. Returns matching lines with file paths and line numbers."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern (regex)"},
                "path": {"type": "string", "description": "Relative directory to search in", "default": "."},
                "include_glob": {"type": "string", "description": "File glob filter, e.g. '*.py'"},
            },
            "required": ["pattern"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        rel = params.get("path", ".")
        try:
            abs_path = self.resolve_safe_path(rel, context.workspace)
        except PermissionError as e:
            return ToolResult(False, str(e))

        cmd = ["grep", "-rn", "--max-count=100", params["pattern"], abs_path]
        if params.get("include_glob"):
            cmd.insert(2, f"--include={params['include_glob']}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=context.workspace
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "Search timed out after 30s")

        output = result.stdout[:8000] if result.stdout else "(no matches)"
        # Make paths relative to workspace
        output = output.replace(context.workspace + "/", "")
        return ToolResult(True, output)
