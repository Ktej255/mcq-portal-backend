"""Security regression guard: every Optional-platform route is auth-gated.

The optional router declares ``dependencies=[Depends(get_current_user)]`` at the
package level so that EVERY route — current and future — requires authentication
(see `app/api/v1/optional/__init__.py`). This test enforces that invariant
mechanically by enumerating every registered ``/api/v1/optional/*`` route and
asserting an unauthenticated request is rejected. It will fail loudly if anyone
ever adds an optional route that is reachable without a token.

This is a standing guard (not tied to a single feature), complementing the
per-endpoint ``*_requires_auth`` tests: those cover specific routes, this covers
the whole surface so a newly-added route can't silently ship unauthenticated.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

# Importing the models/routers ensures every optional sub-router is registered.
from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional import student_models as optional_student_models  # noqa: F401

OPTIONAL_PREFIX = "/api/v1/optional"

# A path with no auth dependency would return 200/4xx-other; an auth-gated one
# returns 401 (no token) — that's the invariant.
_PARAM_RE = re.compile(r"\{[^}]+\}")


def _concrete_path(path: str) -> str:
    """Replace every path parameter with '1' (valid for both int and str params)."""
    return _PARAM_RE.sub("1", path)


def _optional_routes():
    """Yield (path, methods) for every registered optional route."""
    seen = set()
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if not path.startswith(OPTIONAL_PREFIX):
            continue
        key = (path, frozenset(methods))
        if key in seen:
            continue
        seen.add(key)
        yield path, methods


def test_optional_routes_exist():
    # Sanity: the optional surface is actually registered (so this guard is real).
    routes = list(_optional_routes())
    assert len(routes) >= 10, f"expected the optional router to be mounted, found {len(routes)}"


def test_every_optional_get_route_requires_auth():
    """Unauthenticated GET to any optional route must be rejected with 401."""
    client = TestClient(app)
    offenders = []
    for path, methods in _optional_routes():
        if "GET" not in methods:
            continue
        url = _concrete_path(path)
        resp = client.get(url)
        # No token → the package-level auth dependency must reject with 401.
        if resp.status_code != 401:
            offenders.append((url, resp.status_code))
    assert not offenders, f"Optional GET routes reachable without 401: {offenders}"


def test_every_optional_write_route_is_not_served_unauthenticated():
    """Unauthenticated POST/PUT/DELETE must never be served (no 2xx)."""
    client = TestClient(app)
    offenders = []
    for path, methods in _optional_routes():
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            if method not in methods:
                continue
            url = _concrete_path(path)
            resp = client.request(method, url)
            # Must not be served (401 ideal; 422 also means "not served" since
            # auth/validation rejected it). Never a 2xx without a token.
            if 200 <= resp.status_code < 300:
                offenders.append((method, url, resp.status_code))
    assert not offenders, f"Optional write routes served without auth: {offenders}"
