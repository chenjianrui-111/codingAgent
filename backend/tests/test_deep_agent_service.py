from app.services.agent_service import PlanningTool, ResultEvaluator


def test_planning_tool_marks_complex_requests():
    planner = PlanningTool()
    query = "Refactor backend scheduler and add database migration test workflow"
    assert planner.assess_complexity(query) == "complex"


def test_planning_tool_creates_todo_chain_for_complex_requests():
    planner = PlanningTool()
    todos = planner.build_todos(
        interpreted_query="Build deep agent workflow with test and review",
        complexity="complex",
        retry_budget=2,
    )
    assert [t.role for t in todos] == ["planner", "coder", "tester", "reviewer"]
    assert todos[2].depends_on_indexes == [1]


def test_evaluator_requires_green_tests_for_tester_role():
    evaluator = ResultEvaluator()
    passed = evaluator.evaluate("tester", "exit_code=0\nall good", "exit_code=0")
    failed = evaluator.evaluate("tester", "exit_code=1\n2 failed", "exit_code=0")
    assert passed.passed is True
    assert failed.passed is False
