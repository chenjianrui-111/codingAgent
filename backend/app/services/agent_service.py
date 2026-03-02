from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from app.core.config import settings
from app.models import AgentTodoEntity, RequirementEntity, SessionEntity
from app.repositories.agent_repo import AgentRepository
from app.services.memory_service import MemoryManager
from app.services.rag_service import RAGService
from app.services.test_service import TestService


@dataclass
class AgentTrace:
    role: str
    instruction: str
    output: str
    status: str


@dataclass
class PlannedTodo:
    role: str
    title: str
    instruction: str
    success_criteria: str
    depends_on_indexes: list[int]
    max_attempts: int


@dataclass
class EvaluationResult:
    passed: bool
    score: int
    reason: str
    next_action: str


@dataclass
class TodoSnapshot:
    todo_id: int
    role: str
    title: str
    status: str
    success_criteria: str
    attempt_count: int


class PersonaInterpreter:
    persona_name = settings.deep_agent_persona_name
    _SPACE_PATTERN = re.compile(r"\s+")

    def interpret(self, query: str) -> str:
        normalized = self._SPACE_PATTERN.sub(" ", query).strip()
        if not normalized:
            return "Implement a robust coding solution for the user request."
        return normalized[:4000]


class PlanningTool:
    COMPLEX_HINTS = {
        "refactor",
        "multi",
        "across",
        "pipeline",
        "architecture",
        "database",
        "migration",
        "concurrency",
        "scheduler",
        "agent",
        "workflow",
        "test",
    }

    def assess_complexity(self, interpreted_query: str) -> str:
        lowered = interpreted_query.lower()
        hint_count = sum(1 for hint in self.COMPLEX_HINTS if hint in lowered)
        if hint_count >= 2 or len(interpreted_query) >= 100:
            return "complex"
        return "simple"

    def build_todos(self, interpreted_query: str, complexity: str, retry_budget: int) -> list[PlannedTodo]:
        if complexity == "simple":
            return [
                PlannedTodo(
                    role="coder",
                    title="Direct implementation",
                    instruction=f"Implement the request directly: {interpreted_query}",
                    success_criteria="Provide concrete and actionable code changes.",
                    depends_on_indexes=[],
                    max_attempts=retry_budget,
                ),
                PlannedTodo(
                    role="reviewer",
                    title="Final quality check",
                    instruction="Review implementation quality, risk, and rollout guidance.",
                    success_criteria="Summarize quality checks and remaining risks.",
                    depends_on_indexes=[0],
                    max_attempts=1,
                ),
            ]
        return [
            PlannedTodo(
                role="planner",
                title="Clarify execution plan",
                instruction=f"Decompose the coding task into deterministic steps: {interpreted_query}",
                success_criteria="List concrete subtasks with measurable completion conditions.",
                depends_on_indexes=[],
                max_attempts=1,
            ),
            PlannedTodo(
                role="coder",
                title="Implement code changes",
                instruction=f"Implement code modifications according to plan: {interpreted_query}",
                success_criteria="Produce concrete patch-oriented coding guidance with target files.",
                depends_on_indexes=[0],
                max_attempts=retry_budget,
            ),
            PlannedTodo(
                role="tester",
                title="Validate with tests",
                instruction="Run automated tests to validate the implementation.",
                success_criteria="Tests should pass with exit_code=0.",
                depends_on_indexes=[1],
                max_attempts=retry_budget,
            ),
            PlannedTodo(
                role="reviewer",
                title="Risk and delivery review",
                instruction="Review final outcome, summarize risk, and provide rollout notes.",
                success_criteria="Deliver final review with risk and next-step guidance.",
                depends_on_indexes=[2],
                max_attempts=1,
            ),
        ]


class PlannerAgent:
    def run(self, instruction: str) -> str:
        return (
            "Execution decomposition:\n"
            f"- Goal: {instruction}\n"
            "- Step 1: Locate related files and symbols.\n"
            "- Step 2: Implement focused code updates.\n"
            "- Step 3: Validate via tests and adjust if failures occur.\n"
            "- Step 4: Summarize delivery risk and rollout notes."
        )


