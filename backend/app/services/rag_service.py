from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.context_repo import ContextRepository
from app.services.context_service import ContextRetriever
from app.services.project_context_service import ProjectContextManager


class RAGService:
    def __init__(
        self,
        workspace: str | None = None,
        db: Session | None = None,
        repo_name: str | None = None,
        branch_name: str | None = None,
    ):
        self.workspace = Path(workspace or settings.run_workspace)
        self.db = db
        self.repo_name = repo_name or settings.context_repo_name
        self.branch_name = branch_name or settings.context_branch_name

    def retrieve_context(
        self,
        query: str,
        session_id: str | None = None,
        current_file: str | None = None,
        max_files: int = 5,
    ) -> str:
        if self.db is not None and session_id:
            try:
                project_manager = ProjectContextManager(ContextRepository(self.db))
                project_context = project_manager.retrieve_project_context(
                    query=query,
                    repo_name=self.repo_name,
                    branch_name=self.branch_name,
                    current_file=current_file,
                )
                if project_context.context and project_context.context != "no indexed context available":
                    return project_context.context[: settings.memory_context_char_budget]
            except Exception:
                pass

            try:
                retriever = ContextRetriever(ContextRepository(self.db))
                result = retriever.retrieve(
                    query=query,
                    session_id=session_id,
                    repo_name=self.repo_name,
                    branch_name=self.branch_name,
                )
                if result and result != "no indexed context available":
                    return result[: settings.memory_context_char_budget]
            except Exception:
                # Keep the service available even when DB context lookup fails.
                pass

        if not self.workspace.exists():
            return "workspace does not exist"

        snippets: list[str] = []
        for path in self.workspace.rglob("*"):
            if len(snippets) >= max_files:
                break
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".java", ".md", ".yaml", ".yml", ".json"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            first_lines = "\\n".join(content.splitlines()[:8])
            snippets.append(f"[{path}]\\n{first_lines}")

        if not snippets:
            return "no indexed code yet"

        return "\\n\\n".join(snippets)[: settings.memory_context_char_budget]
