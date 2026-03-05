# Coding Agent — AI 自主编程平台

一个自主式 AI 编程 Agent 平台，集成 DeepAgent 多角色编排引擎、多层 RAG 知识检索、项目级知识图谱、Streaming Tool-Use 实时工具调用、多租户认证体系，以及完整的全栈 Web UI。专为真实软件工程工作流设计。

##项目效果
<img width="1520" height="1025" alt="image" src="https://github.com/user-attachments/assets/d60d2400-088d-4a46-a98f-ce01aa00b6e4" />


## 架构总览

```
                         +------------------+
                         |   Web 前端        |  React + SSE Streaming
                         |  (对话 / Diff /   |
                         |   工具卡片)        |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   FastAPI 服务端   |  REST + SSE + WebSocket
                         |   /api/v1/*       |
                         +--------+---------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
     +--------v------+  +--------v--------+  +-------v--------+
     | Agent Runner   |  | DeepAgent       |  | Tool System    |
     | (LLM Streaming |  | 多角色编排引擎    |  | 文件 / Shell / |
     |  Tool-Use 循环) |  | (规划-编码-测试)  |  | Git / RAG      |
     +--------+------+  +--------+--------+  +-------+--------+
              |                   |                   |
     +--------v-------------------v-------------------v--------+
     |                    服务层 (Service Layer)                  |
     |  LLM 服务 | 记忆管理 | RAG 服务 | 沙箱隔离                  |
     |  上下文索引 | 项目知识图谱 | 多模态处理 | 测试执行             |
     +----------------------------+----------------------------+
                                  |
              +-------------------+-------------------+
              |                                       |
     +--------v--------+                    +---------v-------+
     | OceanBase / MySQL|                    | 文件系统         |
     | (20+ 张数据表)    |                    | 产物存储 +       |
     | SQLite 降级兜底   |                    | 沙箱工作区       |
     +------------------+                    +-----------------+
```

---

## 核心功能模块

### 1. DeepAgent 多角色编排引擎

> `backend/app/services/agent_service.py` — 655+ 行

生产级 Agentic Loop，具备规划、执行、评估、自愈能力。

**多角色工作流水线**

| 角色 | 职责 |
|------|------|
| **PlannerAgent** | 将用户需求拆解为带依赖关系的 Todo DAG |
| **CoderAgent** | 结合 RAG 注入的项目上下文生成代码变更 |
| **TesterAgent** | 执行测试套件，校验 exit_code = 0 |
| **ReviewerAgent** | 风险评估、交付说明、最终质量把关 |

**智能执行循环**

```
用户输入
  -> Persona 解释器（标准化处理，限制 4000 字符）
  -> 复杂度评估（simple/complex，启发式关键词检测）
  -> 规划工具（构建带任务间依赖的 Todo DAG）
  -> 执行循环（最多 16 步）：
       选取下一个就绪 Todo（所有依赖已完成）
       -> 风险检查：检测到危险关键词？
            是 -> 创建 ApprovalEvent，暂停等待人工决策
            否 -> 执行对应角色的 Worker Agent
       -> 评估结果（基于规则：exit_code、输出长度、关键词）
       -> 失败且有剩余重试次数？
            是 -> ReflectorAgent 注入失败上下文，重新尝试
            否 -> 标记失败，继续下一个
       -> 测试失败？ -> 自动注入修复循环（Coder -> Tester）
  -> 聚合产物 + 生成摘要
```

**自愈与重试机制**
- 每个 Todo 可配置重试预算（默认 2 次）
- `ReflectorAgent` 分析失败原因并注入纠正指令
- 测试失败自动触发 Coder-Tester 修复循环
- 所有中间产物持久化到 `.deepagent/runs/{run_id}/`

**人工审批门控**
- 执行前扫描危险关键词（`DROP TABLE`、`rm -rf`、`ALTER TABLE`、`migration` 等）
- 阻断执行，创建 `ApprovalEvent` 记录，等待人工决策
- 审批/拒绝操作追踪操作者身份和备注，用于审计

---

### 2. LLM Streaming Tool-Use Agent Runner

> `backend/app/services/agent_runner.py` + `backend/app/services/llm_service.py`

实时 LLM API 集成，支持 Streaming Tool-Use 的自主编码 Agent。

**流式架构**
- 使用 `AsyncAnthropic` 客户端的 `messages.stream()` API
- 实时 Chunk 类型：`text_delta` | `tool_use` | `message_stop`
- 零缓冲：文本和工具调用到达即推送
- Server-Sent Events (SSE) 协议传输到前端