class CoderAgent:
    def __init__(self, rag_service: RAGService):
        self.rag_service = rag_service

    def run(
        self,
        instruction: str,
        session_id: str,
        current_file: str | None = None,
    ) -> tuple[str, str]:
        context = self.rag_service.retrieve_context(instruction, session_id=session_id, current_file=current_file)
        output = (
            "Code change proposal generated.\n"
            f"Focus: {instruction}\n"
            f"Current file: {current_file or 'n/a'}\n"
            f"Retrieved context:\n{context}\n"
            "Next action: apply patch to target files and run tests."
        )
        return output, context


class ReviewerAgent:
    def run(self, interpreted_query: str, todo_stats: list[TodoSnapshot]) -> str:
        completed = sum(1 for t in todo_stats if t.status == "completed")
        failed = [t for t in todo_stats if t.status == "failed"]
        return (
            "Review summary:\n"
            f"Requirement: {interpreted_query}\n"
            f"Completed todos: {completed}/{len(todo_stats)}\n"
            f"Failed todos: {len(failed)}\n"
            "Recommendation: require human approval before merge for production branches."
        )


class ResultEvaluator:
    def evaluate(self, role: str, output: str, success_criteria: str) -> EvaluationResult:
        lowered = output.lower()
        if role == "tester":
            passed = "exit_code=0" in lowered and "timeout" not in lowered and "not found" not in lowered
            if passed:
                return EvaluationResult(True, 100, "Tests passed with exit_code=0.", "complete")
            return EvaluationResult(False, 30, "Tests failed or test runner unavailable.", "replan")

        if "workspace does not exist" in lowered:
            return EvaluationResult(False, 20, "Workspace unavailable for coding context.", "retry")
        if len(output.strip()) < 40:
            return EvaluationResult(False, 40, "Output too short and likely incomplete.", "retry")
        if role == "reviewer":
            return EvaluationResult(True, 90, "Review generated.", "complete")
        return EvaluationResult(True, 85, f"Meets criteria: {success_criteria}", "complete")


class ReflectorAgent:
    def replan_instruction(self, instruction: str, reason: str, success_criteria: str) -> str:
        return (
            f"{instruction}\n\n"
            "[REFLECT]\n"
            f"Previous attempt did not pass: {reason}\n"
            f"Must satisfy: {success_criteria}\n"
            "Adjust the approach and provide a concrete result."
        )


class FileSystemArtifactStore:
    def __init__(self, workspace: str, run_id: str):
        self.base_dir = Path(workspace) / settings.deep_agent_artifact_dir / run_id
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_todo_output(self, todo_id: int, role: str, content: str) -> str:
        path = self.base_dir / f"todo_{todo_id:04d}_{role}.md"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def write_run_summary(self, content: str) -> str:
        path = self.base_dir / "final_summary.md"
        path.write_text(content, encoding="utf-8")
        return str(path)


