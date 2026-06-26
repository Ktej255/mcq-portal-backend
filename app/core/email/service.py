import os
import logging

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_EMAIL = "Sarit Classes <hello@saritclasses.com>"


def is_email_configured() -> bool:
    """Check if the Resend API key is available."""
    return bool(RESEND_API_KEY)


def send_email(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Returns True on success, False on failure."""
    if not is_email_configured():
        logger.warning("Email not configured (RESEND_API_KEY missing). Skipping send to %s", to)
        return False
    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent successfully to %s: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, str(e))
        return False
