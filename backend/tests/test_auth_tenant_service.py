import base64
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db import Base
from app.repositories.agent_repo import AgentRepository
from app.services.auth_service import AuthPermissionError, AuthService


def _make_unverified_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def _new_repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    return AgentRepository(db), db


def test_google_login_creates_user_tenant_and_token():
    repo, db = _new_repo()
    service = AuthService(repo)

    old_mode = settings.auth_google_verify_mode
    settings.auth_google_verify_mode = "dev_unverified"
    try:
        token = _make_unverified_jwt(
            {
                "sub": "google-sub-1",
                "email": "demo@example.com",
                "email_verified": True,
                "name": "Demo User",
                "picture": "https://example.com/a.png",
            }
        )
        access_token, _, user, tenant, membership = service.login_with_google(token)
        assert access_token.startswith("ca_")
        assert user.email == "demo@example.com"
        assert tenant.tenant_slug
        assert membership.role == "owner"

        ctx = service.get_auth_context(access_token)
        assert ctx is not None
        assert ctx.user_id == user.user_id
        assert ctx.tenant_id == tenant.tenant_id
    finally:
        settings.auth_google_verify_mode = old_mode
        db.close()


def test_session_scope_by_tenant():
    repo, db = _new_repo()
    t1 = repo.create_tenant("T1", "t1")
    t2 = repo.create_tenant("T2", "t2")

    s = repo.create_session("u", "cat", tenant_id=t1.tenant_id)
    assert repo.get_session_scoped(s.session_id, tenant_id=t1.tenant_id) is not None
    assert repo.get_session_scoped(s.session_id, tenant_id=t2.tenant_id) is None
    assert repo.get_session_scoped(s.session_id, tenant_id=None) is None

    anon = repo.create_session("u2", "cat2")
    assert repo.get_session_scoped(anon.session_id, tenant_id=None) is not None
    db.close()


def test_google_login_reuses_identity_bound_user():
    repo, db = _new_repo()
    service = AuthService(repo)

    user = repo.create_user("bound@example.com", display_name="Bound User")
    repo.create_google_identity(
        user_id=user.user_id,
        google_sub="sub-1",
        email="old@example.com",
        email_verified=True,
        raw_profile_json="{}",
    )
    repo.create_user("old@example.com", display_name="Wrong User")

    old_mode = settings.auth_google_verify_mode
    settings.auth_google_verify_mode = "dev_unverified"
    try:
        token = _make_unverified_jwt(
            {
                "sub": "sub-1",
                "email": "bound@example.com",
                "email_verified": "false",
                "name": "Bound User v2",
            }
        )
        _, _, logged_in_user, _, _ = service.login_with_google(token)
        assert logged_in_user.user_id == user.user_id
    finally:
        settings.auth_google_verify_mode = old_mode
        db.close()


def test_tenant_invitation_accept_flow():
    repo, db = _new_repo()
    service = AuthService(repo)

    owner = repo.create_user("owner@example.com", display_name="Owner")
    tenant = repo.create_tenant("Org", "org")
    repo.create_tenant_membership(tenant.tenant_id, owner.user_id, role="owner")

    invitation = service.invite_member(
        inviter_user_id=owner.user_id,
        inviter_tenant_id=tenant.tenant_id,
        invitee_email="member@example.com",
        role="admin",
        expires_in_hours=24,
    )
    assert invitation.status == "pending"
    assert invitation.role == "admin"

    invitee = repo.create_user("member@example.com", display_name="Member")
    access_token, _, switched_tenant, membership, accepted_invitation = service.accept_invitation(
        user_id=invitee.user_id,
        invite_code=invitation.invite_code,
    )
    assert access_token.startswith("ca_")
    assert switched_tenant.tenant_id == tenant.tenant_id
    assert membership.role == "admin"
    assert accepted_invitation.status == "accepted"

    ctx = service.get_auth_context(access_token)
    assert ctx is not None
    assert ctx.tenant_id == tenant.tenant_id
    db.close()


def test_switch_tenant_requires_membership():
    repo, db = _new_repo()
    service = AuthService(repo)

    user = repo.create_user("switcher@example.com")
    t1 = repo.create_tenant("T1", "sw-t1")
    t2 = repo.create_tenant("T2", "sw-t2")
    repo.create_tenant_membership(t1.tenant_id, user.user_id, role="member")

    token, _, tenant, _ = service.switch_tenant(user_id=user.user_id, target_tenant_id=t1.tenant_id)
    assert token.startswith("ca_")
    assert tenant.tenant_id == t1.tenant_id

    try:
        service.switch_tenant(user_id=user.user_id, target_tenant_id=t2.tenant_id)
        assert False, "expected AuthPermissionError"
    except AuthPermissionError:
        pass
    db.close()