**Agentic Loop**
```
1. 收集 RAG 上下文 + Session 记忆 -> 构建 System Prompt
2. 流式调用 LLM 并附带工具定义
3. 收到 text_delta -> 推送 SSE 事件到前端（实时打字效果）
4. 收到 tool_use -> 执行工具 -> 推送结果 -> 继续对话
5. 无工具调用 -> Agent 完成
6. 最多 16 步安全边界
```

**上下文感知的 System Prompt**
- 注入工作区路径和当前文件上下文
- RAG 检索的代码片段来自项目知识图谱
- Session 记忆摘要来自 MemoryManager
- 编码最佳实践（先读后改、最小变更、执行测试）

---

### 3. 工具系统与沙箱安全

> `backend/app/tools/`

12 个内置工具，带路径沙箱、命令白名单和资源限制。

**文件操作** (`file_ops.py`)

| 工具 | 功能 | 安全机制 |
|------|------|---------|
| `read_file` | 行号输出，支持 offset/limit 分页 | 路径沙箱校验 |
| `write_file` | 创建或覆盖文件，自动创建父目录 | 防止沙箱逃逸 |
| `edit_file` | 精确字符串匹配替换（拒绝歧义匹配） | 单一匹配强制 |
| `list_directory` | 递归目录树，500 条上限 | 遍历保护 |
| `search_files` | 正则搜索 + Glob 过滤，100 条上限 | 输出截断（8KB） |

**Shell 执行** (`shell.py`)
- **命令白名单**：仅允许白名单内的可执行文件（`git`、`python`、`pytest`、`npm`、`node`、`make` 等）
- **环境隔离**：仅保留 `PATH`、`HOME`、`USER`、`LANG`、`TERM`、`SHELL`，`HOME` 设为沙箱目录
- **资源限制**：120 秒超时，stdout 截断 8KB + stderr 截断 2KB
- **退出码追踪**：结构化输出 `exit_code=N` 用于下游评估

**Git 操作** (`git_ops.py`)
- `git_status`、`git_diff`（暂存/未暂存）、`git_log`（可配置深度）
- `git_commit` — 暂存指定文件 + 原子提交
- `git_branch` — 列表、创建、切换分支
- `git_push` **永久禁用** — 防止未经审查的代码推送到远端

**RAG 上下文工具** (`rag_tool.py`)
- 将 RAG 基础设施桥接到 LLM Tool-Use 系统
- LLM 可在解题过程中自主搜索已索引的代码库

**路径沙箱强制**
```python
resolved = (Path(workspace) / relative_path).resolve()
if not str(resolved).startswith(str(Path(workspace).resolve())):
    raise PermissionError("Path escapes sandbox")
```

---

### 4. 多层 RAG 与上下文检索

> `backend/app/services/rag_service.py` + `context_service.py` + `project_context_service.py`

三级检索降级链：项目图谱 -> 上下文索引 -> 工作区扫描。

**第一层：项目知识图谱** (`project_context_service.py` — 700+ 行)

构建整个代码库的语义图谱：

| 节点类型 | 内容 |
|---------|------|
| `file` | 源文件（路径、类型、大小） |
| `symbol` | 函数/类（签名和文档注释） |
| `module` | 逻辑模块分组 |

| 边类型 | 含义 |
|--------|------|
| `contains` | 文件包含符号 |
| `depends_on` | 文件导入模块 |
| `calls` | 符号调用符号 |
| `calls_file` | 符号引用文件 |
| `extends` | 类继承关系 |

**优先级上下文裁剪**
```
当前文件:        +2.5 优先级加成
直接依赖:        +1.4（依赖图 1 跳）
间接依赖:        +0.8（2 跳传递）
配置文件:        +0.5（yaml, json, env）
```

**向量相似度搜索**
- 确定性 64 维 Token-Hash Embedding（无需外部 API）
- 所有索引实体上的 Cosine Similarity 排序
- 结合图距离评分实现混合检索

**第二层：上下文索引** (`context_service.py` — 270+ 行)

| 能力 | 实现方式 |
|------|---------|
| 符号提取 | Python AST 解析（类、函数、签名、文档注释）；JS/TS 正则模式 |
| 依赖追踪 | Python 的 `ast.Import`/`ast.ImportFrom`；JS/TS 的 `import`/`require` 正则 |
| 知识分块 | 60 行语义块 + 关键词提取 |
| 检索评分 | Token 重叠 + 时间衰减 + 置顶/摘要加成（+0.6） |

