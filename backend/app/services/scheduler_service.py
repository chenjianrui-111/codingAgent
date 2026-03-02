import heapq
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(order=True)
class ScheduledTask:
    sort_key: tuple[int, int, float] = field(init=False)
    priority_rank: int
    estimated_points: int
    created_ts: float
    requirement_id: int

    def __post_init__(self) -> None:
        self.sort_key = (self.priority_rank, self.estimated_points, self.created_ts)


class TaskScheduler:
    PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

    def __init__(self) -> None:
        self._queue: list[ScheduledTask] = []

    def enqueue(self, requirement_id: int, priority: str, estimated_points: int) -> None:
        rank = self.PRIORITY_RANK.get(priority, 1)
        task = ScheduledTask(
            priority_rank=rank,
            estimated_points=estimated_points,
            created_ts=datetime.utcnow().timestamp(),
            requirement_id=requirement_id,
        )
        heapq.heappush(self._queue, task)

    def next_requirement(self) -> int | None:
        if not self._queue:
            return None
        return heapq.heappop(self._queue).requirement_id

    def size(self) -> int:
        return len(self._queue)
