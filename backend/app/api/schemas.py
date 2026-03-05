from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class CreateSessionRequest(BaseModel):
    influencer_name: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(min_length=10)
    tenant_id: str | None = None
    tenant_slug: str | None = None
    tenant_name: str | None = None


class AuthUserInfo(BaseModel):
    user_id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


class AuthTenantInfo(BaseModel):
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    role: str


class GoogleLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: AuthUserInfo
    tenant: AuthTenantInfo


class AuthMeResponse(BaseModel):
    user: AuthUserInfo
    tenant: AuthTenantInfo


class TenantListResponse(BaseModel):
    current_tenant_id: str
    tenants: list[AuthTenantInfo]


class TenantSwitchRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)


class TenantSwitchResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant: AuthTenantInfo


class TenantInviteRequest(BaseModel):
    invitee_email: str = Field(min_length=3, max_length=256)
    role: str = Field(default="member", pattern="^(member|admin)$")
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class TenantInvitationItem(BaseModel):
    invitation_id: int
    invite_code: str
    invitee_email: str
    role: str
    status: str
    tenant_id: str
    invited_by_user_id: str
    accepted_by_user_id: str | None = None
    expires_at: datetime
    created_at: datetime
    accepted_at: datetime | None = None


class TenantInviteResponse(BaseModel):
    invitation: TenantInvitationItem
    tenant: AuthTenantInfo
    invite_link: str
    email_sent: bool = False
    email_provider: str | None = None
    email_message_id: str | None = None
    email_error: str | None = None


class TenantInvitationListResponse(BaseModel):
    invitations: list[TenantInvitationItem]


class TenantInvitationAcceptRequest(BaseModel):
    invite_code: str = Field(min_length=10, max_length=128)


class TenantInvitationAcceptResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    tenant: AuthTenantInfo


class AttachmentInput(BaseModel):
    kind: str = Field(pattern="^(image|audio|document|text)$")
    path: str | None = None
    text: str | None = None
    content_base64: str | None = None
    mime_type: str | None = None
    file_name: str | None = None


class MultimodalSummary(BaseModel):
    attachment_count: int
    processed_count: int
    extracted_count: int
    failed_count: int
    notes: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    session_id: str
    query: str = Field(min_length=1)
    current_file: str | None = None
    attachments: list[AttachmentInput] = Field(default_factory=list)


class TaskTrace(BaseModel):
    role: str
    instruction: str
    output: str
    status: str


class TodoState(BaseModel):
    todo_id: int
    role: str
    title: str
    status: str
    success_criteria: str
    attempt_count: int


class GenerateResponse(BaseModel):
    session_id: str
    requirement_id: int
    priority: str
    estimated_points: int
    answer: str
    traces: list[TaskTrace]
    agent_run_id: str | None = None
    todo_states: list[TodoState] = Field(default_factory=list)
    multimodal_summary: MultimodalSummary | None = None


class ContextIndexRequest(BaseModel):
    workspace: str
    repo_name: str = "codingAgent"
    branch_name: str = "main"


class ContextIndexResponse(BaseModel):
    repo_name: str
    branch_name: str
    indexed_files: int
    indexed_symbols: int
    indexed_dependencies: int
    indexed_chunks: int


class ContextQueryRequest(BaseModel):
    session_id: str
    query: str = Field(min_length=1)
    repo_name: str = "codingAgent"
    branch_name: str = "main"


class ContextQueryResponse(BaseModel):
    context: str


class MemoryOptimizeRequest(BaseModel):
    session_id: str


class MemoryOptimizeResponse(BaseModel):
    session_id: str
    before_count: int
    after_count: int
    compacted_count: int
    summary_created: bool


class ProjectInitRequest(BaseModel):
    workspace: str
    repo_name: str = "codingAgent"
    branch_name: str = "main"
    module_path: str | None = None


class ProjectInitResponse(BaseModel):
    repo_name: str
    branch_name: str
    scoped_workspace: str
    indexed_files: int
    graph_nodes: int
    graph_edges: int
    vectors: int


