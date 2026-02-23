"""Email utility — sends transactional emails via SMTP (TLS)."""
from __future__ import annotations

import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_smtp_connection() -> smtplib.SMTP:
    """Open an authenticated SMTP TLS connection."""
    conn = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
    conn.ehlo()
    conn.starttls()
    conn.ehlo()
    conn.login(settings.SMTP_USER, settings.SMTP_PASS)
    return conn


def send_email(
    to: str,
    subject: str,
    html_body: str,
    plain_body: str = "",
    attachment_bytes: Optional[bytes] = None,
    attachment_filename: Optional[str] = None,
    attachment_mime: str = "application/pdf",
) -> bool:
    """
    Send a transactional email. Returns True on success, False on failure.

    Parameters
    ----------
    attachment_bytes    : raw bytes of an optional attachment (e.g. PDF invoice)
    attachment_filename : filename shown to the recipient
    attachment_mime     : MIME type, default 'application/pdf'
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"DoceanAI <{settings.EMAIL_FROM}>"
        msg["To"] = to

        if plain_body:
            msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if attachment_bytes and attachment_filename:
            part = MIMEBase(*attachment_mime.split("/"))
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment_filename}"',
            )
            msg.attach(part)

        with _build_smtp_connection() as conn:
            conn.sendmail(settings.EMAIL_FROM, [to], msg.as_string())

        logger.info(f"[Email] Sent '{subject}' → {to}")
        return True

    except Exception as exc:
        logger.error(f"[Email] Failed to send '{subject}' to {to}: {exc}")
        return False


# ── Convenience senders ───────────────────────────────────────────────────────

def send_otp_email(to: str, otp: str, full_name: str = "") -> bool:
    """Send a 6-digit OTP for email verification."""
    greeting = f"Hi {full_name}," if full_name else "Hello,"
    subject = "Your DoceanAI Verification Code"
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }}
    .container {{ max-width: 500px; margin: 40px auto; background: #fff;
                  border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
    .logo {{ font-size: 26px; font-weight: 700; color: #1e40af; margin-bottom: 24px; }}
    .otp {{ font-size: 40px; font-weight: 800; letter-spacing: 10px; color: #1e40af;
            background: #eff6ff; padding: 16px 24px; border-radius: 8px;
            display: inline-block; margin: 16px 0; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">DoceanAI</div>
    <p>{greeting}</p>
    <p>Use the verification code below to complete your registration.
       The code expires in <strong>10 minutes</strong>.</p>
    <div class="otp">{otp}</div>
    <p>If you did not request this code, please ignore this email.</p>
    <div class="footer">
      &copy; DoceanAI &nbsp;|&nbsp; noreply@doceanai.cloud
    </div>
  </div>
</body>
</html>
"""
    plain_body = f"{greeting}\n\nYour DoceanAI verification code is: {otp}\n\nExpires in 10 minutes."
    return send_email(to, subject, html_body, plain_body)


def send_invoice_email(
    to: str,
    full_name: str,
    invoice_pdf_bytes: bytes,
    invoice_number: str,
) -> bool:
    """Send a payment invoice PDF to the user."""
    subject = f"DoceanAI Invoice #{invoice_number}"
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: Arial, sans-serif; background: #f4f4f4; margin: 0; padding: 0; }}
    .container {{ max-width: 560px; margin: 40px auto; background: #fff;
                  border-radius: 8px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,.1); }}
    .logo {{ font-size: 26px; font-weight: 700; color: #1e40af; margin-bottom: 24px; }}
    .highlight {{ color: #1e40af; font-weight: 600; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #9ca3af; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">DoceanAI</div>
    <p>Hi {full_name},</p>
    <p>Thank you for your subscription! Your payment has been confirmed.</p>
    <p>Please find your invoice <span class="highlight">#{invoice_number}</span>
       attached to this email as a PDF.</p>
    <p>Your OCR pages have been added to your account and are ready to use.</p>
    <div class="footer">
      &copy; DoceanAI &nbsp;|&nbsp; noreply@doceanai.cloud
    </div>
  </div>
</body>
</html>
"""
    plain_body = (
        f"Hi {full_name},\n\n"
        f"Thank you for your subscription! Your invoice #{invoice_number} is attached.\n\n"
        f"— DoceanAI"
    )
    return send_email(
        to=to,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
        attachment_bytes=invoice_pdf_bytes,
        attachment_filename=f"DoceanAI_Invoice_{invoice_number}.pdf",
    )
