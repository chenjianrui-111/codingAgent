from datetime import datetime, timezone
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import (
    AuthMeResponse,
    AuthTenantInfo,
    AuthUserInfo,
    AgentRunApproveRequest,
    AgentRunApproveResponse,
    AgentRunDetailResponse,
    AgentRunTodoItem,
    AgentStreamRequest,
    ApprovalEventItem,
    MultimodalSummary,
    ContextIndexRequest,
    ContextIndexResponse,
    ContextQueryRequest,
    ContextQueryResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GoogleLoginRequest,
    GoogleLoginResponse,
    GenerateRequest,
    GenerateResponse,
    HealthResponse,
    MemoryOptimizeRequest,
    MemoryOptimizeResponse,
    ProjectCallersRequest,
    ProjectCallersResponse,
    ProjectContextRequest,
    ProjectContextResponse,
    ProjectInitRequest,
    ProjectInitResponse,
    TaskTrace,
    TaskEvaluationItem,
    TenantInvitationAcceptRequest,
    TenantInvitationAcceptResponse,
    TenantInvitationItem,
    TenantInvitationListResponse,
    TenantInviteRequest,
    TenantInviteResponse,
    TenantListResponse,
    TenantSwitchRequest,
    TenantSwitchResponse,
    TodoState,
)
from app.api.auth import get_auth_context_optional, get_auth_context_required
from app.core.config import settings
from app.db import get_db
from app.repositories.agent_repo import AgentRepository
from app.repositories.context_repo import ContextRepository
from app.services.agent_service import AgentOrchestrator
from app.services.context_service import ContextIndexer, ContextRetriever
from app.services.memory_service import MemoryManager
from app.services.multimodal_service import MultimodalPreprocessor
from app.services.project_context_service import ProjectContextManager
from app.services.rag_service import RAGService
from app.services.requirement_service import RequirementAnalyzer
from app.services.scheduler_service import TaskScheduler
from app.services.test_service import TestService
from app.services.invite_mail_service import InvitationMailer
from app.services.auth_service import (
    AuthConflictError,
    AuthContext,
    AuthPermissionError,
    AuthService,
    AuthValidationError,
    GoogleTokenVerificationError,
)

logger = logging.getLogger(__name__)

router = APIRouter()
scheduler = TaskScheduler()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="coding-agent", timestamp=datetime.now(timezone.utc))


@router.post("/auth/google/login", response_model=GoogleLoginResponse)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> GoogleLoginResponse:
    repo = AgentRepository(db)
    auth_service = AuthService(repo)
    try:
        access_token, expires_at, user, tenant, membership = auth_service.login_with_google(
            id_token=payload.id_token,
            tenant_id=payload.tenant_id,
            tenant_slug=payload.tenant_slug,
            tenant_name=payload.tenant_name,
        )
    except GoogleTokenVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    return GoogleLoginResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=AuthUserInfo(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
        ),
        tenant=AuthTenantInfo(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            tenant_slug=tenant.tenant_slug,
            role=membership.role,
        ),
    )


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> AuthMeResponse:
    repo = AgentRepository(db)
    user = repo.get_user_by_id(auth_ctx.user_id)
    tenant = repo.get_tenant_by_id(auth_ctx.tenant_id)
    membership = repo.get_tenant_membership(auth_ctx.tenant_id, auth_ctx.user_id)
    if not user or not tenant or not membership:
        raise HTTPException(status_code=404, detail="auth context not found")
    return AuthMeResponse(
        user=AuthUserInfo(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
        ),
        tenant=AuthTenantInfo(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            tenant_slug=tenant.tenant_slug,
            role=membership.role,
        ),
    )


