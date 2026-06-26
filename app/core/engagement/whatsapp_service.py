"""
WhatsApp engagement service using Wati API.
Sends welcome and progress messages to students.
API key is read from WATI_API_KEY and WATI_API_URL env vars.

All functions fail gracefully — if credentials are missing or the call
fails, the error is logged and the function returns without raising.
The main application flow is never interrupted by engagement failures.
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read once at module load)
# ---------------------------------------------------------------------------

WATI_API_KEY: str = os.environ.get("WATI_API_KEY", "")
WATI_API_URL: str = os.environ.get("WATI_API_URL", "https://live-server-115247.wati.io")

if not WATI_API_KEY:
    logger.warning(
        "WATI_API_KEY not set — WhatsApp engagement is DISABLED. "
        "Set the env var to enable outbound WhatsApp messages."
    )

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_headers() -> dict:
    """Build auth headers for Wati API requests."""
    return {
        "Authorization": f"Bearer {WATI_API_KEY}",
        "Content-Type": "application/json",
    }


def _normalize_phone(phone: str) -> str:
    """
    Normalize phone number to E.164-ish format for Wati.
    Strips leading + and spaces. Wati expects digits only (e.g. 919876543210).
    """
    cleaned = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    # If it's a 10-digit Indian number, prepend country code
    if len(cleaned) == 10 and cleaned[0] in ("6", "7", "8", "9"):
        cleaned = "91" + cleaned
    return cleaned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_template_message(
    phone: str,
    template_name: str,
    parameters: list[dict],
) -> bool:
    """
    Send a WhatsApp template message via Wati.

    Args:
        phone: Student phone number (any common format)
        template_name: Wati-approved template name
        parameters: List of parameter dicts, e.g. [{"name": "1", "value": "John"}]

    Returns True if sent successfully, False otherwise.
    Never raises — logs errors internally.
    """
    if not WATI_API_KEY:
        logger.warning(
            "WhatsApp not sent (API key missing): phone=%s template=%s",
            phone,
            template_name,
        )
        return False

    normalized_phone = _normalize_phone(phone)
    url = f"{WATI_API_URL}/api/v1/sendTemplateMessage"

    payload = {
        "template_name": template_name,
        "broadcast_name": f"engagement_{template_name}",
        "parameters": parameters,
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                url,
                json=payload,
                headers=_get_headers(),
                params={"whatsappNumber": normalized_phone},
            )

        if response.status_code in (200, 201):
            logger.info(
                "WhatsApp template sent: phone=%s template=%s",
                normalized_phone,
                template_name,
            )
            return True
        else:
            logger.error(
                "WhatsApp send failed: phone=%s status=%d body=%s",
                normalized_phone,
                response.status_code,
                response.text[:200],
            )
            return False

    except httpx.TimeoutException:
        logger.error("WhatsApp send timed out: phone=%s template=%s", normalized_phone, template_name)
        return False
    except Exception as exc:
        logger.error("WhatsApp send error: phone=%s error=%s", normalized_phone, str(exc))
        return False


def send_welcome_message(
    phone: str,
    student_name: str,
    first_topic_url: str,
) -> bool:
    """
    Send the welcome WhatsApp message to a new student.

    Uses the 'welcome_student' template (must be pre-approved in Wati dashboard).
    Template expected parameters:
      {{1}} = student first name
      {{2}} = first topic URL

    Returns True if sent, False otherwise. Never raises.
    """
    if not WATI_API_KEY:
        logger.warning(
            "Welcome WhatsApp not sent (API key missing): phone=%s name=%s",
            phone,
            student_name,
        )
        return False

    parameters = [
        {"name": "1", "value": student_name},
        {"name": "2", "value": first_topic_url},
    ]

    return send_template_message(
        phone=phone,
        template_name="welcome_student",
        parameters=parameters,
    )
