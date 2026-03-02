from __future__ import annotations

import base64
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.models import TenantEntity, TenantInvitationEntity, TenantMemberEntity, UserEntity
from app.repositories.agent_repo import AgentRepository


_SLUG_SAFE_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass
class GoogleProfile:
    sub: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None
    raw_json: str


@dataclass
class AuthContext:
    user_id: str
    tenant_id: str
    role: str
    email: str | None = None


class GoogleTokenVerificationError(ValueError):
    pass


class AuthPermissionError(PermissionError):
    pass


class AuthValidationError(ValueError):
    pass


class AuthConflictError(ValueError):
    pass


class AuthService:
    TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

    def __init__(self, repo: AgentRepository):
        self.repo = repo

    def verify_google_id_token(self, id_token: str) -> GoogleProfile:
        mode = (settings.auth_google_verify_mode or "tokeninfo").strip().lower()
        if mode == "dev_unverified":
            return self._decode_unverified_id_token(id_token)
        return self._verify_via_tokeninfo(id_token)

    def get_auth_context(self, access_token: str) -> AuthContext | None:
        entity = self.repo.get_auth_token(access_token)
        if not entity or entity.revoked:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if entity.expires_at <= now:
            return None
        return AuthContext(
            user_id=entity.user_id,
            tenant_id=entity.tenant_id,
            role=entity.role,
            email=(entity.user.email if entity.user else None),
        )

    def login_with_google(
        self,
        id_token: str,
        tenant_id: str | None = None,
        tenant_slug: str | None = None,
        tenant_name: str | None = None,
    ) -> tuple[str, datetime, UserEntity, TenantEntity, TenantMemberEntity]:
        profile = self.verify_google_id_token(id_token)
        user, _ = self._upsert_user_and_identity(profile)
        tenant, membership = self._resolve_tenant_for_user(
            user=user,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            tenant_name=tenant_name,
        )

        token_text = self._generate_access_token()
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.auth_access_token_ttl_hours)
        self.repo.create_auth_token(
            access_token=token_text,
            user_id=user.user_id,
            tenant_id=tenant.tenant_id,
            role=membership.role,
            expires_at=expires_at,
        )
        return token_text, expires_at, user, tenant, membership

    def list_user_tenants(self, user_id: str) -> list[tuple[TenantEntity, TenantMemberEntity]]:
        memberships = self.repo.list_user_tenant_memberships(user_id)
        result: list[tuple[TenantEntity, TenantMemberEntity]] = []
        for membership in memberships:
            tenant = self.repo.get_tenant_by_id(membership.tenant_id)
            if not tenant:
                continue
            result.append((tenant, membership))
        return result

    def switch_tenant(
        self,
        *,
        user_id: str,
        target_tenant_id: str,
    ) -> tuple[str, datetime, TenantEntity, TenantMemberEntity]:
        tenant = self.repo.get_tenant_by_id(target_tenant_id)
        if not tenant:
            raise AuthValidationError("target tenant not found")
        membership = self.repo.get_tenant_membership(target_tenant_id, user_id)
        if not membership:
            raise AuthPermissionError("user is not a member of target tenant")

        token_text = self._generate_access_token()
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=settings.auth_access_token_ttl_hours)
        self.repo.create_auth_token(
            access_token=token_text,
            user_id=user_id,
            tenant_id=tenant.tenant_id,
            role=membership.role,
            expires_at=expires_at,
        )
        return token_text, expires_at, tenant, membership

    def invite_member(
        self,
        *,
        inviter_user_id: str,
        inviter_tenant_id: str,
        invitee_email: str,
        role: str = "member",
        expires_in_hours: int = 72,
    ) -> TenantInvitationEntity:
        inviter_membership = self.repo.get_tenant_membership(inviter_tenant_id, inviter_user_id)
        if not inviter_membership:
            raise AuthPermissionError("inviter is not a member of tenant")
        if inviter_membership.role not in {"owner", "admin"}:
            raise AuthPermissionError("only owner/admin can invite members")

        normalized_email = invitee_email.strip().lower()
        if not normalized_email:
            raise AuthValidationError("invitee_email is required")
        normalized_role = role.strip().lower()
        if normalized_role not in {"member", "admin"}:
            raise AuthValidationError("invalid role, expected member/admin")
        normalized_expires = max(1, min(int(expires_in_hours), 24 * 30))

        existing_user = self.repo.get_user_by_email(normalized_email)
        if existing_user:
            existing_membership = self.repo.get_tenant_membership(inviter_tenant_id, existing_user.user_id)
            if existing_membership:
                raise AuthConflictError("invitee is already a tenant member")

        invite_code = self._generate_invite_code()
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=normalized_expires)
        pending = self.repo.get_pending_tenant_invitation(inviter_tenant_id, normalized_email)
        if pending:
            return self.repo.update_tenant_invitation(
                pending,
                invite_code=invite_code,
                role=normalized_role,
                expires_at=expires_at,
            )

        return self.repo.create_tenant_invitation(
            tenant_id=inviter_tenant_id,
            invite_code=invite_code,
            invitee_email=normalized_email,
            role=normalized_role,
            invited_by_user_id=inviter_user_id,
            expires_at=expires_at,
        )

    def accept_invitation(
        self,
        *,
        user_id: str,
        invite_code: str,
    ) -> tuple[str, datetime, TenantEntity, TenantMemberEntity, TenantInvitationEntity]:
        invitation = self.repo.get_tenant_invitation_by_code(invite_code.strip())
        if not invitation:
            raise AuthValidationError("invitation not found")
        if invitation.status != "pending":
            raise AuthConflictError("invitation is not pending")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if invitation.expires_at <= now:
            self.repo.update_tenant_invitation(invitation, status="expired")
            raise AuthConflictError("invitation has expired")

        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise AuthValidationError("user not found")
        if user.email.lower() != invitation.invitee_email.lower():
            raise AuthPermissionError("invitation email does not match current user")

        membership = self.repo.get_tenant_membership(invitation.tenant_id, user_id)
        if not membership:
            membership = self.repo.create_tenant_membership(
                tenant_id=invitation.tenant_id,
                user_id=user_id,
                role=invitation.role,
            )

        self.repo.update_tenant_invitation(
            invitation,
            status="accepted",
            accepted_by_user_id=user_id,
            accepted_at=now,
        )

        tenant = self.repo.get_tenant_by_id(invitation.tenant_id)
        if not tenant:
            raise AuthValidationError("tenant not found")

        token_text = self._generate_access_token()
        expires_at = now + timedelta(hours=settings.auth_access_token_ttl_hours)
        self.repo.create_auth_token(
            access_token=token_text,
            user_id=user.user_id,
            tenant_id=tenant.tenant_id,
            role=membership.role,
            expires_at=expires_at,
        )
        return token_text, expires_at, tenant, membership, invitation

    def _upsert_user_and_identity(self, profile: GoogleProfile) -> tuple[UserEntity, bool]:
        identity = self.repo.get_google_identity_by_sub(profile.sub)
        if identity:
            user = self.repo.get_user_by_id(identity.user_id)
            if not user:
                user = self.repo.create_user(profile.email, display_name=profile.name, avatar_url=profile.picture)
            else:
                self.repo.update_user_profile(user, display_name=profile.name, avatar_url=profile.picture)
            self.repo.update_google_identity(
                identity,
                email=profile.email,
                email_verified=profile.email_verified,
                raw_profile_json=profile.raw_json,
            )
            return user, False

        user = self.repo.get_user_by_email(profile.email)
        if not user:
            user = self.repo.create_user(profile.email, display_name=profile.name, avatar_url=profile.picture)
        else:
            self.repo.update_user_profile(user, display_name=profile.name, avatar_url=profile.picture)
        self.repo.create_google_identity(
            user_id=user.user_id,
            google_sub=profile.sub,
            email=profile.email,
            email_verified=profile.email_verified,
            raw_profile_json=profile.raw_json,
        )
        return user, True

    def _resolve_tenant_for_user(
        self,
        user: UserEntity,
        tenant_id: str | None,
        tenant_slug: str | None,
        tenant_name: str | None,
    ) -> tuple[TenantEntity, TenantMemberEntity]:
        target_tenant: TenantEntity | None = None
        if tenant_id:
            target_tenant = self.repo.get_tenant_by_id(tenant_id)
        elif tenant_slug:
            target_tenant = self.repo.get_tenant_by_slug(tenant_slug)

        if target_tenant:
            membership = self.repo.get_tenant_membership(target_tenant.tenant_id, user.user_id)
            if not membership:
                raise GoogleTokenVerificationError("user is not a member of target tenant")
            return target_tenant, membership

        memberships = self.repo.list_user_tenant_memberships(user.user_id)
        if memberships:
            first = memberships[0]
            tenant = self.repo.get_tenant_by_id(first.tenant_id)
            if tenant:
                return tenant, first

        base_name = (tenant_name or user.display_name or user.email.split("@")[0]).strip()
        if not base_name:
            base_name = "Personal Tenant"
        slug_seed = f"{settings.auth_default_tenant_prefix}-{base_name}"
        slug = self._make_unique_tenant_slug(slug_seed)
        tenant = self.repo.create_tenant(tenant_name=f"{base_name} Workspace", tenant_slug=slug)
        membership = self.repo.create_tenant_membership(tenant.tenant_id, user.user_id, role="owner")
        return tenant, membership

    def _make_unique_tenant_slug(self, raw_text: str) -> str:
        max_len = 120
        base_slug = _SLUG_SAFE_PATTERN.sub("-", raw_text.lower()).strip("-")
        if not base_slug:
            base_slug = "tenant"
        base_slug = base_slug[:max_len]
        candidate = base_slug
        suffix = 1
        while self.repo.get_tenant_by_slug(candidate):
            suffix += 1
            suffix_text = f"-{suffix}"
            keep_len = max_len - len(suffix_text)
            candidate = f"{base_slug[:keep_len]}{suffix_text}"
        return candidate

    def _verify_via_tokeninfo(self, id_token: str) -> GoogleProfile:
        try:
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(self.TOKENINFO_URL, params={"id_token": id_token})
        except Exception as exc:
            raise GoogleTokenVerificationError(f"google token verification failed: {exc}") from exc

        if resp.status_code != 200:
            raise GoogleTokenVerificationError("invalid google id_token")
        data = resp.json()
        aud = str(data.get("aud") or "")
        allowed = self._allowed_google_client_ids()
        if allowed and aud not in allowed:
            raise GoogleTokenVerificationError("google token audience mismatch")
        email = str(data.get("email") or "").lower().strip()
        sub = str(data.get("sub") or "").strip()
        if not email or not sub:
            raise GoogleTokenVerificationError("google token missing required fields")
        email_verified = str(data.get("email_verified") or "").lower() in {"true", "1"}
        return GoogleProfile(
            sub=sub,
            email=email,
            email_verified=email_verified,
            name=(str(data.get("name")) if data.get("name") else None),
            picture=(str(data.get("picture")) if data.get("picture") else None),
            raw_json=json.dumps(data, ensure_ascii=False),
        )

    def _decode_unverified_id_token(self, id_token: str) -> GoogleProfile:
        parts = id_token.split(".")
        if len(parts) < 2:
            raise GoogleTokenVerificationError("invalid jwt format")
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        try:
            payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
            data = json.loads(payload_json)
        except Exception as exc:
            raise GoogleTokenVerificationError(f"invalid jwt payload: {exc}") from exc

        email = str(data.get("email") or "").lower().strip()
        sub = str(data.get("sub") or "").strip()
        if not email or not sub:
            raise GoogleTokenVerificationError("jwt payload missing email or sub")
        raw_verified = str(data.get("email_verified") or "").lower()
        email_verified = raw_verified in {"true", "1"}
        return GoogleProfile(
            sub=sub,
            email=email,
            email_verified=email_verified,
            name=(str(data.get("name")) if data.get("name") else None),
            picture=(str(data.get("picture")) if data.get("picture") else None),
            raw_json=json.dumps(data, ensure_ascii=False),
        )

    def _allowed_google_client_ids(self) -> set[str]:
        raw = settings.auth_google_client_ids or ""
        return {x.strip() for x in raw.split(",") if x.strip()}

    def _generate_access_token(self) -> str:
        return "ca_" + secrets.token_urlsafe(32)

    def _generate_invite_code(self) -> str:
        return "inv_" + secrets.token_urlsafe(24)
