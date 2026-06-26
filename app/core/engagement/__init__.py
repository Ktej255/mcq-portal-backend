"""
Engagement automation module for Sarit Classes.
Handles WhatsApp (Wati) and Email (Resend) outbound messaging
for student onboarding and retention flows.
"""

from app.core.engagement.email_service import send_email, send_welcome_email
from app.core.engagement.whatsapp_service import send_template_message, send_welcome_message

__all__ = [
    "send_email",
    "send_welcome_email",
    "send_template_message",
    "send_welcome_message",
]
