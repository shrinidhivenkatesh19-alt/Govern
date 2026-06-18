"""Resend transactional email — onboarding, assignment, nudge templates."""
import asyncio
import os
from typing import Optional

import resend

from core import logger

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
APP_URL = os.environ.get("APP_URL", "")
FROM = f"GOVERN Approval Agent <{SENDER_EMAIL}>"

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


async def _send(to_email: str, subject: str, html: str) -> Optional[str]:
    """Fire-and-forget email send. Never raises — failures logged only."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email")
        return None
    if not to_email:
        return None
    params = {"from": FROM, "to": [to_email], "subject": subject, "html": html}
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        eid = result.get("id") if isinstance(result, dict) else None
        logger.info(f"Email sent → {to_email} subject='{subject}' id={eid}")
        return eid
    except Exception as e:
        logger.error(f"Resend send failed → {to_email}: {e}")
        return None


# ---------- Templates ----------
_SHELL = """
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'IBM Plex Sans',Helvetica,Arial,sans-serif;color:#0a0a0a;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:40px 20px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e5e7eb;">
        <tr><td style="padding:24px 32px;border-bottom:1px solid #e5e7eb;background:#0a0a0a;">
          <div style="font-weight:800;letter-spacing:-0.02em;font-size:18px;color:#ffffff;">GOVERN</div>
          <div style="font-size:10px;letter-spacing:0.2em;color:#a3a3a3;text-transform:uppercase;margin-top:4px;">Approval Agent</div>
        </td></tr>
        <tr><td style="padding:32px;">{body}</td></tr>
        <tr><td style="padding:20px 32px;border-top:1px solid #e5e7eb;background:#fafafa;font-size:11px;color:#6b7280;">
          You're receiving this because you're part of an approval workflow on GOVERN.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>
