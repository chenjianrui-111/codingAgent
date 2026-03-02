# Coding Agent — Enterprise-Grade AI Coding Platform

An autonomous AI coding agent platform with DeepAgent orchestration, multi-layer RAG retrieval, project-level knowledge graph, streaming tool-use, and a full-stack Web UI. Built for real-world software engineering workflows.

## Architecture Overview

```
                         +------------------+
                         |   Web Frontend   |  React + SSE Streaming
                         |  (Chat / Diff /  |
                         |   Tool Cards)    |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   FastAPI Server  |  REST + SSE + WebSocket
                         |   /api/v1/*       |
                         +--------+---------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
     +--------v------+  +--------v--------+  +-------v--------+
     | Agent Runner   |  | Agent           |  | Tool System    |
     | (LLM Streaming |  | Orchestrator    |  | File / Shell / |
     |  Tool-Use Loop)|  | (DeepAgent Loop)|  | Git / RAG      |
     +--------+------+  +--------+--------+  +-------+--------+
              |                   |                   |
     +--------v-------------------v-------------------v--------+
     |                    Service Layer                         |
     |  LLM Service | Memory Manager | RAG Service | Sandbox   |
     |  Context Indexer | Project Context | Multimodal | Test   |
     +----------------------------+----------------------------+
                                  |
              +-------------------+-------------------+
              |                                       |
     +--------v--------+                    +---------v-------+
     | OceanBase / MySQL|                    | File System     |
     | (20+ tables)     |                    | Artifacts +     |
     | SQLite fallback   |                    | Sandbox         |
     +------------------+                    +-----------------+
```

---

## Module Highlights

### 1. DeepAgent Orchestration Engine

> `backend/app/services/agent_service.py` — 655 lines

Production-grade agentic loop with planning, execution, evaluation, and self-healing capabilities.

**Multi-Role Worker Pipeline**

| Role | Responsibility |
|------|---------------|
| **PlannerAgent** | Decompose user requirement into a dependency-aware todo DAG |
| **CoderAgent** | Generate code changes with RAG-injected project context |
| **TesterAgent** | Execute test suite, validate exit_code = 0 |
| **ReviewerAgent** | Risk assessment, delivery notes, final quality gate |

**Intelligent Execution Loop**

```
User Query
  -> Persona Interpreter (normalize, cap at 4000 chars)
  -> Complexity Assessment (simple/complex, heuristic keyword detection)
  -> Planning Tool (build todo DAG with inter-task dependencies)
  -> Execution Loop (max 16 steps):
       Pick next ready todo (all deps completed)
       -> Risk Check: risky keywords detected?
            Yes -> Create ApprovalEvent, pause for human decision
            No  -> Execute worker agent
       -> Evaluate result (rule-based: exit_code, output length, keywords)
       -> Failed & retries remaining?
            Yes -> Reflector injects failure context, re-attempt
            No  -> Mark failed, continue to next
       -> Test failure? -> Auto-inject remediation loop (coder -> tester)
  -> Aggregate artifacts + summary
```

**Self-Healing & Retry**
- Configurable retry budget per todo (default: 2 attempts)
- `ReflectorAgent` analyzes failure reason and injects corrective instructions
- Test failures trigger automatic coder-tester remediation cycles
- All intermediate outputs persisted as artifacts at `.deepagent/runs/{run_id}/`

**Human Approval Gates**
- Pre-execution keyword scanning for dangerous operations (`DROP TABLE`, `rm -rf`, `ALTER TABLE`, `migration`, etc.)
- Blocks execution, creates `ApprovalEvent` record, awaits human decision
- Approval/rejection tracked with operator identity and comment for audit trail

---

### 2. LLM-Driven Agent Runner (Streaming Tool-Use)

> `backend/app/services/agent_runner.py` + `backend/app/services/llm_service.py`

Real-time Claude API integration with streaming tool-use for autonomous coding.

**Streaming Architecture**
- Anthropic `AsyncAnthropic` client with `messages.stream()` API
- Real-time chunk types: `text_delta` | `tool_use` | `message_stop`
- Zero-buffering: text and tool calls emitted as they arrive
- Server-Sent Events (SSE) protocol for frontend consumption

