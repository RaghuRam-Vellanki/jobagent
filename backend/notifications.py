"""
Email notifications — V1.1 E5-S5.

Sends a small HTML email after a successful apply, when:
  - profile.email_notifications_enabled is True
  - SMTP_HOST + SMTP_USER + SMTP_PASSWORD are set in env
  - profile.notification_email (or profile.email as fallback) is non-empty

Uses stdlib smtplib + ssl. Defaults are tuned for Gmail (smtp.gmail.com:465 SSL),
but any SMTP provider with an SSL or STARTTLS port works via env overrides.
"""
from __future__ import annotations
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime

logger = logging.getLogger("notifications")

_SMTP_WARNING_LOGGED = False


def _smtp_config() -> dict | None:
    """Returns the SMTP config dict, or None if anything required is missing."""
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not user or not password:
        return None
    return {
        "host": host,
        "port": int(os.getenv("SMTP_PORT", "465")),
        "user": user,
        "password": password,
        "from": os.getenv("SMTP_FROM", user),
        "use_ssl": os.getenv("SMTP_USE_SSL", "true").lower() != "false",
    }


def send_apply_email(profile: dict, job: dict) -> bool:
    """Send an "applied" notification email. Returns True on success."""
    global _SMTP_WARNING_LOGGED

    if not profile.get("email_notifications_enabled"):
        return False

    to_addr = (profile.get("notification_email") or profile.get("email") or "").strip()
    if not to_addr:
        return False

    cfg = _smtp_config()
    if not cfg:
        if not _SMTP_WARNING_LOGGED:
            logger.warning(
                "[email] notifications enabled but SMTP_USER/SMTP_PASSWORD not set in env "
                "— skipping email. Add SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD to .env "
                "(Gmail: use an App Password, port 465, SSL)."
            )
            _SMTP_WARNING_LOGGED = True
        return False

    title = job.get("title") or "?"
    company = job.get("company") or "?"
    location = job.get("location") or ""
    url = job.get("url") or ""
    score = job.get("match_score")
    platform = job.get("platform") or ""
    applied_at = (job.get("applied_at")
                  or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))

    subject = f"Applied: {title} @ {company}"
    plain = (
        f"Applied to {title} at {company}\n"
        f"Location: {location}\n"
        f"Platform: {platform}\n"
        f"Match score: {score}\n"
        f"Applied at: {applied_at}\n"
        f"URL: {url}\n\n"
        f"— JobAgent"
    )
    html = f"""\
<!doctype html>
<html><body style="font-family: 'DM Sans', system-ui, sans-serif; color:#0A0A0A; max-width:560px; margin:0 auto; padding:24px;">
  <div style="font-size:11px; letter-spacing:0.08em; text-transform:uppercase; color:#6B6B6B;">
    JobAgent — applied
  </div>
  <h2 style="font-family:'General Sans', system-ui, sans-serif; font-size:22px; margin:8px 0 4px; letter-spacing:-0.02em;">
    {title}
  </h2>
  <div style="font-size:14px; color:#6B6B6B; margin-bottom:16px;">
    {company}{(' · ' + location) if location else ''}
  </div>
  <table style="font-size:13px; border-collapse:collapse;">
    <tr><td style="color:#6B6B6B; padding:2px 12px 2px 0;">Platform</td><td>{platform}</td></tr>
    <tr><td style="color:#6B6B6B; padding:2px 12px 2px 0;">Match score</td><td>{score}</td></tr>
    <tr><td style="color:#6B6B6B; padding:2px 12px 2px 0;">Applied at</td><td>{applied_at}</td></tr>
  </table>
  <p style="margin-top:20px;">
    <a href="{url}" style="display:inline-block; padding:8px 16px; background:#6366F1; color:#fff; text-decoration:none; border-radius:6px; font-size:13px;">
      Open job listing
    </a>
  </p>
  <hr style="border:none; border-top:1px solid #E8E8EC; margin:24px 0;"/>
  <div style="font-size:11px; color:#9C9C9C;">
    Sent by JobAgent. Disable these emails in Settings → Limits & Delays.
  </div>
</body></html>"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = to_addr
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        if cfg["use_ssl"]:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], context=ctx, timeout=15) as server:
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg["user"], cfg["password"])
                server.send_message(msg)
        logger.info(f"[email] sent → {to_addr}: {subject}")
        return True
    except Exception as e:
        logger.warning(f"[email] failed to send to {to_addr}: {e}")
        return False
