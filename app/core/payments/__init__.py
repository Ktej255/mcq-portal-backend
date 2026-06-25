"""Cashfree Payments integration domain.

This package handles live payment collection via Cashfree Payments, including
order creation, webhook-based payment confirmation, subscription lifecycle
management, and refund processing.

Domain isolation: this package has zero cross-imports from other core modules
(``app.core.gs_lms``, ``app.core.optional``). It registers on the shared
declarative ``Base`` (``app.db.session.Base``) so that Alembic covers the schema.
Table names use a ``payment_`` / ``subscriptions`` namespace.
"""

MODULE_NAME = "payments"

__all__ = ["MODULE_NAME"]