支持文件类型：`.py`、`.ts`、`.tsx`、`.js`、`.java`、`.md`、`.yaml`、`.yml`、`.json`

**第三层：工作区降级**
- 无索引时直接扫描文件系统
- 读取每个文件前 8 行作为预览
- 限制 5000 字符预算

**跨文件理解**
```bash
# 查找调用指定函数的所有文件
POST /api/v1/project/callers
{"function_name": "run", "repo_name": "codingAgent", "branch_name": "main"}
```

---

### 5. Session 记忆管理

> `backend/app/services/memory_service.py`

智能对话记忆系统，支持去重、重要性评分和自动压缩。

**去重机制**
- 对标准化文本计算 SHA256 Content Hash
- 同一 Session 内相同消息仅存储一次

**重要性评分与置顶**
- 5 级重要性评分（1-5）用于优先级检索
- 置顶消息在压缩时永不被淘汰
- 摘要记忆自动创建为 importance=4 并置顶

**自动压缩策略**
```
当 Session 超过 80 条记录时：
  1. 保留最近 36 条不动
  2. 选取最旧的未置顶、非摘要记录
  3. 每批 16 条 -> 提取主题词 -> 生成摘要
  4. 存储摘要为置顶记忆（importance=4）
  5. 删除原始批次
```

**上下文预算控制**
- 每次查询的记忆检索限制 5000 字符
- 防止 LLM System Prompt 中的 Token 膨胀
- 时间衰减权重确保近期上下文排名更高

---

### 6. 多模态输入处理

> `backend/app/services/multimodal_service.py`

支持图片、音频、文档作为任务输入，与文本查询并行处理。

| 输入类型 | 处理方式 | 工具 |
|---------|---------|------|
| **图片** | OCR 文字提取 | Tesseract CLI |
| **音频** | 语音转文字 | Whisper CLI |
| **文档** | 文本提取 | 直接文件读取 |
| **文本** | 内联或基于文件 | 原生 |

**弹性管道**
- 支持文件路径、内联文本、Base64 编码输入
- 优雅降级：失败记录到 `notes[]` 但不崩溃
- 每个附件提取文本上限 1600 字符
- 查询中注入 `[ATTACHMENT_CONTEXT]` 块
- 完整预处理统计：`attachment_count`、`processed_count`、`extracted_count`、`failed_count`

---

### 7. 实时 Web 前端

> `frontend/` — React 18 + TypeScript + Vite + Tailwind CSS + Zustand

具备流式 Agent 输出和交互式工具卡片的全功能聊天界面。

**SSE 流式协议**

| 事件类型 | 数据 | 界面行为 |
|---------|------|---------|
| `status` | `{message, step}` | 状态指示器 + 步骤计数 |
| `text_delta` | `{text}` | 逐字实时渲染 |
| `tool_call` | `{tool, input, id}` | 可展开工具调用卡片 |
| `tool_result` | `{id, success, output}` | 成功/失败标记 + 可折叠输出 |
| `diff_preview` | `{path, detail}` | 文件变更预览 |
| `approval_required` | `{run_id, reason}` | 审批/拒绝对话框 |
| `done` | `{run_id, status}` | 流完成 |

**组件架构**
- `ChatPanel` — 主对话视图，自动滚动
- `MessageBubble` — Markdown 渲染 + 语法高亮（VSCode Dark+ 主题）
- `ToolCallCard` — 展开/折叠工具调用，显示 JSON 输入输出
- `DiffPreview` — 文件变更预览
- `ApprovalDialog` — 人工审批门控，审批/拒绝操作
- `StatusIndicator` — 动画脉冲指示当前 Agent 步骤

**状态管理** — Zustand Store：
- `appendToLastAssistant()` 实现零闪烁流式文本更新
- `localStorage` 持久化 Session
- 首次访问自动创建 Session

---

### 8. 沙箱与工作区隔离

> `backend/app/services/sandbox_service.py`

每个 Session 独立的隔离工作区，确保 Agent 安全执行。

**工作区生命周期**
```
create_workspace(session_id, source_path)
  -> Git 仓库？Clone --depth 1
  -> 普通目录？shutil.copytree
  -> 无源路径？空工作区

destroy_workspace(session_id)
  -> 完全清理 /tmp/codex-sandbox/{session_id}/
```

**安全层级**

