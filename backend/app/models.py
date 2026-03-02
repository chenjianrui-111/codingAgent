import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TenantEntity(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    users: Mapped[list["TenantMemberEntity"]] = relationship(back_populates="tenant")
    sessions: Mapped[list["SessionEntity"]] = relationship(back_populates="tenant")
    auth_tokens: Mapped[list["AuthTokenEntity"]] = relationship(back_populates="tenant")
    invitations: Mapped[list["TenantInvitationEntity"]] = relationship(back_populates="tenant")


class UserEntity(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    identities: Mapped[list["GoogleIdentityEntity"]] = relationship(back_populates="user")
    memberships: Mapped[list["TenantMemberEntity"]] = relationship(back_populates="user")
    sessions: Mapped[list["SessionEntity"]] = relationship(back_populates="owner_user")
    auth_tokens: Mapped[list["AuthTokenEntity"]] = relationship(back_populates="user")
    sent_invitations: Mapped[list["TenantInvitationEntity"]] = relationship(
        back_populates="invited_by_user",
        foreign_keys="TenantInvitationEntity.invited_by_user_id",
    )
    accepted_invitations: Mapped[list["TenantInvitationEntity"]] = relationship(
        back_populates="accepted_by_user",
        foreign_keys="TenantInvitationEntity.accepted_by_user_id",
    )


class TenantMemberEntity(Base):
    __tablename__ = "tenant_members"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uk_tenant_member"),)

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    tenant: Mapped[TenantEntity] = relationship(back_populates="users")
    user: Mapped[UserEntity] = relationship(back_populates="memberships")


class GoogleIdentityEntity(Base):
    __tablename__ = "google_identities"

    identity_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    google_sub: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_profile_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user: Mapped[UserEntity] = relationship(back_populates="identities")


class AuthTokenEntity(Base):
    __tablename__ = "auth_tokens"

    token_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    access_token: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    user: Mapped[UserEntity] = relationship(back_populates="auth_tokens")
    tenant: Mapped[TenantEntity] = relationship(back_populates="auth_tokens")


class TenantInvitationEntity(Base):
    __tablename__ = "tenant_invitations"

    invitation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invite_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    invitee_email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    invited_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped[TenantEntity] = relationship(back_populates="invitations")
    invited_by_user: Mapped[UserEntity] = relationship(
        back_populates="sent_invitations",
        foreign_keys=[invited_by_user_id],
    )
    accepted_by_user: Mapped[UserEntity | None] = relationship(
        back_populates="accepted_invitations",
        foreign_keys=[accepted_by_user_id],
    )


class SessionEntity(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    influencer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    tenant: Mapped[TenantEntity | None] = relationship(back_populates="sessions")
    owner_user: Mapped[UserEntity | None] = relationship(back_populates="sessions")
    requirements: Mapped[list["RequirementEntity"]] = relationship(back_populates="session")
    memories: Mapped[list["InteractionMemoryEntity"]] = relationship(back_populates="session")


class RequirementEntity(Base):
    __tablename__ = "requirements"

    requirement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    estimated_points: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    session: Mapped[SessionEntity] = relationship(back_populates="requirements")
    tasks: Mapped[list["TaskEntity"]] = relationship(back_populates="requirement")
    agent_runs: Mapped[list["AgentRunEntity"]] = relationship(back_populates="requirement")


class TaskEntity(Base):
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.requirement_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    requirement: Mapped[RequirementEntity] = relationship(back_populates="tasks")


class ToolCallEntity(Base):
    __tablename__ = "tool_calls"

    call_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ProjectFileEntity(Base):
    __tablename__ = "project_files"

    file_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class CodeSymbolEntity(Base):
    __tablename__ = "code_symbols"

    symbol_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    symbol_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    symbol_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    signature: Mapped[str | None] = mapped_column(String(512), nullable=True)
    docstring: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class DependencyEdgeEntity(Base):
    __tablename__ = "dependency_edges"

    edge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_file: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    target_module: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False, default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class InteractionMemoryEntity(Base):
    __tablename__ = "interaction_memories"

    memory_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    session: Mapped[SessionEntity] = relationship(back_populates="memories")


class KnowledgeChunkEntity(Base):
    __tablename__ = "knowledge_chunks"

    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="code")
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ProjectGraphNodeEntity(Base):
    __tablename__ = "project_graph_nodes"

    node_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    node_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ProjectGraphEdgeEntity(Base):
    __tablename__ = "project_graph_edges"

    edge_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    target_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    edge_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class ProjectVectorEntity(Base):
    __tablename__ = "project_vectors"

    vector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_key: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class AgentRunEntity(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.session_id"), nullable=False, index=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.requirement_id"), nullable=False, index=True)
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    interpreted_query: Mapped[str] = mapped_column(Text, nullable=False)
    persona_name: Mapped[str] = mapped_column(String(64), nullable=False, default="coding_deep_agent")
    complexity: Mapped[str] = mapped_column(String(16), nullable=False, default="simple")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    requirement: Mapped[RequirementEntity] = relationship(back_populates="agent_runs")
    todos: Mapped[list["AgentTodoEntity"]] = relationship(back_populates="run")
    evaluations: Mapped[list["TaskEvaluationEntity"]] = relationship(back_populates="run")
    approvals: Mapped[list["ApprovalEventEntity"]] = relationship(back_populates="run")


class AgentTodoEntity(Base):
    __tablename__ = "agent_todos"

    todo_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"), nullable=False, index=True)
    parent_todo_id: Mapped[int | None] = mapped_column(ForeignKey("agent_todos.todo_id"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[str] = mapped_column(String(512), nullable=False)
    depends_on_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    run: Mapped[AgentRunEntity] = relationship(back_populates="todos")
    evaluations: Mapped[list["TaskEvaluationEntity"]] = relationship(back_populates="todo")
    approvals: Mapped[list["ApprovalEventEntity"]] = relationship(back_populates="todo")


class TaskEvaluationEntity(Base):
    __tablename__ = "task_evaluations"

    evaluation_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"), nullable=False, index=True)
    todo_id: Mapped[int] = mapped_column(ForeignKey("agent_todos.todo_id"), nullable=False, index=True)
    evaluator: Mapped[str] = mapped_column(String(32), nullable=False, default="rule_evaluator")
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    run: Mapped[AgentRunEntity] = relationship(back_populates="evaluations")
    todo: Mapped[AgentTodoEntity] = relationship(back_populates="evaluations")


class ApprovalEventEntity(Base):
    __tablename__ = "approval_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"), nullable=False, index=True)
    todo_id: Mapped[int | None] = mapped_column(ForeignKey("agent_todos.todo_id"), nullable=True, index=True)
    gate_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual_gate")
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    operator: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    run: Mapped[AgentRunEntity] = relationship(back_populates="approvals")
    todo: Mapped[AgentTodoEntity | None] = relationship(back_populates="approvals")


class AgentFileChangeEntity(Base):
    """Tracks file modifications proposed by the agent for review/apply/reject."""

    __tablename__ = "agent_file_changes"

    change_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)  # create / edit / delete
    old_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_content: Mapped[str] = mapped_column(Text, nullable=False)
    diff_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending / applied / rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
