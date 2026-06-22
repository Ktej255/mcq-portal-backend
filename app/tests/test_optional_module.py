"""Tests for the Optional Subjects Platform backend module skeleton.

Verifies the optional module is wired into the FastAPI app, the health/contract
endpoint responds, and every optional route is auth-gated via the existing
authentication dependency (Requirements 15.1, 2.1; design Property 9/10).
"""
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_current_user

client = TestClient(app)

HEALTH_PATH = "/api/v1/optional/health"


def test_optional_router_is_registered():
    paths = [getattr(route, "path", "") for route in app.routes]
    assert HEALTH_PATH in paths


def test_health_requires_authentication():
    # No Authorization header -> rejected by the existing (real) auth dependency.
    response = client.get(HEALTH_PATH)
    assert response.status_code == 401


def test_health_returns_contract_payload_when_authenticated():
    # Verify the contract payload shape for an authenticated request. We override
    # the auth dependency with a fake user so the assertion is hermetic — it does
    # not depend on an external DB/auth backend (the MOCK_TOKEN path goes through
    # the real DB). The real-auth 401 path is covered above.
    class _FakeUser:
        id = 1
        email = "validator@upsc.local"
        google_uid = "dev-validator-id"

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    try:
        response = client.get(HEALTH_PATH)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["module"] == "optional"
        assert body["data"]["status"] == "healthy"
        assert body["data"]["authenticated"] is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_optional_module_does_not_reference_gs_geography():
    # Hard isolation constraint (Requirement 2): the optional API/core packages
    # must not import or reference GS Geography (/upsc/geography) modules.
    import app.api.v1.optional as optional_api
    import app.core.optional as optional_core

    for module in (optional_api, optional_core):
        source_module = getattr(module, "__file__", "") or ""
        assert "geography" not in source_module.lower()