class ProjectContextRequest(BaseModel):
    query: str = Field(min_length=1)
    repo_name: str = "codingAgent"
    branch_name: str = "main"
    current_file: str | None = None
    max_items: int | None = None


class ProjectContextResponse(BaseModel):
    context: str
    selected_files: list[str]


class ProjectCallersRequest(BaseModel):
    function_name: str = Field(min_length=1)
    repo_name: str = "codingAgent"
    branch_name: str = "main"


class ProjectCallersResponse(BaseModel):
    function_name: str
    caller_files: list[str]


class AgentRunTodoItem(BaseModel):
    todo_id: int
    parent_todo_id: int | None = None
    role: str
    title: str
    instruction: str
    success_criteria: str
    depends_on: list[int] = Field(default_factory=list)
    status: str
    attempt_count: int
    max_attempts: int
    output_text: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskEvaluationItem(BaseModel):
    evaluation_id: int
    todo_id: int
    evaluator: str
    passed: bool
    score: int
    reason: str
    next_action: str | None = None
    created_at: datetime


class ApprovalEventItem(BaseModel):
    event_id: int
    todo_id: int | None = None
    gate_type: str
    decision: str
    operator: str
    comment: str | None = None
    created_at: datetime


class AgentRunDetailResponse(BaseModel):
    run_id: str
    session_id: str
    requirement_id: int
    original_query: str
    interpreted_query: str
    persona_name: str
    complexity: str
    status: str
    max_steps: int
    current_step: int
    created_at: datetime
    finished_at: datetime | None = None
    todos: list[AgentRunTodoItem] = Field(default_factory=list)
    evaluations: list[TaskEvaluationItem] = Field(default_factory=list)
    approval_events: list[ApprovalEventItem] = Field(default_factory=list)


class AgentRunApproveRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    operator: str = Field(min_length=1, max_length=128)
    comment: str | None = None
    gate_type: str = "manual_gate"
    todo_id: int | None = None


class AgentRunApproveResponse(BaseModel):
    run_id: str
    decision: str
    updated_todo_ids: list[int]
    run_status: str


# ---------------------------------------------------------------------------
# Streaming agent endpoint schemas
# ---------------------------------------------------------------------------

class AgentStreamRequest(BaseModel):
    session_id: str
    query: str = Field(min_length=1)
    current_file: str | None = None
    workspace: str | None = None
    attachments: list[AttachmentInput] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Data Agent schemas
# ---------------------------------------------------------------------------


class DatasetColumnInfo(BaseModel):
    name: str
    dtype: str
    nullable: bool = True
    unique_count: int = 0
    null_count: int = 0
    min_value: str | None = None
    max_value: str | None = None
    mean_value: str | None = None
    sample_values: list[str] = Field(default_factory=list)


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    name: str
    file_type: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: list[DatasetColumnInfo]
    status: str


class DatasetListItem(BaseModel):
    dataset_id: str
    name: str
    file_type: str
    row_count: int
    column_count: int
    file_size_bytes: int
    status: str
    created_at: datetime


class DatasetListResponse(BaseModel):
    datasets: list[DatasetListItem]


class DatasetDetailResponse(BaseModel):
    dataset_id: str
    name: str
    file_type: str
    file_size_bytes: int
    row_count: int
    column_count: int
    columns: list[DatasetColumnInfo]
    summary: dict | None = None
    sample_rows: list[dict] = Field(default_factory=list)
    status: str
    created_at: datetime


class DataAnalyzeRequest(BaseModel):
    session_id: str
    dataset_id: str
    query: str = Field(min_length=1)


class DataExecuteRequest(BaseModel):
    session_id: str
    code: str = Field(min_length=1)
    dataset_id: str | None = None


class DataExecuteResponse(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    display: str | None = None
    figures: list[dict] = Field(default_factory=list)
    execution_time_ms: int = 0


class DataAutoEDARequest(BaseModel):
    session_id: str
    dataset_id: str
