"""
app/services/email_service.py
Email doğrulama + şifre sıfırlama mailleri
MAIL_ENABLED=False ise sadece loglara yazar (dev mode)
"""
import logging
from app.core.config import settings

logger = logging.getLogger("autotaxhub.email")


async def send_verification_email(email: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    subject = "Verify your AutoTax-HUB email"
    body = f"""
    <h2>Welcome to AutoTax-HUB!</h2>
    <p>Click the link below to verify your email address:</p>
    <p><a href="{link}" style="background:#00ff87;color:#000;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">Verify Email</a></p>
    <p>Link expires in {settings.EMAIL_TOKEN_EXPIRE_HOURS} hours.</p>
    <p>If you did not register, ignore this email.</p>
    """
    await _send(email, subject, body)


async def send_password_reset_email(email: str, token: str) -> None:
    link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    subject = "Reset your AutoTax-HUB password"
    body = f"""
    <h2>Password Reset Request</h2>
    <p>Click the link below to reset your password:</p>
    <p><a href="{link}" style="background:#4f8ef7;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold">Reset Password</a></p>
    <p>Link expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes.</p>
    <p>If you did not request this, ignore this email.</p>
    """
    await _send(email, subject, body)


async def _send(to: str, subject: str, html_body: str) -> None:
    if not settings.MAIL_ENABLED:
        logger.info(f"[EMAIL DISABLED] To:{to} | Subject:{subject}")
        return
    try:
        from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
        conf = ConnectionConfig(
            MAIL_USERNAME   = settings.MAIL_USERNAME,
            MAIL_PASSWORD   = settings.MAIL_PASSWORD,
            MAIL_FROM       = settings.MAIL_FROM,
            MAIL_FROM_NAME  = settings.MAIL_FROM_NAME,
            MAIL_PORT       = settings.MAIL_PORT,
            MAIL_SERVER     = settings.MAIL_SERVER,
            MAIL_STARTTLS   = settings.MAIL_STARTTLS,
            MAIL_SSL_TLS    = settings.MAIL_SSL_TLS,
            USE_CREDENTIALS = True,
        )
        msg = MessageSchema(subject=subject, recipients=[to], body=html_body, subtype=MessageType.html)
        await FastMail(conf).send_message(msg)
        logger.info(f"Email sent to {to}")
    except Exception as e:
        logger.error(f"Email send failed: {e}")
