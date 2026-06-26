"""
Welcome sequence orchestration for Sarit Classes.
Determines which email to send based on days since signup.
"""

from datetime import datetime, timedelta

from app.core.email.service import send_email, is_email_configured
from app.core.email.templates import (
    welcome_email,
    daily_loop_email,
    first_gap_report_email,
    week_one_retro_email,
    upgrade_nudge_email,
)

SEQUENCE = [
    {"day": 0, "template": "welcome"},
    {"day": 2, "template": "daily_loop"},
    {"day": 4, "template": "first_gap_report"},
    {"day": 7, "template": "week_one_retro"},
    {"day": 14, "template": "upgrade_nudge"},
]


def send_welcome_sequence_email(email: str, name: str, days_since_signup: int) -> bool:
    """Send the appropriate email based on days since signup.

    Args:
        email: Recipient email address.
        name: User's display name.
        days_since_signup: Number of days since the user signed up.

    Returns:
        True if an email was sent successfully, False otherwise.
    """
    template_map = {
        "welcome": welcome_email,
        "daily_loop": daily_loop_email,
        "first_gap_report": first_gap_report_email,
        "week_one_retro": week_one_retro_email,
        "upgrade_nudge": upgrade_nudge_email,
    }

    for item in SEQUENCE:
        if item["day"] == days_since_signup:
            fn = template_map[item["template"]]
            subject, html = fn(name)
            return send_email(email, subject, html)
    return False


def trigger_immediate_welcome(email: str, name: str) -> bool:
    """Called immediately after signup to send the welcome email.

    Args:
        email: Recipient email address.
        name: User's display name.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    subject, html = welcome_email(name)
    return send_email(email, subject, html)


def get_sequence_schedule() -> list[dict]:
    """Return the full sequence schedule (useful for cron job planners)."""
    return SEQUENCE
