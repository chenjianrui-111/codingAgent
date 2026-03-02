import hashlib

from sqlalchemy import delete, desc, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CodeSymbolEntity,
    DependencyEdgeEntity,
    InteractionMemoryEntity,
    KnowledgeChunkEntity,
    ProjectGraphEdgeEntity,
    ProjectGraphNodeEntity,
    ProjectFileEntity,
    ProjectVectorEntity,
)


class ContextRepository:
    def __init__(self, db: Session):
        self.db = db

    def clear_repo_context(self, repo_name: str, branch_name: str) -> None:
        self.db.execute(
            delete(ProjectFileEntity).where(
                ProjectFileEntity.repo_name == repo_name,
                ProjectFileEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(CodeSymbolEntity).where(
                CodeSymbolEntity.repo_name == repo_name,
                CodeSymbolEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(DependencyEdgeEntity).where(
                DependencyEdgeEntity.repo_name == repo_name,
                DependencyEdgeEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(KnowledgeChunkEntity).where(
                KnowledgeChunkEntity.repo_name == repo_name,
                KnowledgeChunkEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(ProjectGraphEdgeEntity).where(
                ProjectGraphEdgeEntity.repo_name == repo_name,
                ProjectGraphEdgeEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(ProjectGraphNodeEntity).where(
                ProjectGraphNodeEntity.repo_name == repo_name,
                ProjectGraphNodeEntity.branch_name == branch_name,
            )
        )
        self.db.execute(
            delete(ProjectVectorEntity).where(
                ProjectVectorEntity.repo_name == repo_name,
                ProjectVectorEntity.branch_name == branch_name,
            )
        )
        self.db.commit()

    def add_project_files(self, rows: list[ProjectFileEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_code_symbols(self, rows: list[CodeSymbolEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_dependency_edges(self, rows: list[DependencyEdgeEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_knowledge_chunks(self, rows: list[KnowledgeChunkEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_graph_nodes(self, rows: list[ProjectGraphNodeEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_graph_edges(self, rows: list[ProjectGraphEdgeEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_project_vectors(self, rows: list[ProjectVectorEntity]) -> None:
        if not rows:
            return
        self.db.add_all(rows)
        self.db.commit()

    def add_memory(self, session_id: str, role: str, content: str, tags: str | None = None) -> InteractionMemoryEntity:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return self.add_memory_with_metadata(
            session_id=session_id,
            role=role,
            content=content,
            content_hash=content_hash,
            importance_score=1,
            is_pinned=False,
            tags=tags,
        )

    def add_memory_with_metadata(
        self,
        session_id: str,
        role: str,
        content: str,
        content_hash: str,
        importance_score: int = 1,
        is_pinned: bool = False,
        tags: str | None = None,
    ) -> InteractionMemoryEntity:
        memory = InteractionMemoryEntity(
            session_id=session_id,
            role=role,
            content=content,
            content_hash=content_hash,
            importance_score=importance_score,
            is_pinned=is_pinned,
            tags=tags,
        )
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def list_recent_memories(self, session_id: str, limit: int = 6) -> list[InteractionMemoryEntity]:
        stmt = (
            select(InteractionMemoryEntity)
            .where(InteractionMemoryEntity.session_id == session_id)
            .order_by(desc(InteractionMemoryEntity.created_at), desc(InteractionMemoryEntity.memory_id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_session_memories(self, session_id: str, limit: int = 200) -> list[InteractionMemoryEntity]:
        stmt = (
            select(InteractionMemoryEntity)
            .where(InteractionMemoryEntity.session_id == session_id)
            .order_by(desc(InteractionMemoryEntity.created_at), desc(InteractionMemoryEntity.memory_id))
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def find_memory_by_hash(self, session_id: str, content_hash: str) -> InteractionMemoryEntity | None:
        stmt = (
            select(InteractionMemoryEntity)
            .where(
                InteractionMemoryEntity.session_id == session_id,
                InteractionMemoryEntity.content_hash == content_hash,
            )
            .order_by(desc(InteractionMemoryEntity.memory_id))
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def delete_memories(self, memory_ids: list[int]) -> int:
        if not memory_ids:
            return 0
        stmt = delete(InteractionMemoryEntity).where(InteractionMemoryEntity.memory_id.in_(memory_ids))
        result = self.db.execute(stmt)
        self.db.commit()
        return int(result.rowcount or 0)

    def search_symbols(self, repo_name: str, branch_name: str, keywords: list[str], limit: int = 8) -> list[CodeSymbolEntity]:
        if not keywords:
            return []
        conditions = [CodeSymbolEntity.symbol_name.ilike(f"%{kw}%") for kw in keywords[:5]]
        stmt = select(CodeSymbolEntity).where(
            CodeSymbolEntity.repo_name == repo_name,
            CodeSymbolEntity.branch_name == branch_name,
            or_(*conditions),
        )
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def search_dependencies(self, repo_name: str, branch_name: str, keywords: list[str], limit: int = 10) -> list[DependencyEdgeEntity]:
        if not keywords:
            return []
        conditions = [DependencyEdgeEntity.target_module.ilike(f"%{kw}%") for kw in keywords[:5]]
        stmt = select(DependencyEdgeEntity).where(
            DependencyEdgeEntity.repo_name == repo_name,
            DependencyEdgeEntity.branch_name == branch_name,
            or_(*conditions),
        )
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def search_knowledge_chunks(
        self,
        repo_name: str,
        branch_name: str,
        keywords: list[str],
        limit: int = 8,
    ) -> list[KnowledgeChunkEntity]:
        if not keywords:
            return []
        conditions = [KnowledgeChunkEntity.chunk_text.ilike(f"%{kw}%") for kw in keywords[:4]]
        stmt = select(KnowledgeChunkEntity).where(
            KnowledgeChunkEntity.repo_name == repo_name,
            KnowledgeChunkEntity.branch_name == branch_name,
            or_(*conditions),
        )
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_graph_neighbors(self, repo_name: str, branch_name: str, node_key: str, limit: int = 200) -> list[ProjectGraphEdgeEntity]:
        stmt = (
            select(ProjectGraphEdgeEntity)
            .where(
                ProjectGraphEdgeEntity.repo_name == repo_name,
                ProjectGraphEdgeEntity.branch_name == branch_name,
                or_(
                    ProjectGraphEdgeEntity.source_key == node_key,
                    ProjectGraphEdgeEntity.target_key == node_key,
                ),
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_edges_from_sources(
        self,
        repo_name: str,
        branch_name: str,
        source_keys: list[str],
        edge_types: list[str] | None = None,
        limit: int = 500,
    ) -> list[ProjectGraphEdgeEntity]:
        if not source_keys:
            return []
        stmt = select(ProjectGraphEdgeEntity).where(
            ProjectGraphEdgeEntity.repo_name == repo_name,
            ProjectGraphEdgeEntity.branch_name == branch_name,
            ProjectGraphEdgeEntity.source_key.in_(source_keys),
        )
        if edge_types:
            stmt = stmt.where(ProjectGraphEdgeEntity.edge_type.in_(edge_types))
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_nodes_by_keys(self, repo_name: str, branch_name: str, node_keys: list[str]) -> list[ProjectGraphNodeEntity]:
        if not node_keys:
            return []
        stmt = select(ProjectGraphNodeEntity).where(
            ProjectGraphNodeEntity.repo_name == repo_name,
            ProjectGraphNodeEntity.branch_name == branch_name,
            ProjectGraphNodeEntity.node_key.in_(node_keys),
        )
        return list(self.db.scalars(stmt).all())

    def list_symbol_nodes_by_name(self, repo_name: str, branch_name: str, symbol_name: str, limit: int = 100) -> list[ProjectGraphNodeEntity]:
        stmt = (
            select(ProjectGraphNodeEntity)
            .where(
                ProjectGraphNodeEntity.repo_name == repo_name,
                ProjectGraphNodeEntity.branch_name == branch_name,
                ProjectGraphNodeEntity.node_type == "function",
                ProjectGraphNodeEntity.name == symbol_name,
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def list_edges_to_targets(
        self,
        repo_name: str,
        branch_name: str,
        target_keys: list[str],
        edge_type: str,
        limit: int = 500,
    ) -> list[ProjectGraphEdgeEntity]:
        if not target_keys:
            return []
        stmt = (
            select(ProjectGraphEdgeEntity)
            .where(
                ProjectGraphEdgeEntity.repo_name == repo_name,
                ProjectGraphEdgeEntity.branch_name == branch_name,
                ProjectGraphEdgeEntity.target_key.in_(target_keys),
                ProjectGraphEdgeEntity.edge_type == edge_type,
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def search_project_vectors(
        self,
        repo_name: str,
        branch_name: str,
        keywords: list[str],
        limit: int = 200,
    ) -> list[ProjectVectorEntity]:
        stmt = select(ProjectVectorEntity).where(
            ProjectVectorEntity.repo_name == repo_name,
            ProjectVectorEntity.branch_name == branch_name,
        )
        if keywords:
            conditions = []
            for kw in keywords[:6]:
                conditions.append(ProjectVectorEntity.text_content.ilike(f"%{kw}%"))
                conditions.append(ProjectVectorEntity.keywords.ilike(f"%{kw}%"))
            stmt = stmt.where(or_(*conditions))
        stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def list_core_config_vectors(self, repo_name: str, branch_name: str, limit: int = 20) -> list[ProjectVectorEntity]:
        file_names = [
            "pom.xml",
            "requirements.txt",
            "package.json",
            "pyproject.toml",
            "README.md",
            "README.MD",
        ]
        conditions = [ProjectVectorEntity.file_path.ilike(f"%{name}") for name in file_names]
        stmt = (
            select(ProjectVectorEntity)
            .where(
                ProjectVectorEntity.repo_name == repo_name,
                ProjectVectorEntity.branch_name == branch_name,
                or_(*conditions),
            )
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
