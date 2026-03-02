from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.core.config import settings
from app.models import InteractionMemoryEntity
from app.repositories.context_repo import ContextRepository


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_\-]{2,}")


@dataclass
class OptimizationResult:
    before_count: int
    after_count: int
    compacted_count: int
    summary_created: bool


class MemoryManager:
    def __init__(self, repo: ContextRepository):
        self.repo = repo

    def record(
        self,
        session_id: str,
        role: str,
        content: str,
        tags: str | None = None,
        importance_score: int = 1,
        is_pinned: bool = False,
        auto_optimize: bool = True,
    ) -> InteractionMemoryEntity | None:
        normalized = self._normalize(content)
        if not normalized:
            return None

        content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        existing = self.repo.find_memory_by_hash(session_id=session_id, content_hash=content_hash)
        if existing:
            return existing

        memory = self.repo.add_memory_with_metadata(
            session_id=session_id,
            role=role,
            content=normalized,
            content_hash=content_hash,
            importance_score=max(1, min(5, importance_score)),
            is_pinned=is_pinned,
            tags=tags,
        )
        if auto_optimize:
            self.optimize_session(session_id)
        return memory

    def optimize_session(self, session_id: str) -> OptimizationResult:
        memories = self.repo.list_session_memories(session_id=session_id, limit=500)
        before_count = len(memories)
        if before_count <= settings.memory_max_items_per_session:
            return OptimizationResult(
                before_count=before_count,
                after_count=before_count,
                compacted_count=0,
                summary_created=False,
            )

        # Desc order -> oldest are at the tail.
        desc_memories = memories
        recent_keep = max(8, settings.memory_keep_recent_items)
        candidate_tail = list(reversed(desc_memories[recent_keep:]))
        candidates = [m for m in candidate_tail if not m.is_pinned and m.role != "summary"]

        if not candidates:
            return OptimizationResult(
                before_count=before_count,
                after_count=before_count,
                compacted_count=0,
                summary_created=False,
            )

        batch = candidates[: settings.memory_summary_batch_size]
        summary_content = self._build_summary(batch)
        summary_created = False
        if summary_content:
            self.record(
                session_id=session_id,
                role="summary",
                content=summary_content,
                tags="auto_summary",
                importance_score=4,
                is_pinned=True,
                auto_optimize=False,
            )
            summary_created = True

        deleted = self.repo.delete_memories([m.memory_id for m in batch])

        after_memories = self.repo.list_session_memories(session_id=session_id, limit=500)
        return OptimizationResult(
            before_count=before_count,
            after_count=len(after_memories),
            compacted_count=deleted,
            summary_created=summary_created,
        )

    def _build_summary(self, memories: list[InteractionMemoryEntity]) -> str:
        if not memories:
            return ""

        lines = ["Auto summary of older session memories:"]
        for m in memories:
            preview = m.content.replace("\n", " ").strip()[:180]
            lines.append(f"- {m.role}: {preview}")

        topic_words: list[str] = []
        seen: set[str] = set()
        for m in memories:
            for token in TOKEN_PATTERN.findall(m.content.lower()):
                if token in seen:
                    continue
                seen.add(token)
                topic_words.append(token)
                if len(topic_words) >= 12:
                    break
            if len(topic_words) >= 12:
                break
        if topic_words:
            lines.append("Topics: " + ", ".join(topic_words))

        return "\n".join(lines)[:1400]

    def _normalize(self, content: str) -> str:
        normalized = re.sub(r"\s+", " ", content).strip()
        return normalized
