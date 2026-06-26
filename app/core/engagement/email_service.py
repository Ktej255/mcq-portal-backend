"""
Email engagement service using Resend API.
Sends welcome sequence emails to new students.
API key is read from RESEND_API_KEY env var.

All functions fail gracefully — if the API key is missing or the call
fails, the error is logged and the function returns without raising.
The main application flow is never interrupted by engagement failures.
"""

import os
import logging
from pathlib import Path
from typing import Optional

import resend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read once at module load)
# ---------------------------------------------------------------------------

RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM_ADDRESS: str = os.environ.get("EMAIL_FROM_ADDRESS", "hello@saritclasses.com")

if not RESEND_API_KEY:
    logger.warning(
        "RESEND_API_KEY not set — email engagement is DISABLED. "
        "Set the env var to enable outbound emails."
    )
else:
    resend.api_key = RESEND_API_KEY

# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_template(name: str) -> Optional[str]:
    """Load an HTML template from the templates directory."""
    path = _TEMPLATES_DIR / name
    if not path.exists():
        logger.error("Email template not found: %s", path)
        return None
    return path.read_text(encoding="utf-8")


def _render_welcome_html(name: str, plan_data: dict) -> Optional[str]:
    """Render the welcome email template with student data."""
    html = _load_template("welcome.html")
    if html is None:
        return None

    # Simple placeholder replacement
    html = html.replace("{{name}}", name)
    html = html.replace("{{target_year}}", plan_data.get("target_year", "2027"))
    html = html.replace("{{first_topic_url}}", plan_data.get("first_topic_url", "/upsc"))
    html = html.replace("{{first_topic_title}}", plan_data.get("first_topic_title", "your first topic"))
    html = html.replace("{{plan_summary}}", plan_data.get("plan_summary", "Your personalized study plan"))

    return html


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_email(to: str, subject: str, html_body: str) -> bool:
    """
    Send a single email via Resend.

    Returns True if sent successfully, False otherwise.
    Never raises — logs errors internally.
    """
    if not RESEND_API_KEY:
        logger.warning("Email not sent (API key missing): to=%s subject=%s", to, subject)
        return False

    try:
        params = {
            "from": EMAIL_FROM_ADDRESS,
            "to": [to],
            "subject": subject,
            "html": html_body,
        }
        response = resend.Emails.send(params)
        logger.info("Email sent successfully: to=%s id=%s", to, response.get("id", "unknown"))
        return True
    except Exception as exc:
        logger.error("Failed to send email: to=%s error=%s", to, str(exc))
        return False


def send_welcome_email(name: str, email: str, plan_data: dict) -> bool:
    """
    Send the welcome email (Email 1 of the onboarding sequence).

    Args:
        name: Student's display name
        email: Student's email address
        plan_data: Dict with keys: target_year, first_topic_url, first_topic_title, plan_summary

    Returns True if sent, False otherwise. Never raises.
    """
    if not RESEND_API_KEY:
        logger.warning(
            "Welcome email not sent (API key missing): name=%s email=%s", name, email
        )
        return False

    subject = "Welcome to Sarit Classes — Your study plan is ready"
    html_body = _render_welcome_html(name, plan_data)

    if html_body is None:
        logger.error("Could not render welcome email template for %s", email)
        return False

    return send_email(to=email, subject=subject, html_body=html_body)