| 层级 | 机制 |
|------|------|
| 路径隔离 | `resolve()` + 前缀检查，防止 `../` 逃逸 |
| 命令白名单 | 仅白名单内的可执行文件可运行 |
| 审批门控 | 危险操作暂停等待人工审查 |
| 资源限制 | 120 秒超时、8KB 输出上限、16 步 Agent 上限 |
| 环境隔离 | 精简环境变量、沙箱化 HOME 目录 |
| 推送阻断 | `git push` 在工具系统中永久禁用 |

---

### 9. 认证与多租户体系

> `backend/app/services/auth_service.py`

**Google OAuth 2.0 登录**
- 前端通过 Google Sign-In 获取 ID Token
- 后端通过 `oauth2.googleapis.com/tokeninfo` 验证
- 首次登录自动创建用户、租户、成员关系
- 签发 Bearer Token（24 小时有效期）

**多租户隔离**
- 所有资源（Session、Run）均绑定 `tenant_id`
- 用户可属于多个租户，切换租户时签发新 Token
- 角色体系：`member`、`admin`

**邀请系统**
- Owner/Admin 发起邀请，邮件自动送达（Resend / SendGrid）
- 唯一邀请码，默认 72 小时过期
- 受邀者通过邀请码加入租户
- 追踪邀请人身份和备注用于审计

---

### 10. IDE 集成

> `extension/` — VS Code Extension

- **命令**：`Coding Agent: Ask` — 从任意文件触发
- **当前文件感知**：自动捕获活跃编辑器文件路径，提升上下文相关性
- **附件支持**：可指定图片、音频、文档作为多模态输入
- **可配置端点**：通过 `codingAgent.baseUrl` 设置指向任意后端实例
- **Session 持久化**：Session ID 存储在 VS Code globalState 中，跨重启保持

### 11. Data Agent 数据分析子系统

> `backend/app/api/data_routes.py` + `backend/app/services/data_agent_service.py`

在现有 DeepAgent 编排之上新增数据分析能力，形成“上传数据 -> 自动建模上下文 -> 对话分析/代码执行 -> 图表流式回显”的闭环。

**业界对标与借鉴**

| 产品 | 核心能力 | 本项目借鉴点 |
|------|----------|--------------|
| Julius AI | 文件优先 + Learning Sub Agent | 自动 Schema 发现 + 统计摘要注入 |
| ChatGPT Code Interpreter | Jupyter 内核 | 会话级有状态 Python Kernel |
| Cursor | Planner/Worker/Judge | 复用现有多角色编排 + DataAnalyst 角色 |
| Devin | 自愈循环 | 失败重试 + 动态重规划 |
| Databricks Assistant | Schema + 人工参与 | Schema 注入 + 审批门控 |
| Replit Agent | 有状态/无状态执行 | 会话级 Kernel 管理 |

**新增能力架构**

```
DataAnalysisPanel(React)
  -> /api/v1/data/upload
  -> /api/v1/data/analyze (SSE)
  -> /api/v1/data/execute
  -> /api/v1/data/auto-eda (SSE)
  -> /api/v1/data/datasets

FastAPI Data Router
  -> DataService: 文件摄入 / Schema发现 / 统计摘要
  -> PythonKernelService: 会话级有状态执行
  -> DataAgentRunner: LLM + Tool 编排
  -> DataTools: execute_python / analyze_dataset / generate_chart / query_data
```

**新增后端文件**
- `backend/app/services/data_service.py`：数据摄入、字段剖析、统计摘要、样本提取
- `backend/app/services/python_kernel_service.py`：有状态 Python 子进程内核与会话管理
- `backend/app/services/data_agent_service.py`：Data Agent 编排与 Auto EDA 流水线
- `backend/app/tools/data_tools.py`：4 个 Data Tool
- `backend/app/api/data_routes.py`：数据上传、查询、分析、执行、自动 EDA 接口
- `sql/migrations/20260305_data_agent_tables.sql`：`datasets` / `dataset_columns` / `data_analysis_runs` 三张表

**新增前端文件**
- `frontend/src/components/DataAnalysisPanel.tsx`：数据分析主界面（上传、对话、图表、代码执行）
- `frontend/src/components/DataUploadPanel.tsx`：拖拽上传
- `frontend/src/components/DatasetExplorer.tsx`：Schema/样本/统计查看
- `frontend/src/components/CodeCell.tsx`：Jupyter 风格代码单元执行
- `frontend/src/components/ChartViewer.tsx`：Base64 图表渲染

