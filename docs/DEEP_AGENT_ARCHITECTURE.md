# DeepAgent Architecture for codingAgent

## 1. 先回答核心问题

像 Codex 这类 AI 编程工具，通常不是“单次问答 Agent”，而是接近 `DeepAgent` 的体系：

- 任务分解（Plan）
- 工具执行（Act）
- 结果验证（Test/Review）
- 失败反思与再规划（Reflect/Replan）
- 受控执行（Approval/Safety）

你当前项目已经具备雏形（`planner -> coder -> tester -> reviewer` + memory + project graph + vector context），可以在此基础上升级为真正的 DeepAgent。

## 2. 当前项目能力映射

已有模块与 DeepAgent 要素映射如下：

1. 流程编排：
- `backend/app/services/agent_service.py`
- 已有顺序流水线，但缺少“循环执行”和“失败恢复”。

2. 知识与上下文：
- `context_service.py` + `project_context_service.py` + `rag_service.py`
- 已有结构化索引、图谱、向量检索和上下文裁剪。

3. 记忆系统：
- `memory_service.py`
- 已有去重、压缩、summary。

4. 任务优先级：
- `scheduler_service.py`
- 已有基础优先级队列。

结论：你不是从 0 开始，而是从“线性 Agent”升级到“闭环 DeepAgent”。

## 3. 目标架构（建议）

```
User Goal
  -> Goal Manager
  -> Task Graph Planner (DAG)
  -> Execution Loop:
       SelectTask -> RetrieveContext -> Act(Tool Calls) -> Evaluate
       -> (pass) mark done
       -> (fail) Reflect + Replan + Retry Budget
  -> Merge Artifacts (patch/test/report)
  -> Human Gate (optional)
  -> Final Delivery
```

关键点：

1. `DAG` 而不是固定四步：
- 任务是节点（例如“改 API”“补测试”“修 lint”），节点有依赖边。

2. `Loop` 而不是单次执行：
- 每个节点都支持重试、降级、升级到人工审批。

3. `Evaluator` 独立：
- 不把“生成代码”与“判定是否完成”放在同一个 Agent。

4. `Artifact` 一等公民：
- patch、test logs、design notes、risk notes 都可追踪。

## 4. 推荐角色拆分

可先用 5 角色，足够稳定：

1. `planner`：把需求拆成可执行任务图。
2. `coder`：产出代码修改建议/补丁。
3. `tester`：执行单测、集成测试、静态检查。
4. `reviewer`：检查风险、兼容性、回滚方案。
5. `reflector`：失败后给出“失败原因 + 下一轮策略”。

## 5. 数据模型增量（在现有表基础上）

建议新增表（可逐步加）：

1. `agent_runs`
- run_id, session_id, goal, status, attempt_count, started_at, finished_at

2. `agent_tasks`
- task_id, run_id, parent_task_id, role, instruction, status, retry_count, depends_on_json

3. `task_artifacts`
- artifact_id, task_id, artifact_type(patch/test/report), content, metadata_json

4. `task_evaluations`
- eval_id, task_id, score, passed, reason, next_action

5. `approval_events`
- event_id, run_id, gate_type, decision, operator, comment

你现有 `requirements/tasks/tool_calls` 可以保留，逐步迁移或并行写入。

## 6. 服务层改造建议

### 6.1 新增 orchestrator（核心）

新增：`backend/app/services/deep_agent_service.py`

职责：

- 创建 run
- 生成 task graph
- 循环执行 task
- 收集 artifacts
- evaluator 判定 pass/fail
- fail 时 reflector 触发 replan
- 达到重试上限则进入人工 gate

### 6.2 保留并复用已有能力

1. `RAGService`：继续做上下文入口。
2. `ProjectContextManager`：继续提供跨文件理解。
3. `MemoryManager`：记录每轮执行摘要（建议按 run_id 聚合）。
4. `TestService`：作为标准工具节点。

## 7. API 设计（增量）

建议新增：

1. `POST /api/v1/agent/runs`
- 输入：session_id, goal, current_file
- 输出：run_id, initial_plan

2. `POST /api/v1/agent/runs/{run_id}/step`
- 执行一轮 loop（便于流式 UI）

3. `GET /api/v1/agent/runs/{run_id}`
- 返回：任务图、当前状态、最近 artifacts

4. `POST /api/v1/agent/runs/{run_id}/approve`
- 人工审批高风险操作（如大规模改动、迁移脚本）

## 8. 执行循环伪代码

```python
while not run.done:
    task = scheduler.pick_next_ready_task(run_id)
    ctx = rag.retrieve(task.instruction, session_id, current_file)
    output = role_executor.run(task.role, task.instruction, ctx)
    artifacts.save(task.id, output)

    eval_result = evaluator.judge(task, artifacts.of(task.id))
    if eval_result.passed:
        task.mark_done()
    else:
        if task.retry_count < task.retry_budget:
            task.retry_with(reflector.replan(task, eval_result))
        else:
            run.request_human_gate(task, eval_result)
```

## 9. 分阶段落地（建议 3 个迭代）

### Iteration A（1-2 周）

目标：从“线性流程”升级到“可重试 loop”

- 新增 `agent_runs/agent_tasks/task_evaluations` 基础模型
- 抽象 evaluator（先规则评分）
- orchestrator 支持 retry budget

验收：
- 对同一需求可自动进行至少 2 轮修复尝试

### Iteration B（2-3 周）

目标：任务图和多工件追踪

- planner 输出 DAG（最小可先 tree）
- 每个 task 输出 artifact（patch/test/report）
- API 可查询 run 全量轨迹

验收：
- 前端可看到“任务图 + 每节点结果”

### Iteration C（2 周）

目标：安全与生产化

- 人工审批 gate
- 风险策略（数据库迁移、批量改文件、删除操作）
- 评估指标：成功率、平均轮次、回归率、成本

验收：
- 有可追踪审计链路，失败可回放

## 10. 最小代码改造优先级

1. 先改 `agent_service.py`：从固定四步改为 `loop + evaluator`。
2. 再加数据模型：run/task/eval。
3. 再开新 API：run 生命周期。
4. 最后接入 IDE 流式可视化。

这条路径风险最低，且与当前代码结构最兼容。
