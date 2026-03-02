from datetime import datetime, timedelta

from app.core.config import settings
from app.services.invite_mail_service import InvitationMailer


def test_build_invite_link_uses_base_url():
    old_base = settings.invite_accept_url_base
    settings.invite_accept_url_base = "https://agent.example.com/"
    try:
        link = InvitationMailer().build_invite_link("inv_abc")
        assert link == "https://agent.example.com/accept-invite?code=inv_abc"
    finally:
        settings.invite_accept_url_base = old_base


def test_send_invitation_email_noop_provider():
    old_enabled = settings.invite_email_enabled
    old_provider = settings.invite_email_provider
    settings.invite_email_enabled = True
    settings.invite_email_provider = "noop"
    try:
        result = InvitationMailer().send_invitation_email(
            tenant_name="Acme",
            inviter_email="owner@example.com",
            invitee_email="member@example.com",
            invite_code="inv_123",
            role="member",
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        assert result.sent is True
        assert result.provider == "noop"
    finally:
        settings.invite_email_enabled = old_enabled
        settings.invite_email_provider = old_provider