class AgentOrchestrator:
    TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
    RISKY_KEYWORDS = {
        "drop table",
        "truncate",
        "delete from",
        "alter table",
        "migration",
        "rm -rf",
        "delete file",
        "bulk delete",
    }

    def __init__(
        self,
        repo: AgentRepository,
        rag_service: RAGService,
        test_service: TestService,
        memory_manager: MemoryManager | None = None,
    ):
        self.repo = repo
        self.persona = PersonaInterpreter()
        self.planning_tool = PlanningTool()
        self.planner_worker = PlannerAgent()
        self.coder_worker = CoderAgent(rag_service)
        self.tester_worker = test_service
        self.reviewer_worker = ReviewerAgent()
        self.evaluator = ResultEvaluator()
        self.reflector = ReflectorAgent()
        self.memory_manager = memory_manager

    def run(
        self,
        session: SessionEntity,
        requirement: RequirementEntity,
        query: str,
        current_file: str | None = None,
    ) -> tuple[str, list[AgentTrace], str, list[TodoSnapshot]]:
        traces: list[AgentTrace] = []
        interpreted_query = self.persona.interpret(query)
        complexity = self.planning_tool.assess_complexity(interpreted_query)
        run = self.repo.create_agent_run(
            session_id=session.session_id,
            requirement_id=requirement.requirement_id,
            original_query=query,
            interpreted_query=interpreted_query,
            persona_name=self.persona.persona_name,
            complexity=complexity,
            max_steps=settings.deep_agent_max_steps,
        )
        store = FileSystemArtifactStore(settings.run_workspace, run.run_id)
        if self.memory_manager:
            self.memory_manager.record(
                session_id=session.session_id,
                role="system",
                content=f"DeepAgent run started: run_id={run.run_id}, complexity={complexity}",
                tags="deepagent_run_start",
                importance_score=3,
                auto_optimize=False,
            )

        plan = self.planning_tool.build_todos(
            interpreted_query=interpreted_query,
            complexity=complexity,
            retry_budget=settings.deep_agent_default_retry_budget,
        )
        self._persist_initial_plan(run.run_id, plan)
        traces.append(
            AgentTrace(
                role="planner",
                instruction="Build executable to-do list",
                output=f"Complexity={complexity}; planned_todos={len(plan)}",
                status="completed",
            )
        )

        step_count = 0
        while step_count < run.max_steps:
            todos = self.repo.list_agent_todos(run.run_id)
            next_todo = self._pick_next_ready_todo(todos)
            if not next_todo:
                break
            if self._requires_human_approval(next_todo):
                reason = "Risky operation requires human approval before execution."
                self.repo.update_agent_todo(next_todo, status="waiting_approval", output_text=reason)
                self.repo.create_approval_event(
                    run_id=run.run_id,
                    todo_id=next_todo.todo_id,
                    gate_type="risky_operation",
                    decision="pending",
                    operator="system",
                    comment=f"todo#{next_todo.todo_id} flagged for approval",
                )
                traces.append(
                    AgentTrace(
                        role=next_todo.role,
                        instruction=next_todo.instruction,
                        output=reason,
                        status="waiting_approval",
                    )
                )
                break

            step_count += 1
            self.repo.update_agent_run_progress(run, current_step=step_count)
            attempt = next_todo.attempt_count + 1
            next_todo = self.repo.update_agent_todo(next_todo, status="running", attempt_count=attempt)

            task = self.repo.create_task(requirement.requirement_id, next_todo.role, next_todo.instruction)
            output = self._execute_todo(
                todo=next_todo,
                interpreted_query=interpreted_query,
                session_id=session.session_id,
                current_file=current_file,
            )
            artifact_path = store.write_todo_output(next_todo.todo_id, next_todo.role, output)
            output_with_artifact = f"{output}\n\nArtifact: {artifact_path}"
            self.repo.complete_task(task, output_with_artifact)

            evaluation = self.evaluator.evaluate(next_todo.role, output, next_todo.success_criteria)
            self.repo.create_task_evaluation(
                run_id=run.run_id,
                todo_id=next_todo.todo_id,
                evaluator="rule_evaluator",
                passed=evaluation.passed,
                score=evaluation.score,
                reason=evaluation.reason,
                next_action=evaluation.next_action,
            )

            if evaluation.passed:
                updated_todo = self.repo.update_agent_todo(
                    next_todo,
                    status="completed",
                    output_text=f"{output_with_artifact}\n\nEvaluator: {evaluation.reason}",
                )
                traces.append(
                    AgentTrace(
                        role=updated_todo.role,
                        instruction=updated_todo.instruction,
                        output=updated_todo.output_text or output_with_artifact,
                        status="completed",
                    )
                )
                if self.memory_manager:
                    self.memory_manager.record(
                        session_id=session.session_id,
                        role="system",
                        content=f"Todo completed: {updated_todo.todo_id} {updated_todo.title}",
                        tags="deepagent_todo_completed",
                        importance_score=2,
                        auto_optimize=False,
                    )
                continue

            if next_todo.role == "tester":
                if self._can_inject_test_remediation(run.run_id):
                    updated_todo = self.repo.update_agent_todo(
                        next_todo,
                        status="completed",
                        output_text=f"{output_with_artifact}\n\nEvaluator: {evaluation.reason}",
                    )
                    self._inject_test_remediation(run.run_id, updated_todo, output)
                    traces.append(
                        AgentTrace(
                            role=updated_todo.role,
                            instruction=updated_todo.instruction,
                            output=updated_todo.output_text or output_with_artifact,
                            status="replanned",
                        )
                    )
                else:
                    updated_todo = self.repo.update_agent_todo(
                        next_todo,
                        status="failed",
                        output_text=(
                            f"{output_with_artifact}\n\nEvaluator: {evaluation.reason}\n\n"
                            "Retry budget exhausted for tester remediation."
                        ),
                    )
                    traces.append(
                        AgentTrace(
                            role=updated_todo.role,
                            instruction=updated_todo.instruction,
                            output=updated_todo.output_text or output_with_artifact,
                            status="failed",
                        )
                    )
                continue

            if attempt < next_todo.max_attempts:
                replanned_instruction = self.reflector.replan_instruction(
                    instruction=next_todo.instruction,
                    reason=evaluation.reason,
                    success_criteria=next_todo.success_criteria,
                )
                updated_todo = self.repo.update_agent_todo(
                    next_todo,
                    status="pending",
                    instruction=replanned_instruction,
                    output_text=f"{output_with_artifact}\n\nEvaluator: {evaluation.reason}",
                )
                traces.append(
                    AgentTrace(
                        role=updated_todo.role,
                        instruction=updated_todo.instruction,
                        output=updated_todo.output_text or output_with_artifact,
                        status="retrying",
                    )
                )
                continue

            updated_todo = self.repo.update_agent_todo(
                next_todo,
                status="failed",
                output_text=f"{output_with_artifact}\n\nEvaluator: {evaluation.reason}",
            )
            traces.append(
                AgentTrace(
                    role=updated_todo.role,
                    instruction=updated_todo.instruction,
                    output=updated_todo.output_text or output_with_artifact,
                    status="failed",
                )
            )

        todo_snapshots = self._todo_snapshots(self.repo.list_agent_todos(run.run_id))
        failed_todos = [t for t in todo_snapshots if t.status == "failed"]
        approval_todos = [t for t in todo_snapshots if t.status == "waiting_approval"]
        pending_todos = [t for t in todo_snapshots if t.status not in self.TERMINAL_STATUSES]

        if approval_todos:
            run_status = "waiting_approval"
        elif not pending_todos and not failed_todos:
            run_status = "completed"
        elif failed_todos:
            run_status = "failed"
        elif step_count >= run.max_steps:
            run_status = "max_steps_reached"
        else:
            run_status = "partial"
        self.repo.set_agent_run_status(run, run_status, finished=run_status not in {"running", "waiting_approval"})

        review_output = self._latest_reviewer_output(run.run_id)
        final_answer = review_output or self._build_fallback_summary(interpreted_query, todo_snapshots, run_status)
        summary_path = store.write_run_summary(final_answer)
        final_answer = f"{final_answer}\n\nRun ID: {run.run_id}\nSummary Artifact: {summary_path}"
        if self.memory_manager:
            self.memory_manager.record(
                session_id=session.session_id,
                role="assistant",
                content=f"DeepAgent run finished: run_id={run.run_id}, status={run_status}",
                tags="deepagent_run_end",
                importance_score=3,
                auto_optimize=False,
            )
        return final_answer, traces, run.run_id, todo_snapshots

    def _persist_initial_plan(self, run_id: str, plan: list[PlannedTodo]) -> None:
        created_todos: list[AgentTodoEntity] = []
        for item in plan:
            depends_ids = [created_todos[idx].todo_id for idx in item.depends_on_indexes if idx < len(created_todos)]
            todo = self.repo.create_agent_todo(
                run_id=run_id,
                role=item.role,
                title=item.title,
                instruction=item.instruction,
                success_criteria=item.success_criteria,
                depends_on=depends_ids,
                max_attempts=item.max_attempts,
            )
            created_todos.append(todo)

    def _pick_next_ready_todo(self, todos: list[AgentTodoEntity]) -> AgentTodoEntity | None:
        completed_ids = {t.todo_id for t in todos if t.status == "completed"}
        for todo in todos:
            if todo.status != "pending":
                continue
            deps = self._load_depends(todo.depends_on_json)
            if all(dep in completed_ids for dep in deps):
                return todo
        return None

    def _load_depends(self, depends_on_json: str | None) -> list[int]:
        if not depends_on_json:
            return []
        try:
            data = json.loads(depends_on_json)
            if isinstance(data, list):
                return [int(x) for x in data if str(x).isdigit()]
        except Exception:
            return []
        return []

    def _execute_todo(
        self,
        todo: AgentTodoEntity,
        interpreted_query: str,
        session_id: str,
        current_file: str | None,
    ) -> str:
        if todo.role == "planner":
            return self.planner_worker.run(todo.instruction)

        if todo.role == "coder":
            start = perf_counter()
            output, context = self.coder_worker.run(todo.instruction, session_id=session_id, current_file=current_file)
            elapsed = int((perf_counter() - start) * 1000)
            self.repo.create_tool_call(
                session_id=session_id,
                tool_name="rag.retrieve_context",
                request_text=todo.instruction,
                response_text=context[:1000],
                latency_ms=elapsed,
            )
            return output

        if todo.role == "tester":
            start = perf_counter()
            test_output = self.tester_worker.run_tests()
            elapsed = int((perf_counter() - start) * 1000)
            self.repo.create_tool_call(
                session_id=session_id,
                tool_name="test.run",
                request_text=todo.instruction,
                response_text=test_output[:1000],
                latency_ms=elapsed,
            )
            return test_output

        if todo.role == "reviewer":
            snapshots = self._todo_snapshots(self.repo.list_agent_todos(todo.run_id))
            return self.reviewer_worker.run(interpreted_query, snapshots)

        return f"Unsupported role: {todo.role}"

    def _inject_test_remediation(self, run_id: str, failed_todo: AgentTodoEntity, failed_output: str) -> None:
        existing = [
            t
            for t in self.repo.list_agent_todos(run_id)
            if t.parent_todo_id == failed_todo.todo_id and t.role in {"coder", "tester"}
        ]
        if existing:
            return

        fix_todo = self.repo.create_agent_todo(
            run_id=run_id,
            role="coder",
            title="Fix issues from failed tests",
            instruction=(
                "Address failures from latest test output and provide concrete patch guidance.\n\n"
                f"Failed test output:\n{failed_output[:2000]}"
            ),
            success_criteria="Propose concrete fixes that directly target test failures.",
            depends_on=[failed_todo.todo_id],
            parent_todo_id=failed_todo.todo_id,
            max_attempts=settings.deep_agent_default_retry_budget,
        )
        retest_todo = self.repo.create_agent_todo(
            run_id=run_id,
            role="tester",
            title="Re-run tests after remediation",
            instruction="Run tests again after remediation; target exit_code=0.",
            success_criteria="Tests should pass with exit_code=0.",
            depends_on=[fix_todo.todo_id],
            parent_todo_id=fix_todo.todo_id,
            max_attempts=settings.deep_agent_default_retry_budget,
        )

        for todo in self.repo.list_agent_todos(run_id):
            if todo.role != "reviewer" or todo.status != "pending":
                continue
            deps = self._load_depends(todo.depends_on_json)
            if failed_todo.todo_id in deps:
                rewired = [retest_todo.todo_id if dep == failed_todo.todo_id else dep for dep in deps]
                self.repo.update_agent_todo(todo, depends_on=rewired)

    def _can_inject_test_remediation(self, run_id: str) -> bool:
        tester_todos = [t for t in self.repo.list_agent_todos(run_id) if t.role == "tester"]
        max_tester_rounds = max(1, settings.deep_agent_default_retry_budget + 1)
        return len(tester_todos) < max_tester_rounds

    def _latest_reviewer_output(self, run_id: str) -> str:
        todos = self.repo.list_agent_todos(run_id)
        reviewers = [t for t in todos if t.role == "reviewer" and t.status == "completed" and t.output_text]
        if not reviewers:
            return ""
        reviewers.sort(key=lambda t: t.todo_id, reverse=True)
        return reviewers[0].output_text or ""

    def _todo_snapshots(self, todos: list[AgentTodoEntity]) -> list[TodoSnapshot]:
        return [
            TodoSnapshot(
                todo_id=t.todo_id,
                role=t.role,
                title=t.title,
                status=t.status,
                success_criteria=t.success_criteria,
                attempt_count=t.attempt_count,
            )
            for t in todos
        ]

    def _build_fallback_summary(self, interpreted_query: str, snapshots: list[TodoSnapshot], run_status: str) -> str:
        lines = [
            "DeepAgent execution summary:",
            f"Requirement: {interpreted_query}",
            f"Run status: {run_status}",
        ]
        for item in snapshots:
            lines.append(
                f"- todo#{item.todo_id} [{item.role}] {item.title} => {item.status} (attempts={item.attempt_count})"
            )
        return "\n".join(lines)

    def _requires_human_approval(self, todo: AgentTodoEntity) -> bool:
        if todo.role not in {"coder", "planner"}:
            return False
        if todo.attempt_count > 0:
            return False
        text = f"{todo.title}\n{todo.instruction}".lower()
        return any(keyword in text for keyword in self.RISKY_KEYWORDS)