**Agentic Loop**
```
1. Gather RAG context + session memory -> build system prompt
2. Stream LLM response with tool definitions
3. On text_delta -> push SSE event to frontend (real-time typing)
4. On tool_use -> execute tool -> push result -> continue conversation
5. On no tool calls -> agent finished
6. Max 16 steps safety boundary
```

**Context-Aware System Prompt**
- Injects workspace path and current file context
- RAG-retrieved code snippets from project knowledge graph
- Session memory summary from MemoryManager
- Coding best practices (read before edit, minimal changes, run tests)

---

### 3. Tool System with Sandbox Security

> `backend/app/tools/`

12 built-in tools with path sandboxing, command allowlisting, and resource limits.

**File Operations** (`file_ops.py`)

| Tool | Capability | Security |
|------|-----------|----------|
| `read_file` | Line-numbered output with offset/limit pagination | Path sandbox validation |
| `write_file` | Create or overwrite files, auto-create parent dirs | Sandbox escape prevention |
| `edit_file` | Exact string match replacement (rejects ambiguous matches) | Single-match enforcement |
| `list_directory` | Recursive tree view with 500-entry cap | Traversal protection |
| `search_files` | Regex grep with glob filtering, 100-match cap | Output truncation (8KB) |

**Shell Execution** (`shell.py`)
- **Command Allowlist**: Only whitelisted executables run (`git`, `python`, `pytest`, `npm`, `node`, `make`, etc.)
- **Environment Isolation**: Strips all env vars except `PATH`, `HOME`, `USER`, `LANG`, `TERM`, `SHELL`; sets `HOME` to sandbox
- **Resource Limits**: 120-second timeout via `asyncio.wait_for`, output truncated at 8KB stdout + 2KB stderr
- **Exit Code Tracking**: Structured output with `exit_code=N` for downstream evaluation

**Git Operations** (`git_ops.py`)
- `git_status`, `git_diff` (staged/unstaged), `git_log` (configurable depth)
- `git_commit` — stage specific files + atomic commit
- `git_branch` — list, create, and switch branches
- `git push` **permanently blocked** — prevents unreviewed code from reaching remote

**RAG Context Tool** (`rag_tool.py`)
- Bridges existing RAG infrastructure into the LLM tool-use system
- LLM can autonomously search the indexed codebase during problem-solving

**Path Sandbox Enforcement**
```python
# All file tools enforce this before any I/O:
resolved = (Path(workspace) / relative_path).resolve()
if not str(resolved).startswith(str(Path(workspace).resolve())):
    raise PermissionError("Path escapes sandbox")
```

---

### 4. Multi-Layer RAG & Context Retrieval

> `backend/app/services/rag_service.py` + `context_service.py` + `project_context_service.py`

Three-tier retrieval with fallback chain: Project Graph -> Context Index -> Workspace Scan.

**Tier 1: Project Knowledge Graph** (`project_context_service.py` — 700+ lines)

Builds a semantic graph of the entire codebase:

| Node Type | Content |
|-----------|---------|
| `file` | Source files with path, type, size |
| `symbol` | Functions, classes with signatures and docstrings |
| `module` | Logical module groupings |

| Edge Type | Meaning |
|-----------|---------|
| `contains` | File contains symbol |
| `depends_on` | File imports module |
| `calls` | Symbol invokes symbol |
| `calls_file` | Symbol references file |
| `extends` | Class inheritance |

**Priority-Based Context Clipping**
```
Current file:       +2.5 priority boost
Direct dependencies: +1.4 (1-hop in dependency graph)
Indirect deps:       +0.8 (2-hop transitive)
Config files:        +0.5 (yaml, json, env)
```

**Vector Similarity Search**
- Deterministic 64-dim token-hash embeddings (no external API required)
- Cosine similarity ranking across all indexed entities
- Combined with graph-distance scoring for hybrid retrieval

**Tier 2: Context Index** (`context_service.py` — 270+ lines)

| Capability | Implementation |
|-----------|---------------|
| Symbol Extraction | Python AST parsing (classes, functions, signatures, docstrings); JS/TS regex patterns |
| Dependency Tracking | `ast.Import`/`ast.ImportFrom` for Python; `import`/`require` regex for JS/TS |
| Knowledge Chunking | 60-line semantic chunks with keyword extraction |
| Retrieval Scoring | Token overlap + recency weighting + pinned/summary bonus (+0.6) |

