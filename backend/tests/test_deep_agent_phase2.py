from types import SimpleNamespace

from app.api.routes import _parse_depends_on
from app.services.agent_service import AgentOrchestrator


class DummyRepo:
    pass


class DummyRag:
    pass


class DummyTester:
    pass


def test_parse_depends_on_json():
    assert _parse_depends_on('[1, "2", "x"]') == [1, 2]
    assert _parse_depends_on(None) == []
    assert _parse_depends_on('{"a":1}') == []


def test_risky_todo_requires_human_approval():
    orchestrator = AgentOrchestrator(repo=DummyRepo(), rag_service=DummyRag(), test_service=DummyTester())
    todo = SimpleNamespace(
        role="planner",
        title="database migration task",
        instruction="prepare alter table migration",
        attempt_count=0,
    )
    assert orchestrator._requires_human_approval(todo) is True

    safe_todo = SimpleNamespace(role="tester", title="run tests", instruction="pytest -q", attempt_count=0)
    assert orchestrator._requires_human_approval(safe_todo) is False
