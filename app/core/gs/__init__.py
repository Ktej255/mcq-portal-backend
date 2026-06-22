"""GS (General Studies) backend domain.

This package is the backend source of truth for the GS student experience
(starting with Geography), mirroring the proven ``app.core.optional`` pattern
under the Master Plan GATE-1 decision (standardize the live loop on a real
backend). It is intentionally namespaced (``gs_`` table prefix) and additive:
content is ingested into the canonical DB via the no-loss importer and served
behind the existing localStorage-fail-soft frontend seam, so nothing breaks
while the source of truth moves to FastAPI/Postgres.
"""

MODULE_NAME = "gs"

__all__ = ["MODULE_NAME"]