@router.get("/auth/tenants", response_model=TenantListResponse)
def auth_tenants(
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> TenantListResponse:
    repo = AgentRepository(db)
    service = AuthService(repo)
    items = service.list_user_tenants(auth_ctx.user_id)
    return TenantListResponse(
        current_tenant_id=auth_ctx.tenant_id,
        tenants=[
            AuthTenantInfo(
                tenant_id=t.tenant_id,
                tenant_name=t.tenant_name,
                tenant_slug=t.tenant_slug,
                role=m.role,
            )
            for t, m in items
        ],
    )


@router.post("/auth/tenant/switch", response_model=TenantSwitchResponse)
def auth_switch_tenant(
    payload: TenantSwitchRequest,
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> TenantSwitchResponse:
    repo = AgentRepository(db)
    service = AuthService(repo)
    try:
        access_token, expires_at, tenant, membership = service.switch_tenant(
            user_id=auth_ctx.user_id,
            target_tenant_id=payload.tenant_id,
        )
    except AuthPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TenantSwitchResponse(
        access_token=access_token,
        expires_at=expires_at,
        tenant=AuthTenantInfo(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            tenant_slug=tenant.tenant_slug,
            role=membership.role,
        ),
    )


@router.post("/auth/tenant/invitations", response_model=TenantInviteResponse)
def create_tenant_invitation(
    payload: TenantInviteRequest,
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> TenantInviteResponse:
    repo = AgentRepository(db)
    service = AuthService(repo)
    mailer = InvitationMailer()
    try:
        invitation = service.invite_member(
            inviter_user_id=auth_ctx.user_id,
            inviter_tenant_id=auth_ctx.tenant_id,
            invitee_email=payload.invitee_email,
            role=payload.role,
            expires_in_hours=payload.expires_in_hours,
        )
    except AuthPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tenant = repo.get_tenant_by_id(auth_ctx.tenant_id)
    membership = repo.get_tenant_membership(auth_ctx.tenant_id, auth_ctx.user_id)
    inviter = repo.get_user_by_id(auth_ctx.user_id)
    if not tenant or not membership:
        raise HTTPException(status_code=404, detail="tenant or membership not found")

    invite_link = mailer.build_invite_link(invitation.invite_code)
    mail_result = mailer.send_invitation_email(
        tenant_name=tenant.tenant_name,
        inviter_email=(inviter.email if inviter else None),
        invitee_email=invitation.invitee_email,
        invite_code=invitation.invite_code,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )
    if settings.invite_email_required and not mail_result.sent:
        raise HTTPException(
            status_code=502,
            detail=f"invitation created but email delivery failed: {mail_result.error or 'unknown error'}",
        )

    return TenantInviteResponse(
        invitation=_to_tenant_invitation_item(invitation),
        tenant=AuthTenantInfo(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            tenant_slug=tenant.tenant_slug,
            role=membership.role,
        ),
        invite_link=invite_link,
        email_sent=mail_result.sent,
        email_provider=mail_result.provider,
        email_message_id=mail_result.message_id,
        email_error=mail_result.error,
    )


@router.get("/auth/tenant/invitations", response_model=TenantInvitationListResponse)
def list_tenant_invitations(
    status: str | None = None,
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> TenantInvitationListResponse:
    repo = AgentRepository(db)
    membership = repo.get_tenant_membership(auth_ctx.tenant_id, auth_ctx.user_id)
    if not membership or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="only owner/admin can view invitations")
    invitations = repo.list_tenant_invitations(auth_ctx.tenant_id, status=status, limit=100)
    return TenantInvitationListResponse(invitations=[_to_tenant_invitation_item(i) for i in invitations])


@router.post("/auth/tenant/invitations/accept", response_model=TenantInvitationAcceptResponse)
def accept_tenant_invitation(
    payload: TenantInvitationAcceptRequest,
    auth_ctx: AuthContext = Depends(get_auth_context_required),
    db: Session = Depends(get_db),
) -> TenantInvitationAcceptResponse:
    service = AuthService(AgentRepository(db))
    try:
        access_token, expires_at, tenant, membership, _ = service.accept_invitation(
            user_id=auth_ctx.user_id,
            invite_code=payload.invite_code,
        )
    except AuthPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TenantInvitationAcceptResponse(
        access_token=access_token,
        expires_at=expires_at,
        tenant=AuthTenantInfo(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.tenant_name,
            tenant_slug=tenant.tenant_slug,
            role=membership.role,
        ),
    )


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    payload: CreateSessionRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> CreateSessionResponse:
    repo = AgentRepository(db)
    entity = repo.create_session(
        influencer_name=payload.influencer_name,
        category=payload.category,
        tenant_id=(auth_ctx.tenant_id if auth_ctx else None),
        owner_user_id=(auth_ctx.user_id if auth_ctx else None),
    )
    return CreateSessionResponse(session_id=entity.session_id, status=entity.status)


@router.post("/generate", response_model=GenerateResponse)
def generate(
    payload: GenerateRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    repo = AgentRepository(db)
    context_repo = ContextRepository(db)
    memory_manager = MemoryManager(context_repo)
    multimodal_preprocessor = MultimodalPreprocessor()
    session = repo.get_session_scoped(
        payload.session_id,
        tenant_id=(auth_ctx.tenant_id if auth_ctx else None),
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    preprocess_result = multimodal_preprocessor.preprocess(
        query=payload.query,
        attachments=[x.model_dump() for x in payload.attachments],
    )
    effective_query = preprocess_result.enriched_query

    memory_manager.record(
        session_id=session.session_id,
        role="user",
        content=effective_query,
        tags="generate_query",
        importance_score=3,
    )
    if preprocess_result.attachment_count > 0:
        memory_manager.record(
            session_id=session.session_id,
            role="system",
            content=(
                "Multimodal preprocessing summary: "
                f"attachments={preprocess_result.attachment_count}, "
                f"processed={preprocess_result.processed_count}, "
                f"extracted={preprocess_result.extracted_count}, "
                f"failed={preprocess_result.failed_count}, "
                f"notes={'; '.join(preprocess_result.notes) or 'none'}"
            ),
            tags="multimodal_preprocess",
            importance_score=2,
        )

    analysis = RequirementAnalyzer().analyze(effective_query)
    requirement = repo.create_requirement(
        session_id=session.session_id,
        query_text=effective_query,
        priority=analysis.priority,
        estimated_points=analysis.estimated_points,
    )
    scheduler.enqueue(requirement.requirement_id, analysis.priority, analysis.estimated_points)
    _ = scheduler.next_requirement()
    orchestrator = AgentOrchestrator(
        repo=repo,
        rag_service=RAGService(
            db=db,
            workspace=settings.run_workspace,
            repo_name=settings.context_repo_name,
            branch_name=settings.context_branch_name,
        ),
        test_service=TestService(),
        memory_manager=memory_manager,
    )
    answer, traces, run_id, todo_states = orchestrator.run(
        session,
        requirement,
        effective_query,
        current_file=payload.current_file,
    )
    memory_manager.record(
        session_id=session.session_id,
        role="assistant",
        content=answer,
        tags="generate_answer",
        importance_score=2,
    )

    return GenerateResponse(
        session_id=session.session_id,
        requirement_id=requirement.requirement_id,
        priority=requirement.priority,
        estimated_points=requirement.estimated_points,
        answer=answer,
        traces=[
            TaskTrace(role=t.role, instruction=t.instruction, output=t.output, status=t.status)
            for t in traces
        ],
        agent_run_id=run_id,
        todo_states=[
            TodoState(
                todo_id=t.todo_id,
                role=t.role,
                title=t.title,
                status=t.status,
                success_criteria=t.success_criteria,
                attempt_count=t.attempt_count,
            )
            for t in todo_states
        ],
        multimodal_summary=MultimodalSummary(
            attachment_count=preprocess_result.attachment_count,
            processed_count=preprocess_result.processed_count,
            extracted_count=preprocess_result.extracted_count,
            failed_count=preprocess_result.failed_count,
            notes=preprocess_result.notes,
        ),
    )


@router.post("/context/index", response_model=ContextIndexResponse)
def context_index(payload: ContextIndexRequest, db: Session = Depends(get_db)) -> ContextIndexResponse:
    context_repo = ContextRepository(db)
    indexer = ContextIndexer(context_repo)
    try:
        stats = indexer.index_workspace(
            workspace=payload.workspace,
            repo_name=payload.repo_name,
            branch_name=payload.branch_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ContextIndexResponse(
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
        indexed_files=stats.files,
        indexed_symbols=stats.symbols,
        indexed_dependencies=stats.dependencies,
        indexed_chunks=stats.chunks,
    )


@router.post("/context/query", response_model=ContextQueryResponse)
def context_query(
    payload: ContextQueryRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> ContextQueryResponse:
    repo = AgentRepository(db)
    if not repo.get_session_scoped(payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)):
        raise HTTPException(status_code=404, detail="session not found")
    retriever = ContextRetriever(ContextRepository(db))
    context_text = retriever.retrieve(
        query=payload.query,
        session_id=payload.session_id,
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
    )
    return ContextQueryResponse(context=context_text)


@router.post("/project/init", response_model=ProjectInitResponse)
def project_init(payload: ProjectInitRequest, db: Session = Depends(get_db)) -> ProjectInitResponse:
    manager = ProjectContextManager(ContextRepository(db))
    try:
        stats = manager.initialize_project(
            workspace=payload.workspace,
            repo_name=payload.repo_name,
            branch_name=payload.branch_name,
            module_path=payload.module_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProjectInitResponse(
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
        scoped_workspace=stats.scoped_workspace,
        indexed_files=stats.indexed_files,
        graph_nodes=stats.graph_nodes,
        graph_edges=stats.graph_edges,
        vectors=stats.vectors,
    )


@router.post("/project/context", response_model=ProjectContextResponse)
def project_context(payload: ProjectContextRequest, db: Session = Depends(get_db)) -> ProjectContextResponse:
    manager = ProjectContextManager(ContextRepository(db))
    result = manager.retrieve_project_context(
        query=payload.query,
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
        current_file=payload.current_file,
        max_items=payload.max_items,
    )
    return ProjectContextResponse(context=result.context, selected_files=result.selected_files)


@router.post("/project/callers", response_model=ProjectCallersResponse)
def project_callers(payload: ProjectCallersRequest, db: Session = Depends(get_db)) -> ProjectCallersResponse:
    manager = ProjectContextManager(ContextRepository(db))
    files = manager.caller_files_of_function(
        repo_name=payload.repo_name,
        branch_name=payload.branch_name,
        function_name=payload.function_name,
    )
    return ProjectCallersResponse(function_name=payload.function_name, caller_files=files)


@router.post("/memory/optimize", response_model=MemoryOptimizeResponse)
def memory_optimize(
    payload: MemoryOptimizeRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> MemoryOptimizeResponse:
    repo = AgentRepository(db)
    if not repo.get_session_scoped(payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)):
        raise HTTPException(status_code=404, detail="session not found")

    manager = MemoryManager(ContextRepository(db))
    result = manager.optimize_session(payload.session_id)
    return MemoryOptimizeResponse(
        session_id=payload.session_id,
        before_count=result.before_count,
        after_count=result.after_count,
        compacted_count=result.compacted_count,
        summary_created=result.summary_created,
    )


@router.get("/agent/runs/{run_id}", response_model=AgentRunDetailResponse)
def get_agent_run(
    run_id: str,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> AgentRunDetailResponse:
    repo = AgentRepository(db)
    run = repo.get_agent_run_scoped(run_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    todos = repo.list_agent_todos(run_id)
    evaluations = repo.list_task_evaluations(run_id)
    approvals = repo.list_approval_events(run_id)
    return AgentRunDetailResponse(
        run_id=run.run_id,
        session_id=run.session_id,
        requirement_id=run.requirement_id,
        original_query=run.original_query,
        interpreted_query=run.interpreted_query,
        persona_name=run.persona_name,
        complexity=run.complexity,
        status=run.status,
        max_steps=run.max_steps,
        current_step=run.current_step,
        created_at=run.created_at,
        finished_at=run.finished_at,
        todos=[
            AgentRunTodoItem(
                todo_id=t.todo_id,
                parent_todo_id=t.parent_todo_id,
                role=t.role,
                title=t.title,
                instruction=t.instruction,
                success_criteria=t.success_criteria,
                depends_on=_parse_depends_on(t.depends_on_json),
                status=t.status,
                attempt_count=t.attempt_count,
                max_attempts=t.max_attempts,
                output_text=t.output_text,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in todos
        ],
        evaluations=[
            TaskEvaluationItem(
                evaluation_id=e.evaluation_id,
                todo_id=e.todo_id,
                evaluator=e.evaluator,
                passed=e.passed,
                score=e.score,
                reason=e.reason,
                next_action=e.next_action,
                created_at=e.created_at,
            )
            for e in evaluations
        ],
        approval_events=[
            ApprovalEventItem(
                event_id=a.event_id,
                todo_id=a.todo_id,
                gate_type=a.gate_type,
                decision=a.decision,
                operator=a.operator,
                comment=a.comment,
                created_at=a.created_at,
            )
            for a in approvals
        ],
    )


@router.post("/agent/runs/{run_id}/approve", response_model=AgentRunApproveResponse)
def approve_agent_run(
    run_id: str,
    payload: AgentRunApproveRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> AgentRunApproveResponse:
    repo = AgentRepository(db)
    run = repo.get_agent_run_scoped(run_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None))
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    todos = repo.list_agent_todos(run_id)
    waiting_todos = [t for t in todos if t.status == "waiting_approval"]
    if payload.todo_id is not None:
        waiting_todos = [t for t in waiting_todos if t.todo_id == payload.todo_id]
    if not waiting_todos:
        raise HTTPException(status_code=409, detail="no waiting approval todo found")

    updated_ids: list[int] = []
    for todo in waiting_todos:
        if payload.decision == "approved":
            repo.update_agent_todo(
                todo,
                status="pending",
                output_text=(todo.output_text or "") + f"\n\nApproved by {payload.operator}.",
            )
        else:
            repo.update_agent_todo(
                todo,
                status="failed",
                output_text=(todo.output_text or "") + f"\n\nRejected by {payload.operator}.",
            )
        repo.create_approval_event(
            run_id=run_id,
            todo_id=todo.todo_id,
            gate_type=payload.gate_type,
            decision=payload.decision,
            operator=payload.operator,
            comment=payload.comment,
        )
        updated_ids.append(todo.todo_id)

    refreshed = repo.list_agent_todos(run_id)
    if payload.decision == "rejected":
        run_status = "failed"
    elif any(t.status == "waiting_approval" for t in refreshed):
        run_status = "waiting_approval"
    elif any(t.status == "failed" for t in refreshed):
        run_status = "failed"
    else:
        run_status = "running"
    repo.set_agent_run_status(run, run_status, finished=run_status in {"failed", "completed", "cancelled"})

    return AgentRunApproveResponse(
        run_id=run_id,
        decision=payload.decision,
        updated_todo_ids=updated_ids,
        run_status=run_status,
    )


def _parse_depends_on(depends_on_json: str | None) -> list[int]:
    if not depends_on_json:
        return []
    try:
        data = json.loads(depends_on_json)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    values: list[int] = []
    for item in data:
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def _to_tenant_invitation_item(entity) -> TenantInvitationItem:
    return TenantInvitationItem(
        invitation_id=entity.invitation_id,
        invite_code=entity.invite_code,
        invitee_email=entity.invitee_email,
        role=entity.role,
        status=entity.status,
        tenant_id=entity.tenant_id,
        invited_by_user_id=entity.invited_by_user_id,
        accepted_by_user_id=entity.accepted_by_user_id,
        expires_at=entity.expires_at,
        created_at=entity.created_at,
        accepted_at=entity.accepted_at,
    )


# ---------------------------------------------------------------------------
# Streaming agent endpoint (SSE)
# ---------------------------------------------------------------------------

@router.post("/agent/stream")
async def agent_stream(
    payload: AgentStreamRequest,
    auth_ctx: AuthContext | None = Depends(get_auth_context_optional),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """LLM-driven agent loop with Server-Sent Events streaming."""

    from app.services.agent_runner import AgentRunner
    from app.services.llm_service import LLMService
    from app.tools import create_default_registry

    llm = LLMService()
    registry = create_default_registry()
    runner = AgentRunner(llm=llm, tool_registry=registry)

    workspace = payload.workspace or settings.sandbox_workspace_root

    # Tenant-scoped session access
    repo = AgentRepository(db)
    if not repo.get_session_scoped(payload.session_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None)):
        raise HTTPException(status_code=404, detail="session not found")

    # Optionally gather RAG context using the sync DB session
    rag_context: str | None = None
    try:
        rag = RAGService(
            db=db,
            workspace=workspace,
            repo_name=settings.context_repo_name,
            branch_name=settings.context_branch_name,
        )
        rag_context = rag.retrieve_context(
            query=payload.query,
            session_id=payload.session_id,
            current_file=payload.current_file,
        )
    except Exception:
        logger.debug("RAG context retrieval failed, proceeding without it", exc_info=True)

    async def event_generator():
        from app.services.agent_runner import StreamEvent

        try:
            async for event in runner.run_stream(
                session_id=payload.session_id,
                query=payload.query,
                workspace=workspace,
                current_file=payload.current_file,
                rag_context=rag_context,
            ):
                yield f"data: {event.to_json()}\n\n"
        except Exception as exc:
            logger.exception("agent stream error")
            err = StreamEvent("error", {"message": str(exc)})
            yield f"data: {err.to_json()}\n\n"
            done = StreamEvent("done", {"run_id": "unknown", "status": "failed"})
            yield f"data: {done.to_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# WebSocket for approval flow during agent runs
# ---------------------------------------------------------------------------

@router.websocket("/agent/ws/{run_id}")
async def agent_ws(websocket: WebSocket, run_id: str):
    """WebSocket for real-time approval flow during an agent run."""
    auth_ctx: AuthContext | None = None
    token = websocket.query_params.get("access_token")
    if token:
        db = next(get_db())
        auth_ctx = AuthService(AgentRepository(db)).get_auth_context(token)
        db.close()
        if not auth_ctx:
            await websocket.close(code=4401, reason="invalid token")
            return
    elif settings.auth_required:
        await websocket.close(code=4401, reason="missing token")
        return

    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type in ("approve", "reject"):
                # Forward to the approval endpoint logic
                try:
                    db = next(get_db())
                    repo = AgentRepository(db)
                    run = repo.get_agent_run_scoped(run_id, tenant_id=(auth_ctx.tenant_id if auth_ctx else None))
                    if not run:
                        await websocket.send_json({"type": "error", "message": "run not found"})
                        db.close()
                        continue

                    todos = repo.list_agent_todos(run_id)
                    waiting = [t for t in todos if t.status == "waiting_approval"]
                    todo_id = data.get("todo_id")
                    if todo_id is not None:
                        waiting = [t for t in waiting if t.todo_id == todo_id]

                    decision = "approved" if msg_type == "approve" else "rejected"
                    operator = data.get("operator", "web_user")
                    for todo in waiting:
                        if decision == "approved":
                            repo.update_agent_todo(todo, status="pending")
                        else:
                            repo.update_agent_todo(todo, status="failed")
                        repo.create_approval_event(
                            run_id=run_id,
                            todo_id=todo.todo_id,
                            gate_type="ws_gate",
                            decision=decision,
                            operator=operator,
                            comment=data.get("reason"),
                        )

                    await websocket.send_json({
                        "type": "approval_ack",
                        "decision": decision,
                        "run_id": run_id,
                    })
                    db.close()
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})
            else:
                await websocket.send_json({"type": "error", "message": f"unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for run %s", run_id)
