"""
Cashfree Payment Gateway configuration.

Reads credentials from environment variables at import time.
If credentials are missing, logs a critical warning and sets is_configured=False.
Payment endpoints should check is_configured and return HTTP 503 when False.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CashfreeConfig:
    """Immutable configuration for the Cashfree payment gateway."""

    app_id: str
    secret_key: str
    environment: str  # "sandbox" or "production"
    is_configured: bool


def _load_config() -> CashfreeConfig:
    """Load Cashfree configuration from environment variables.

    If CASHFREE_APP_ID or CASHFREE_SECRET_KEY are missing/empty, logs a
    critical warning and returns a config with is_configured=False.
    Payment endpoints must check this flag and return 503 if not configured.
    """
    app_id = os.environ.get("CASHFREE_APP_ID", "").strip()
    secret_key = os.environ.get("CASHFREE_SECRET_KEY", "").strip()
    environment = os.environ.get("CASHFREE_ENVIRONMENT", "sandbox").strip()

    # Validate environment value
    if environment not in ("sandbox", "production"):
        logger.warning(
            "CASHFREE_ENVIRONMENT has invalid value '%s'; defaulting to 'sandbox'",
            environment,
        )
        environment = "sandbox"

    # Check required credentials
    missing = []
    if not app_id:
        missing.append("CASHFREE_APP_ID")
    if not secret_key:
        missing.append("CASHFREE_SECRET_KEY")

    if missing:
        logger.critical(
            "Cashfree payment credentials missing: %s. "
            "All payment endpoints will return HTTP 503 until configured.",
            ", ".join(missing),
        )
        return CashfreeConfig(
            app_id=app_id,
            secret_key=secret_key,
            environment=environment,
            is_configured=False,
        )

    logger.info(
        "Cashfree payments configured (environment=%s)", environment
    )
    return CashfreeConfig(
        app_id=app_id,
        secret_key=secret_key,
        environment=environment,
        is_configured=True,
    )


# Module-level singleton — validated at import time
cashfree_config = _load_config()
