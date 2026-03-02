"""RAG codebase search tool – bridges existing RAG infrastructure into the tool system."""

from __future__ import annotations

from typing import Any

from app.tools.base import BaseTool, ToolContext, ToolResult


class SearchCodebaseTool(BaseTool):
    """Semantic search over the indexed codebase using the existing RAG pipeline."""

    @property
    def name(self) -> str:
        return "search_codebase"

    @property
    def description(self) -> str:
        return (
            "Search the indexed codebase for code snippets, functions, classes, and "
            "files relevant to a query. Uses the project's RAG index for semantic "
            "retrieval. Returns ranked code context."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "current_file": {
                    "type": "string",
                    "description": "Optional current file path for context-aware ranking",
                },
            },
            "required": ["query"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        # Lazy import to avoid circular deps and allow use without DB
        try:
            from app.db import SessionLocal
            from app.repositories.context_repo import ContextRepository
            from app.services.rag_service import RAGService
            from app.core.config import settings

            db = SessionLocal()
            try:
                repo = ContextRepository(db)
                rag = RAGService(repo)
                result = rag.retrieve_context(
                    query=params["query"],
                    repo_name=settings.context_repo_name,
                    branch_name=settings.context_branch_name,
                    workspace=context.workspace,
                    current_file=params.get("current_file"),
                )
                if result:
                    return ToolResult(True, result[:5000])
                return ToolResult(True, "(no relevant code found)")
            finally:
                db.close()
        except Exception as e:
            return ToolResult(False, f"RAG search error: {e}")