**差异化能力**
1. 有状态 Python 内核：变量和 DataFrame 在同一 session 内可复用
2. 自动 Schema 注入：上传后自动发现字段类型、缺失、统计量并注入 LLM 上下文
3. Auto EDA 流水线：一键执行数据加载、缺失分析、统计、分布、相关性分析
4. 图表流式回传：执行中捕获 matplotlib 图像并通过 SSE 推送前端
5. 安全沙箱：限制危险调用与执行超时，降低代码执行风险
6. 多租户隔离：dataset 绑定 `tenant_id + session_id`，与现有权限体系一致
7. 编排复用：DataAgentRunner 继承 AgentRunner，复用既有 streaming + tool-use 基建

---

## API 设计

> `backend/app/api/routes.py` — 19+ REST 端点 + SSE + WebSocket

**Agent 执行**

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/agent/stream` | POST | LLM Agent + SSE 流式响应 |
| `/agent/ws/{run_id}` | WS | 实时审批流 |
| `/generate` | POST | DeepAgent 编排器（完整流水线） |
| `/agent/runs/{run_id}` | GET | 运行详情（Todo、评估、审批） |
| `/agent/runs/{run_id}/approve` | POST | 人工审批/拒绝 |

**上下文与知识**

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/context/index` | POST | 索引工作区（文件、符号、依赖、知识块） |
| `/context/query` | POST | 自然语言 RAG 检索 |
| `/project/init` | POST | 构建项目图谱 + 向量索引 |
| `/project/context` | POST | 文件感知的项目上下文检索 |
| `/project/callers` | POST | 查找函数的所有调用者 |
| `/memory/optimize` | POST | 压缩 Session 记忆 |

**认证与租户**

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/auth/google/login` | POST | Google ID Token 登录 |
| `/auth/me` | GET | 当前用户 + 租户信息 |
| `/auth/tenants` | GET | 列出用户所有租户 |
| `/auth/tenant/switch` | POST | 切换租户并签发新 Token |
| `/auth/tenant/invitations` | POST | 邀请成员（邮件送达） |
| `/auth/tenant/invitations` | GET | 列出租户邀请 |
| `/auth/tenant/invitations/accept` | POST | 接受邀请 |
| `/sessions` | POST | 创建 Session |
| `/health` | GET | 健康检查 |

**数据分析**

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/data/upload` | POST | 上传 CSV/Excel/JSON/Parquet 并自动建模 |
| `/data/datasets` | GET | 列出数据集（支持按 session 过滤） |
| `/data/datasets/{dataset_id}` | GET | 查询数据集详情（Schema/样本/统计） |
| `/data/datasets/{dataset_id}` | DELETE | 删除数据集与关联文件 |
| `/data/execute` | POST | 在有状态 Python Kernel 直接执行代码 |
| `/data/analyze` | POST | Data Agent 流式分析（SSE） |
| `/data/auto-eda` | POST | 自动 EDA 流水线（SSE） |

---

## 数据层（20+ 张表）

> OceanBase (MySQL 模式) + SQLite 开发降级

**认证与租户域**
```
tenants -> tenant_members (角色)
tenants -> tenant_invitations (邀请码、状态、过期时间)
users -> google_identities (google_sub)
auth_tokens (user_id, tenant_id, expires_at, revoked)
sessions (tenant_id, owner_user_id)
```

**Session 域**
```
sessions -> requirements (优先级、估算点数)
         -> interaction_memories (content_hash、重要性、置顶)
```

**Agent 运行时域**
```
agent_runs -> agent_todos (角色、依赖 JSON、尝试次数)
           -> task_evaluations (通过、分数、原因、下一步动作)
           -> approval_events (门控类型、决策、操作者)
           -> agent_file_changes (变更类型、diff 文本、状态)
```

**知识域**
```
project_files -> code_symbols (名称、类型、签名、文档注释)
              -> dependency_edges (源文件 -> 目标模块)
              -> knowledge_chunks (文本、关键词、行范围)
```

**图谱与向量域**
```
project_graph_nodes (file / symbol / module)
project_graph_edges (contains / depends_on / calls / extends)
project_vectors (64 维 Embedding、Cosine Similarity)
```

