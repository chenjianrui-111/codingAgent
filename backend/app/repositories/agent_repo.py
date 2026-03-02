import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ApprovalEventEntity,
    AgentRunEntity,
    AgentTodoEntity,
    AuthTokenEntity,
    GoogleIdentityEntity,
    RequirementEntity,
    SessionEntity,
    TaskEntity,
    TaskEvaluationEntity,
    TenantEntity,
    TenantInvitationEntity,
    TenantMemberEntity,
    ToolCallEntity,
    UserEntity,
)


class AgentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_session(
        self,
        influencer_name: str,
        category: str,
        tenant_id: str | None = None,
        owner_user_id: str | None = None,
    ) -> SessionEntity:
        entity = SessionEntity(
            influencer_name=influencer_name,
            category=category,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_session(self, session_id: str) -> SessionEntity | None:
        return self.db.get(SessionEntity, session_id)

    def get_session_scoped(self, session_id: str, tenant_id: str | None = None) -> SessionEntity | None:
        session = self.db.get(SessionEntity, session_id)
        if not session:
            return None
        # Anonymous callers can only access legacy sessions without tenant binding.
        if tenant_id is None:
            if session.tenant_id is not None:
                return None
            return session
        if session.tenant_id != tenant_id:
            return None
        return session

    def create_requirement(
        self,
        session_id: str,
        query_text: str,
        priority: str = "medium",
        estimated_points: int = 1,
    ) -> RequirementEntity:
        req = RequirementEntity(
            session_id=session_id,
            query_text=query_text,
            priority=priority,
            estimated_points=estimated_points,
        )
        self.db.add(req)
        self.db.commit()
        self.db.refresh(req)
        return req

    def create_task(self, requirement_id: int, role: str, instruction: str) -> TaskEntity:
        task = TaskEntity(requirement_id=requirement_id, role=role, instruction=instruction)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def complete_task(self, task: TaskEntity, output_text: str) -> TaskEntity:
        task.output_text = output_text
        task.status = "completed"
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def list_requirement_tasks(self, requirement_id: int) -> list[TaskEntity]:
        stmt = select(TaskEntity).where(TaskEntity.requirement_id == requirement_id).order_by(TaskEntity.task_id.asc())
        return list(self.db.scalars(stmt).all())

    def create_tool_call(
        self,
        session_id: str,
        tool_name: str,
        request_text: str,
        response_text: str,
        latency_ms: int,
    ) -> ToolCallEntity:
        call = ToolCallEntity(
            session_id=session_id,
            tool_name=tool_name,
            request_text=request_text,
            response_text=response_text,
            latency_ms=latency_ms,
        )
        self.db.add(call)
        self.db.commit()
        self.db.refresh(call)
        return call

    def create_agent_run(
        self,
        session_id: str,
        requirement_id: int,
        original_query: str,
        interpreted_query: str,
        persona_name: str,
        complexity: str,
        max_steps: int,
    ) -> AgentRunEntity:
        run = AgentRunEntity(
            session_id=session_id,
            requirement_id=requirement_id,
            original_query=original_query,
            interpreted_query=interpreted_query,
            persona_name=persona_name,
            complexity=complexity,
            max_steps=max_steps,
            status="running",
            current_step=0,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def update_agent_run_progress(self, run: AgentRunEntity, current_step: int) -> AgentRunEntity:
        run.current_step = current_step
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def complete_agent_run(self, run: AgentRunEntity, status: str) -> AgentRunEntity:
        run.status = status
        run.finished_at = datetime.utcnow()
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def set_agent_run_status(self, run: AgentRunEntity, status: str, finished: bool = False) -> AgentRunEntity:
        run.status = status
        run.finished_at = datetime.utcnow() if finished else None
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def create_agent_todo(
        self,
        run_id: str,
        role: str,
        title: str,
        instruction: str,
        success_criteria: str,
        depends_on: list[int] | None = None,
        parent_todo_id: int | None = None,
        max_attempts: int = 2,
    ) -> AgentTodoEntity:
        todo = AgentTodoEntity(
            run_id=run_id,
            role=role,
            title=title,
            instruction=instruction,
            success_criteria=success_criteria,
            depends_on_json=json.dumps(depends_on or []),
            parent_todo_id=parent_todo_id,
            max_attempts=max(1, max_attempts),
        )
        self.db.add(todo)
        self.db.commit()
        self.db.refresh(todo)
        return todo

    def list_agent_todos(self, run_id: str) -> list[AgentTodoEntity]:
        stmt = select(AgentTodoEntity).where(AgentTodoEntity.run_id == run_id).order_by(AgentTodoEntity.todo_id.asc())
        return list(self.db.scalars(stmt).all())

    def update_agent_todo(
        self,
        todo: AgentTodoEntity,
        *,
        status: str | None = None,
        output_text: str | None = None,
        attempt_count: int | None = None,
        instruction: str | None = None,
        depends_on: list[int] | None = None,
    ) -> AgentTodoEntity:
        if status is not None:
            todo.status = status
        if output_text is not None:
            todo.output_text = output_text
        if attempt_count is not None:
            todo.attempt_count = max(0, attempt_count)
        if instruction is not None:
            todo.instruction = instruction
        if depends_on is not None:
            todo.depends_on_json = json.dumps(depends_on)
        self.db.add(todo)
        self.db.commit()
        self.db.refresh(todo)
        return todo

    def create_task_evaluation(
        self,
        run_id: str,
        todo_id: int,
        evaluator: str,
        passed: bool,
        score: int,
        reason: str,
        next_action: str | None = None,
    ) -> TaskEvaluationEntity:
        entity = TaskEvaluationEntity(
            run_id=run_id,
            todo_id=todo_id,
            evaluator=evaluator,
            passed=passed,
            score=max(0, min(100, score)),
            reason=reason,
            next_action=next_action,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_agent_run(self, run_id: str) -> AgentRunEntity | None:
        return self.db.get(AgentRunEntity, run_id)

    def get_agent_run_scoped(self, run_id: str, tenant_id: str | None = None) -> AgentRunEntity | None:
        run = self.db.get(AgentRunEntity, run_id)
        if not run:
            return None
        session = self.db.get(SessionEntity, run.session_id)
        if tenant_id is None:
            if not session or session.tenant_id is not None:
                return None
            return run
        if not session or session.tenant_id != tenant_id:
            return None
        return run

    def list_task_evaluations(self, run_id: str) -> list[TaskEvaluationEntity]:
        stmt = (
            select(TaskEvaluationEntity)
            .where(TaskEvaluationEntity.run_id == run_id)
            .order_by(TaskEvaluationEntity.evaluation_id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def create_approval_event(
        self,
        run_id: str,
        gate_type: str,
        decision: str,
        operator: str,
        comment: str | None = None,
        todo_id: int | None = None,
    ) -> ApprovalEventEntity:
        entity = ApprovalEventEntity(
            run_id=run_id,
            todo_id=todo_id,
            gate_type=gate_type,
            decision=decision,
            operator=operator,
            comment=comment,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list_approval_events(self, run_id: str) -> list[ApprovalEventEntity]:
        stmt = (
            select(ApprovalEventEntity)
            .where(ApprovalEventEntity.run_id == run_id)
            .order_by(ApprovalEventEntity.event_id.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_tenant_by_id(self, tenant_id: str) -> TenantEntity | None:
        return self.db.get(TenantEntity, tenant_id)

    def get_tenant_by_slug(self, tenant_slug: str) -> TenantEntity | None:
        stmt = select(TenantEntity).where(TenantEntity.tenant_slug == tenant_slug).limit(1)
        return self.db.scalars(stmt).first()

    def create_tenant(self, tenant_name: str, tenant_slug: str, status: str = "active") -> TenantEntity:
        entity = TenantEntity(tenant_name=tenant_name, tenant_slug=tenant_slug, status=status)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_user_by_email(self, email: str) -> UserEntity | None:
        stmt = select(UserEntity).where(UserEntity.email == email.lower()).limit(1)
        return self.db.scalars(stmt).first()

    def get_user_by_id(self, user_id: str) -> UserEntity | None:
        return self.db.get(UserEntity, user_id)

    def create_user(self, email: str, display_name: str | None = None, avatar_url: str | None = None) -> UserEntity:
        entity = UserEntity(email=email.lower(), display_name=display_name, avatar_url=avatar_url)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_user_profile(
        self,
        user: UserEntity,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> UserEntity:
        if display_name:
            user.display_name = display_name
        if avatar_url:
            user.avatar_url = avatar_url
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_google_identity_by_sub(self, google_sub: str) -> GoogleIdentityEntity | None:
        stmt = select(GoogleIdentityEntity).where(GoogleIdentityEntity.google_sub == google_sub).limit(1)
        return self.db.scalars(stmt).first()

    def create_google_identity(
        self,
        user_id: str,
        google_sub: str,
        email: str,
        email_verified: bool,
        raw_profile_json: str | None = None,
    ) -> GoogleIdentityEntity:
        entity = GoogleIdentityEntity(
            user_id=user_id,
            google_sub=google_sub,
            email=email.lower(),
            email_verified=email_verified,
            raw_profile_json=raw_profile_json,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_google_identity(
        self,
        identity: GoogleIdentityEntity,
        email: str,
        email_verified: bool,
        raw_profile_json: str | None = None,
    ) -> GoogleIdentityEntity:
        identity.email = email.lower()
        identity.email_verified = email_verified
        identity.raw_profile_json = raw_profile_json
        self.db.add(identity)
        self.db.commit()
        self.db.refresh(identity)
        return identity

    def get_tenant_membership(self, tenant_id: str, user_id: str) -> TenantMemberEntity | None:
        stmt = (
            select(TenantMemberEntity)
            .where(TenantMemberEntity.tenant_id == tenant_id, TenantMemberEntity.user_id == user_id)
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_user_tenant_memberships(self, user_id: str) -> list[TenantMemberEntity]:
        stmt = select(TenantMemberEntity).where(TenantMemberEntity.user_id == user_id).order_by(TenantMemberEntity.member_id.asc())
        return list(self.db.scalars(stmt).all())

    def create_tenant_membership(self, tenant_id: str, user_id: str, role: str = "member") -> TenantMemberEntity:
        entity = TenantMemberEntity(tenant_id=tenant_id, user_id=user_id, role=role, status="active")
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def create_tenant_invitation(
        self,
        tenant_id: str,
        invite_code: str,
        invitee_email: str,
        role: str,
        invited_by_user_id: str,
        expires_at: datetime,
    ) -> TenantInvitationEntity:
        entity = TenantInvitationEntity(
            tenant_id=tenant_id,
            invite_code=invite_code,
            invitee_email=invitee_email.lower(),
            role=role,
            status="pending",
            invited_by_user_id=invited_by_user_id,
            expires_at=expires_at,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_tenant_invitation_by_code(self, invite_code: str) -> TenantInvitationEntity | None:
        stmt = select(TenantInvitationEntity).where(TenantInvitationEntity.invite_code == invite_code).limit(1)
        return self.db.scalars(stmt).first()

    def get_pending_tenant_invitation(self, tenant_id: str, invitee_email: str) -> TenantInvitationEntity | None:
        stmt = (
            select(TenantInvitationEntity)
            .where(
                TenantInvitationEntity.tenant_id == tenant_id,
                TenantInvitationEntity.invitee_email == invitee_email.lower(),
                TenantInvitationEntity.status == "pending",
            )
            .order_by(TenantInvitationEntity.invitation_id.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_tenant_invitations(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[TenantInvitationEntity]:
        stmt = select(TenantInvitationEntity).where(TenantInvitationEntity.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(TenantInvitationEntity.status == status)
        stmt = stmt.order_by(TenantInvitationEntity.invitation_id.desc()).limit(max(1, limit))
        return list(self.db.scalars(stmt).all())

    def update_tenant_invitation(
        self,
        invitation: TenantInvitationEntity,
        *,
        invite_code: str | None = None,
        role: str | None = None,
        status: str | None = None,
        expires_at: datetime | None = None,
        accepted_by_user_id: str | None = None,
        accepted_at: datetime | None = None,
    ) -> TenantInvitationEntity:
        if invite_code is not None:
            invitation.invite_code = invite_code
        if role is not None:
            invitation.role = role
        if status is not None:
            invitation.status = status
        if expires_at is not None:
            invitation.expires_at = expires_at
        if accepted_by_user_id is not None:
            invitation.accepted_by_user_id = accepted_by_user_id
        if accepted_at is not None:
            invitation.accepted_at = accepted_at
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def create_auth_token(
        self,
        access_token: str,
        user_id: str,
        tenant_id: str,
        role: str,
        expires_at: datetime,
    ) -> AuthTokenEntity:
        entity = AuthTokenEntity(
            access_token=access_token,
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            expires_at=expires_at,
            revoked=False,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_auth_token(self, access_token: str) -> AuthTokenEntity | None:
        stmt = select(AuthTokenEntity).where(AuthTokenEntity.access_token == access_token).limit(1)
        return self.db.scalars(stmt).first()

    def revoke_auth_token(self, entity: AuthTokenEntity) -> AuthTokenEntity:
        entity.revoked = True
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity
