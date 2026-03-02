from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class InvitationDeliveryError(RuntimeError):
    pass


@dataclass
class InvitationEmailResult:
    sent: bool
    provider: str | None = None
    message_id: str | None = None
    error: str | None = None


class InvitationMailer:
    def build_invite_link(self, invite_code: str) -> str:
        base = (settings.invite_accept_url_base or "http://127.0.0.1:5173").rstrip("/")
        return f"{base}/accept-invite?code={invite_code}"

    def send_invitation_email(
        self,
        *,
        tenant_name: str,
        inviter_email: str | None,
        invitee_email: str,
        invite_code: str,
        role: str,
        expires_at: datetime,
    ) -> InvitationEmailResult:
        if not settings.invite_email_enabled:
            return InvitationEmailResult(sent=False, provider=None, error="invite email disabled")

        provider = (settings.invite_email_provider or "noop").strip().lower()
        invite_link = self.build_invite_link(invite_code)
        subject = f"{settings.invite_email_subject_prefix} You are invited to {tenant_name}"
        html_body, text_body = self._render_email(
            tenant_name=tenant_name,
            inviter_email=inviter_email,
            invitee_email=invitee_email,
            invite_link=invite_link,
            role=role,
            expires_at=expires_at,
        )

        try:
            if provider == "resend":
                return self._send_with_resend(invitee_email, subject, html_body, text_body)
            if provider == "sendgrid":
                return self._send_with_sendgrid(invitee_email, subject, html_body, text_body)
            if provider == "noop":
                logger.info(
                    "Invite email noop provider: to=%s tenant=%s role=%s link=%s",
                    invitee_email,
                    tenant_name,
                    role,
                    invite_link,
                )
                return InvitationEmailResult(sent=True, provider="noop", message_id="noop")
            return InvitationEmailResult(sent=False, provider=provider, error=f"unknown provider: {provider}")
        except Exception as exc:
            logger.warning("Invite email send failed via %s: %s", provider, exc)
            return InvitationEmailResult(sent=False, provider=provider, error=str(exc))

    def _send_with_resend(
        self,
        invitee_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> InvitationEmailResult:
        if not settings.resend_api_key:
            raise InvitationDeliveryError("RESEND_API_KEY is empty")
        if not settings.invite_email_from:
            raise InvitationDeliveryError("INVITE_EMAIL_FROM is empty")

        payload: dict[str, object] = {
            "from": settings.invite_email_from,
            "to": [invitee_email],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
        if settings.invite_email_reply_to:
            payload["reply_to"] = settings.invite_email_reply_to

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code not in {200, 201, 202}:
            raise InvitationDeliveryError(f"resend error {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        return InvitationEmailResult(sent=True, provider="resend", message_id=str(data.get("id") or ""))

    def _send_with_sendgrid(
        self,
        invitee_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> InvitationEmailResult:
        if not settings.sendgrid_api_key:
            raise InvitationDeliveryError("SENDGRID_API_KEY is empty")
        if not settings.invite_email_from:
            raise InvitationDeliveryError("INVITE_EMAIL_FROM is empty")

        payload: dict[str, object] = {
            "personalizations": [{"to": [{"email": invitee_email}]}],
            "from": {"email": settings.invite_email_from},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_body},
                {"type": "text/html", "value": html_body},
            ],
        }
        if settings.invite_email_reply_to:
            payload["reply_to"] = {"email": settings.invite_email_reply_to}

        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code not in {200, 201, 202}:
            raise InvitationDeliveryError(f"sendgrid error {resp.status_code}: {resp.text[:300]}")

        message_id = resp.headers.get("x-message-id", "")
        return InvitationEmailResult(sent=True, provider="sendgrid", message_id=message_id)

    def _render_email(
        self,
        *,
        tenant_name: str,
        inviter_email: str | None,
        invitee_email: str,
        invite_link: str,
        role: str,
        expires_at: datetime,
    ) -> tuple[str, str]:
        inviter_line = inviter_email or "A workspace admin"
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        text = (
            f"Hi {invitee_email},\n\n"
            f"{inviter_line} invited you to join '{tenant_name}' as '{role}'.\n"
            f"Accept invite: {invite_link}\n\n"
            f"This invite expires at {expires_text}.\n"
        )
        html = (
            "<div style='font-family:Arial,sans-serif;line-height:1.5;color:#111827'>"
            f"<p>Hi {invitee_email},</p>"
            f"<p>{inviter_line} invited you to join <strong>{tenant_name}</strong> as <strong>{role}</strong>.</p>"
            f"<p><a href='{invite_link}' style='display:inline-block;padding:10px 14px;border-radius:8px;background:#2563eb;color:#fff;text-decoration:none'>Accept Invitation</a></p>"
            f"<p>Or open this link directly:<br/><code>{invite_link}</code></p>"
            f"<p style='color:#6b7280;font-size:12px'>This invite expires at {expires_text}.</p>"
            "</div>"
        )
        return html, text