**可观测性**
```
tool_calls (工具名、请求、响应、延迟毫秒)
audit_events (操作者、动作、实体追踪)
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18、TypeScript、Vite、Tailwind CSS、Zustand |
| 后端 | FastAPI、SQLAlchemy 2.0、Pydantic v2 |
| LLM | Anthropic Claude API（Streaming Tool-Use） |
| 数据库 | OceanBase (MySQL 模式) / SQLite 降级兜底 |
| 实时通信 | Server-Sent Events (SSE) + WebSocket |
| IDE | VS Code Extension (TypeScript) |
| 多模态 | Tesseract OCR、Whisper ASR |

---

## 项目结构

```
codingAgent/
  backend/
    app/
      api/           # 路由 + Pydantic Schema
      core/          # 配置管理（pydantic-settings）
      repositories/  # 数据访问层（Repository 模式）
      services/      # Agent、LLM、Memory、RAG、Context、Sandbox、Multimodal
      tools/         # 文件操作、Shell、Git、RAG（12 个内置工具）
      models.py      # SQLAlchemy ORM（20+ 实体）
      db.py          # 同步 + 异步引擎，自动降级
      main.py        # FastAPI 应用（CORS + 静态文件）
    tests/           # pytest 测试套件
  frontend/
    src/
      api/           # HTTP + SSE 客户端
      components/    # ChatPanel、ToolCallCard、DiffPreview、ApprovalDialog
      hooks/         # useAgentStream、useSession
      stores/        # Zustand 状态管理
  extension/         # VS Code 插件
  scripts/           # 离线索引管道
  sql/               # OceanBase Schema + Migration
  docs/              # 架构设计文档
```

---

## 快速启动

```bash
# 1. 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "LLM_API_KEY=your-api-key" > .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# 2. 前端
cd frontend
npm install
cp .env.example .env.local
# 在 .env.local 中设置 VITE_GOOGLE_CLIENT_ID
npm run dev
# -> http://localhost:5173

# 3.（可选）初始化 OceanBase
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/init_oceanbase.sql
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/migrations/20260303_auth_tenant_isolation.sql
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/migrations/20260303_auth_tenant_invitations.sql
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/migrations/20260305_data_agent_tables.sql

# 4.（可选）构建项目索引以增强 RAG
python3 scripts/build_context.py --workspace . --repo codingAgent --branch main
python3 scripts/build_project_context.py --workspace . --repo codingAgent --branch main
```

若 `pymysql` 不可用，应用自动降级到本地 SQLite（`coding_agent_dev.db`）。

### Makefile 快捷命令

```bash
make backend-install    # 创建虚拟环境 + 安装依赖
make backend-run        # 启动 FastAPI（端口 8080）
make backend-test       # 运行 pytest
make frontend-install   # npm install
make frontend-dev       # Vite 开发服务器（端口 5173）
make frontend-build     # 生产构建
make context-index      # 构建 RAG 上下文索引
make project-index      # 构建项目图谱 + 向量索引
```

---

## 环境变量配置

<details>
<summary>点击展开完整配置说明</summary>

### 认证配置
```bash
AUTH_REQUIRED=true                          # 强制 Bearer 认证
AUTH_ACCESS_TOKEN_TTL_HOURS=24              # Token 有效期
AUTH_GOOGLE_VERIFY_MODE=tokeninfo           # 生产模式；dev_unverified 用于本地调试
AUTH_GOOGLE_CLIENT_IDS=<google-client-id>   # 允许的 Google Client ID（逗号分隔）
```

### 邀请邮件配置
```bash
INVITE_EMAIL_ENABLED=true                   # 启用邮件发送
INVITE_EMAIL_PROVIDER=resend|sendgrid|noop  # 邮件提供商
INVITE_EMAIL_REQUIRED=true|false            # true 时发送失败返回 502
INVITE_ACCEPT_URL_BASE=https://your-domain  # 前端域名
INVITE_EMAIL_FROM=noreply@yourdomain.com    # 发件人
RESEND_API_KEY=...                          # Resend API Key
SENDGRID_API_KEY=...                        # SendGrid API Key
```

### LLM 配置
```bash
LLM_API_KEY=sk-...                          # LLM API Key
LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4-plus                       # 主模型
LLM_VISION_MODEL=glm-4v-plus               # 视觉模型
LLM_MAX_TOKENS=4096                         # 最大输出 Token
```

### 数据库配置
```bash
OCEANBASE_HOST=127.0.0.1
OCEANBASE_PORT=2881
OCEANBASE_USER=root@test
OCEANBASE_PASSWORD=
OCEANBASE_DATABASE=coding_agent
```

</details>