Supported file types: `.py`, `.ts`, `.tsx`, `.js`, `.java`, `.md`, `.yaml`, `.yml`, `.json`

**Tier 3: Workspace Fallback**
- Direct file system scan when no index is available
- Reads first 8 lines of each file as preview snippets
- Budget-limited to 5000 chars

**Cross-File Understanding**
```bash
# Find all files that call a specific function
POST /api/v1/project/callers
{"function_name": "run", "repo_name": "codingAgent", "branch_name": "main"}
```

---

### 5. Session Memory Management

> `backend/app/services/memory_service.py`

Intelligent conversation memory with deduplication, importance scoring, and automatic compression.

**Deduplication**
- SHA256 content hash on normalized text
- Identical messages across a session are stored once

**Importance Scoring & Pinning**
- 5-level importance score (1-5) for priority-based retrieval
- Pinned messages are never evicted during compression
- Summary memories created with importance=4 and auto-pinned

**Auto-Compression Strategy**
```
When session exceeds 80 items:
  1. Keep most recent 36 items untouched
  2. Select oldest unpinned, non-summary items
  3. Batch 16 items -> extract topic words -> generate summary
  4. Store summary as pinned memory (importance=4)
  5. Delete original batch
```

**Context Budget Control**
- Memory retrieval capped at 5000 chars per query
- Prevents token bloat in LLM system prompts
- Recency-weighted scoring ensures recent context ranks higher

---

### 6. Multimodal Input Processing

> `backend/app/services/multimodal_service.py`

Accept images, audio, and documents as task inputs alongside text queries.

| Input Type | Processing | Tool |
|-----------|-----------|------|
| **Image** | OCR text extraction | Tesseract CLI |
| **Audio** | Speech-to-text transcription | Whisper CLI |
| **Document** | Text extraction | Direct file read |
| **Text** | Inline or file-based | Native |

**Resilient Pipeline**
- Supports file path, inline text, and base64 encoded inputs
- Graceful fallback: records failures in `notes[]` without crashing
- Each attachment's extracted text capped at 1600 chars
- Query enriched with `[ATTACHMENT_CONTEXT]` block
- Full preprocessing summary tracked: `attachment_count`, `processed_count`, `extracted_count`, `failed_count`

---

### 7. Real-Time Web Frontend

> `frontend/` — React 18 + TypeScript + Vite + Tailwind CSS + Zustand

Full-featured chat interface with streaming agent output and interactive tool cards.

**SSE Streaming Protocol**

| Event Type | Data | UI Behavior |
|-----------|------|-------------|
| `status` | `{message, step}` | Status indicator with step counter |
| `text_delta` | `{text}` | Real-time character-by-character rendering |
| `tool_call` | `{tool, input, id}` | Expandable tool call card |
| `tool_result` | `{id, success, output}` | Success/failure badge + collapsible output |
| `diff_preview` | `{path, detail}` | File change preview with path highlight |
| `approval_required` | `{run_id, reason}` | Approve/Reject dialog |
| `done` | `{run_id, status}` | Stream completion |

**Component Architecture**
- `ChatPanel` — Main conversation view with auto-scroll
- `MessageBubble` — Markdown rendering with syntax highlighting (react-syntax-highlighter + VSCode Dark+ theme)
- `ToolCallCard` — Expand/collapse tool invocations with JSON input and output display
- `DiffPreview` — File modification preview with path header
- `ApprovalDialog` — Human approval gate with Approve/Reject actions
- `StatusIndicator` — Animated pulse indicator showing current agent step

**State Management** — Zustand store with message streaming support:
- `appendToLastAssistant()` for zero-flicker streaming text updates
- Session persistence via `localStorage`
- Automatic session creation on first visit

---

### 8. Sandbox & Workspace Isolation

> `backend/app/services/sandbox_service.py`

Per-session isolated workspaces for safe agent execution.

**Workspace Lifecycle**
```
create_workspace(session_id, source_path)
  -> Git repo? Clone with --depth 1
  -> Plain dir? shutil.copytree
  -> No source? Empty workspace

destroy_workspace(session_id)
  -> Full cleanup of /tmp/codex-sandbox/{session_id}/
```

**Security Layers**