"""


def _btn(label: str, url: str) -> str:
    return (
        f'<a href="{url}" '
        f'style="display:inline-block;background:#002FA7;color:#ffffff;text-decoration:none;'
        f'padding:12px 24px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;'
        f'font-size:12px;border-radius:0;">{label}</a>'
    )


# 1) Onboarding
async def send_onboarding(user: dict) -> Optional[str]:
    name = user.get("name", "there")
    role = (user.get("role", "submitter") or "").replace("_", " ").title()
    team = user.get("team") or "—"
    designation = user.get("designation") or role
    url = f"{APP_URL}/app" if APP_URL else "#"

    body = f"""
      <h1 style="font-family:Outfit,Helvetica,Arial,sans-serif;font-size:28px;font-weight:700;letter-spacing:-0.02em;margin:0 0 16px;">
        Welcome, {name}.
      </h1>
      <p style="font-size:15px;line-height:1.6;color:#374151;margin:0 0 16px;">
        Your account is live on <strong>GOVERN — Content Approval Agent</strong>. Routine content routes itself, the CEO only sees what should reach the CEO desk, and every approval has a clock.
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;border:1px solid #e5e7eb;">
        <tr><td style="padding:14px 16px;font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6b7280;border-bottom:1px solid #e5e7eb;">Your profile</td></tr>
        <tr><td style="padding:16px;font-size:14px;line-height:1.7;">
          <strong>{name}</strong><br/>
          <span style="color:#6b7280;">{designation} · {team}</span><br/>
          <span style="color:#6b7280;font-family:'JetBrains Mono',monospace;font-size:12px;">{user.get('email','')}</span><br/>
          <span style="display:inline-block;margin-top:8px;padding:3px 8px;background:#0a0a0a;color:#fff;font-size:10px;letter-spacing:0.18em;text-transform:uppercase;">{role}</span>
        </td></tr>
      </table>
      <p style="font-size:14px;line-height:1.6;color:#374151;margin:0 0 24px;">
        What you can do next:
      </p>
      <ul style="font-size:14px;line-height:1.8;color:#374151;padding-left:20px;margin:0 0 24px;">
        <li>Submit a piece of content for review and pick a reviewer.</li>
        <li>Track every submission's status, idle time, and SLA in the Control Room.</li>
        <li>Approve, request revision, or forward to the next reviewer in the chain.</li>
      </ul>
      {_btn("Open the Control Room", url)}
    """
    return await _send(user["email"], "Welcome to GOVERN — your approval workspace is ready", _SHELL.format(body=body))


# 2) Assignment
async def send_assignment(assignee: dict, submission: dict, submitter: dict, accept_by: str) -> Optional[str]:
    title = submission.get("title", "Untitled submission")
    request_type = submission.get("request_type", "—")
    sub_id = submission.get("id", "")
    url = f"{APP_URL}/app/submission/{sub_id}" if APP_URL else "#"
    chain_step = (len(submission.get("approval_chain", []) or []) + 1)

    body = f"""
      <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#002FA7;margin-bottom:8px;">New approval assigned</div>
      <h1 style="font-family:Outfit,Helvetica,Arial,sans-serif;font-size:24px;font-weight:700;letter-spacing:-0.02em;margin:0 0 8px;">
        {title}
      </h1>
      <p style="font-size:13px;color:#6b7280;margin:0 0 24px;">
        From <strong>{submitter.get('name','')}</strong>{(' · ' + submitter.get('designation','')) if submitter.get('designation') else ''}
        · Step {chain_step}
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;margin-bottom:24px;">
        <tr>
          <td style="padding:14px 16px;border-right:1px solid #e5e7eb;width:50%;">
            <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6b7280;margin-bottom:6px;">Request</div>
            <div style="font-size:14px;font-weight:600;">{request_type}</div>
          </td>
          <td style="padding:14px 16px;">
            <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6b7280;margin-bottom:6px;">Accept by</div>
            <div style="font-size:14px;font-weight:600;font-family:'JetBrains Mono',monospace;color:#FF2400;">{accept_by or 'TBD'}</div>
          </td>
        </tr>
      </table>
      <p style="font-size:14px;line-height:1.6;color:#374151;margin:0 0 24px;">
        Hi {assignee.get('name','')}, a new submission needs your acceptance. Once you accept, the agent moves it into review and starts the SLA clock.
      </p>
      {_btn("Review submission", url)}
      <p style="font-size:12px;color:#9ca3af;margin-top:24px;">
        Auto-nudges fire when accept-by passes. Hard escalation triggers at 80% of the overall deadline.
      </p>
    """
    return await _send(assignee["email"], f"Action needed: {title}", _SHELL.format(body=body))


# 3) Nudge
async def send_nudge(assignee: dict, submission: dict, from_user: dict, note: str = "") -> Optional[str]:
    title = submission.get("title", "Untitled submission")
    sub_id = submission.get("id", "")
    url = f"{APP_URL}/app/submission/{sub_id}" if APP_URL else "#"
    tl = submission.get("timeline") or {}
    status = submission.get("status", "")
    if status == "pending_acceptance":
        sla_label, sla_date = "Accept by", tl.get("accept_by", "—")
    elif status == "in_progress":
        sla_label, sla_date = "Review by", tl.get("review_by", "—")
    else:
        sla_label, sla_date = "Approve by", tl.get("approve_by", "—")

    body = f"""
      <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#B8860B;margin-bottom:8px;">Nudge — action requested</div>
      <h1 style="font-family:Outfit,Helvetica,Arial,sans-serif;font-size:24px;font-weight:700;letter-spacing:-0.02em;margin:0 0 16px;">
        {title}
      </h1>
      <p style="font-size:14px;line-height:1.6;color:#374151;margin:0 0 16px;">
        Hi {assignee.get('name','')}, <strong>{from_user.get('name','someone')}</strong>
        {(' · ' + from_user.get('designation','')) if from_user.get('designation') else ''}
        nudged this submission. It's been sitting with you and the SLA is approaching.
      </p>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #FFD700;background:#FFFEF7;margin-bottom:24px;">
        <tr><td style="padding:16px;">
          <div style="font-size:10px;letter-spacing:0.2em;text-transform:uppercase;color:#6b7280;margin-bottom:6px;">{sla_label}</div>
          <div style="font-size:18px;font-weight:700;font-family:'JetBrains Mono',monospace;">{sla_date}</div>
        </td></tr>
      </table>
      {('<p style="font-size:13px;color:#374151;background:#f3f4f6;padding:12px 16px;border-left:3px solid #002FA7;margin:0 0 24px;font-style:italic;">' + note + '</p>') if note else ''}
      {_btn("Open submission", url)}
    """
    subject = f"Nudge: please review '{title}'"
    return await _send(assignee["email"], subject, _SHELL.format(body=body))
