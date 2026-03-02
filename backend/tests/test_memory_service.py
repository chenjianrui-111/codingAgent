from dataclasses import dataclass

from app.services.memory_service import MemoryManager


@dataclass
class FakeMemory:
    memory_id: int
    session_id: str
    role: str
    content: str
    content_hash: str
    importance_score: int
    is_pinned: bool
    tags: str | None = None


class FakeRepo:
    def __init__(self):
        self.items: list[FakeMemory] = []
        self.next_id = 1

    def find_memory_by_hash(self, session_id: str, content_hash: str):
        for item in self.items:
            if item.session_id == session_id and item.content_hash == content_hash:
                return item
        return None

    def add_memory_with_metadata(
        self,
        session_id: str,
        role: str,
        content: str,
        content_hash: str,
        importance_score: int = 1,
        is_pinned: bool = False,
        tags: str | None = None,
    ):
        item = FakeMemory(
            memory_id=self.next_id,
            session_id=session_id,
            role=role,
            content=content,
            content_hash=content_hash,
            importance_score=importance_score,
            is_pinned=is_pinned,
            tags=tags,
        )
        self.next_id += 1
        self.items.append(item)
        return item

    def list_session_memories(self, session_id: str, limit: int = 200):
        filtered = [x for x in self.items if x.session_id == session_id]
        filtered.sort(key=lambda x: x.memory_id, reverse=True)
        return filtered[:limit]

    def delete_memories(self, memory_ids: list[int]) -> int:
        before = len(self.items)
        self.items = [x for x in self.items if x.memory_id not in set(memory_ids)]
        return before - len(self.items)


def test_memory_manager_dedup_and_optimize():
    repo = FakeRepo()
    manager = MemoryManager(repo)

    sid = "s1"
    manager.record(session_id=sid, role="user", content="fix auth bug")
    manager.record(session_id=sid, role="user", content="fix auth bug")
    assert len(repo.items) == 1

    # Push enough items to trigger auto optimization in current defaults.
    for idx in range(90):
        manager.record(session_id=sid, role="assistant", content=f"message {idx}")

    summaries = [x for x in repo.items if x.role == "summary"]
    assert summaries
    assert len(repo.items) <= 90