| Layer | Mechanism |
|-------|-----------|
| Path Containment | `resolve()` + prefix check prevents `../` escape |
| Command Allowlist | Only whitelisted executables can run |
| Approval Gates | Dangerous operations pause for human review |
| Resource Limits | 120s timeout, 8KB output cap, 16-step agent limit |
| Environment Isolation | Stripped env vars, sandboxed HOME |
| Push Blocking | `git push` permanently disabled in tool system |

---

### 9. API Design

> `backend/app/api/routes.py` — 19+ REST endpoints + SSE + WebSocket

**Agent Execution**

| Endpoint | Method | Description |
|---------|--------|-------------|
| `/agent/stream` | POST | LLM-driven agent with SSE streaming |
| `/agent/ws/{run_id}` | WS | Real-time approval flow |
| `/generate` | POST | DeepAgent orchestrator (full pipeline) |
| `/agent/runs/{run_id}` | GET | Run detail with todos, evaluations, approvals |
| `/agent/runs/{run_id}/approve` | POST | Human approval/rejection |

**Context & Knowledge**

| Endpoint | Method | Description |
|---------|--------|-------------|
| `/context/index` | POST | Index workspace (files, symbols, deps, chunks) |
| `/context/query` | POST | RAG retrieval by natural language query |
| `/project/init` | POST | Build project graph + vector index |
| `/project/context` | POST | File-aware project context retrieval |
| `/project/callers` | POST | Find all callers of a function |
| `/memory/optimize` | POST | Compress session memory |

**Session Management**

| Endpoint | Method | Description |
|---------|--------|-------------|
| `/auth/google/login` | POST | Google ID token login, returns bearer token + tenant context |
| `/auth/me` | GET | Current authenticated user + tenant info |
| `/auth/tenants` | GET | List all tenant memberships of current user |
| `/auth/tenant/switch` | POST | Switch active tenant and mint a new tenant-scoped bearer token |
| `/auth/tenant/invitations` | POST | Owner/Admin invites a member by email (returns `invite_link` + email delivery status) |
| `/auth/tenant/invitations` | GET | Owner/Admin lists tenant invitations |
| `/auth/tenant/invitations/accept` | POST | Invitee accepts invitation and gets tenant-scoped token |
| `/sessions` | POST | Create user session |
| `/health` | GET | Service health check |

---

### 10. Data Layer (20+ Tables)

> OceanBase (MySQL mode) with SQLite fallback for development

**Session Domain**
```
sessions -> requirements (priority, estimated_points)
         -> interaction_memories (content_hash, importance, pinned)
```

**Auth & Tenant Domain**
```
tenants -> tenant_members (role)
tenants -> tenant_invitations (invite_code, status, expires_at)
users -> google_identities (google_sub)
auth_tokens (user_id, tenant_id, expires_at, revoked)
sessions (tenant_id, owner_user_id)
```

**Agent Runtime Domain**
```
agent_runs -> agent_todos (role, depends_on_json, attempt_count)
           -> task_evaluations (passed, score, reason, next_action)
           -> approval_events (gate_type, decision, operator)
           -> agent_file_changes (change_type, diff_text, status)
```

**Knowledge Domain**
```
project_files -> code_symbols (name, type, signature, docstring)
              -> dependency_edges (source_file -> target_module)
              -> knowledge_chunks (text, keywords, line range)
```

**Graph & Vector Domain**
```
project_graph_nodes (file / symbol / module)
project_graph_edges (contains / depends_on / calls / extends)
project_vectors (64-dim embeddings, cosine similarity)
```

**Observability**
```
tool_calls (tool_name, request, response, latency_ms)
audit_events (actor, action, entity tracking)
```

---

### 11. IDE Integration

> `extension/` — VS Code Extension

- **Command**: `Coding Agent: Ask` — trigger agent from any file
- **Current File Awareness**: Automatically captures active editor file path, boosting context relevance
- **Attachment Support**: Specify images, audio, and documents as multimodal inputs
- **Configurable Endpoint**: Point to any backend instance via `codingAgent.baseUrl` setting
- **Session Persistence**: Session ID stored in VS Code global state across restarts

---

## Quick Start

