# Detailed Implementation Plan

## Phase 1: MVP closed loop (Week 1-2)

- [x] FastAPI service with health/session/generate APIs.
- [x] OceanBase schema for sessions/requirements/tasks/tool_calls.
- [x] Multi-agent orchestration pipeline.
- [x] Local test runner integration.

Acceptance criteria:
- `/api/v1/generate` returns a final answer with 4 role traces.

## Phase 2: Codebase RAG (Week 3-4)

- [x] `index_repo.py` for file/chunk ingestion.
- [x] Context indexing pipeline (`project_files`, `code_symbols`, `dependency_edges`, `knowledge_chunks`).
- [x] Interaction memory storage (`interaction_memories`) and retrieval.
- [x] Memory management optimization (dedup + compaction + summary memory + retrieval scoring).
- [x] Project-wide graph + vectors (`project_graph_nodes`, `project_graph_edges`, `project_vectors`).
- [ ] Embedding generation service and batch insert.
- [ ] Hybrid retrieval (`keyword + vector + rerank`).

Acceptance criteria:
- Retrieval top-k precision baseline report available.

## Phase 3: Scheduling and collaboration (Week 5-6)

- [x] Requirement analyzer (split requirement into actionable tasks).
- [ ] Priority queue and concurrency control.
- [ ] Human approval gates before risky operations.

Acceptance criteria:
- Task status machine supports retry/escalation/manual takeover.

## Phase 4: IDE and developer UX (Week 7-8)

- [x] VS Code extension command bridge.
- [ ] Inline code actions (apply patch, rerun tests, open PR draft).
- [ ] Streaming agent traces in IDE panel.

Acceptance criteria:
- Engineers can run full loop without leaving IDE.

## Phase 5: Evaluation and production hardening (Week 9-12)

- [ ] Internal benchmark set (bugfix/refactor/test-gen).
- [ ] Eval dashboard: success rate, latency, cost, regression rate.
- [ ] Security policy: prompt injection defense, data boundary checks, audit.

Acceptance criteria:
- Production SLO and rollback runbook are in place.

## Phase 6: DeepAgent upgrade (Week 13-16)

- [x] Introduce `agent_runs` and todo-level tables (`agent_todos`, `task_evaluations`) for run lifecycle management.
- [x] Upgrade orchestration from fixed 4-step pipeline to loop-based execution with retry budget.
- [x] Add `evaluator + reflector` so failed tasks can replan and retry automatically.
- [x] Persist task artifacts to filesystem (`.deepagent/runs/<run_id>/...`) and expose run trace via `/generate`.
- [x] Add human approval gates for risky operations (migration, large refactor, delete-heavy changes).

Acceptance criteria:
- A single requirement can complete through `plan -> act -> evaluate -> reflect -> replan` loop with auditable traces.