```bash
# 1. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-xxx" > .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# 2. Frontend
cd frontend
npm install
cp .env.example .env.local
# set VITE_GOOGLE_CLIENT_ID in .env.local
npm run dev
# -> http://localhost:5173

# 3. (Optional) Initialize OceanBase
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/init_oceanbase.sql
# Existing DB upgrade:
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/migrations/20260303_auth_tenant_isolation.sql
mysql -h127.0.0.1 -P2881 -uroot@test -p < sql/migrations/20260303_auth_tenant_invitations.sql

# 4. (Optional) Build project index for enhanced RAG
python3 scripts/build_context.py --workspace . --repo codingAgent --branch main
python3 scripts/build_project_context.py --workspace . --repo codingAgent --branch main
```

If `pymysql` is unavailable, the app falls back to local SQLite (`coding_agent_dev.db`) automatically.

Auth/Tenant env knobs (optional):
- `AUTH_REQUIRED=true` to force bearer auth
- `AUTH_GOOGLE_VERIFY_MODE=tokeninfo` (production) or `dev_unverified` (local debug)
- `AUTH_GOOGLE_CLIENT_IDS=<google-web-client-id>[,<another-id>]`
- `VITE_GOOGLE_CLIENT_ID=<google-web-client-id>` (frontend Google Sign-In button)
- Tenant-scoped resources (`session_id` / `run_id`) deny anonymous access once bound to a tenant.
- Invite email knobs:
  - `INVITE_EMAIL_ENABLED=true`
  - `INVITE_EMAIL_PROVIDER=resend|sendgrid|noop`
  - `INVITE_EMAIL_REQUIRED=true|false` (if `true`, invite API returns 502 when delivery fails)
  - `INVITE_ACCEPT_URL_BASE=https://your-frontend-domain`
  - `INVITE_EMAIL_FROM=noreply@yourdomain.com`
  - `RESEND_API_KEY=...` or `SENDGRID_API_KEY=...`

Google Sign-In setup (local + production):
1. In Google Cloud Console, create **OAuth 2.0 Client ID** of type **Web application**.
2. Add authorized JavaScript origins:
   - Local: `http://localhost:5173` and/or `http://127.0.0.1:5173`
   - Production: your frontend domain, e.g. `https://agent.example.com`
3. Frontend config:
   - `frontend/.env.local` (local) or deployment env (production):
     - `VITE_GOOGLE_CLIENT_ID=<your-web-client-id>`
4. Backend config:
   - `AUTH_GOOGLE_VERIFY_MODE=tokeninfo`
   - `AUTH_GOOGLE_CLIENT_IDS=<same-client-id>[,<other-allowed-client-id>]`
5. Restart frontend and backend after env changes.

Invite email delivery:
1. `POST /api/v1/auth/tenant/invitations` now auto-sends invite email when `INVITE_EMAIL_ENABLED=true`.
2. Response includes:
   - `invite_link`
   - `email_sent`
   - `email_provider`
   - `email_message_id`
   - `email_error`

### Makefile Shortcuts

```bash
make backend-install    # Create venv + install deps
make backend-run        # Start FastAPI on port 8080
make backend-test       # Run pytest
make frontend-install   # npm install
make frontend-dev       # Vite dev server on port 5173
make frontend-build     # Production build
make context-index      # Build RAG context
make project-index      # Build project graph + vectors
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| LLM | Anthropic Claude API (streaming tool-use) |
| Database | OceanBase (MySQL mode) / SQLite fallback |
| Streaming | Server-Sent Events (SSE) + WebSocket |
| IDE | VS Code Extension (TypeScript) |
| Multimodal | Tesseract OCR, Whisper ASR |

---

## Project Structure

```
codingAgent/
  backend/
    app/
      api/           # Routes + Pydantic schemas
      core/          # Configuration (pydantic-settings)
      repositories/  # Data access layer (Repository pattern)
      services/      # Agent, LLM, Memory, RAG, Context, Sandbox, Multimodal
      tools/         # File ops, Shell, Git, RAG (12 built-in tools)
      models.py      # SQLAlchemy ORM (20+ entities)
      db.py          # Sync + Async engine with fallback
      main.py        # FastAPI app with CORS + static serving
    tests/           # pytest test suite
  frontend/
    src/
      api/           # HTTP + SSE client
      components/    # ChatPanel, ToolCallCard, DiffPreview, ApprovalDialog
      hooks/         # useAgentStream, useSession
      stores/        # Zustand state management
  extension/         # VS Code extension
  scripts/           # Offline indexing pipelines
  sql/               # OceanBase schema + migrations
  docs/              # Architecture documents
```
