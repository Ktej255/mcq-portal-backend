"""Security regression guard: the ``MOCK_TOKEN`` auth bypass is gated.

``get_current_user`` supports a ``MOCK_TOKEN[_<google_uid>]`` bypass used by
local dev / Playwright e2e to authenticate without a real Firebase token. That
bypass MUST NOT be honored in production: otherwise anyone could impersonate any
user (and the default branch auto-provisions an ADMIN) just by sending a static
token string.

This test enforces that the bypass is honored ONLY when ``settings.ALLOW_MOCK_AUTH``
is explicitly enabled (it defaults to ``False``):

* flag OFF (the production default) → ``MOCK_TOKEN`` is rejected as an invalid
  credential (401), exactly like any other bad token;
* flag ON (dev/test/e2e) → the bypass works and resolves a user;
* no token at all → 401 regardless of the flag.

It also pins the secure default so a future config change can't silently turn
the bypass on in production.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.api.dependencies import get_current_user
from app.core.config import settings
from app.models.domain import User, RoleEnum

# Importing the optional models too keeps Base.metadata consistent with the
# rest of the suite when we create_all (no partial-metadata surprises).
from app.core.optional import models as optional_models  # noqa: F401
from app.core.optional import student_models as optional_student_models  # noqa: F401


@pytest.fixture()
def client_and_session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: User = Depends(get_current_user)):
        return {"email": user.email, "role": str(user.role)}

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app), SessionLocal
    app.dependency_overrides.clear()


def test_secure_default_is_off():
    # Pin the secure default: the bypass must be OFF unless explicitly enabled in the class definition.
    from app.core.config import Settings
    assert Settings.model_fields['ALLOW_MOCK_AUTH'].default is False


def test_mock_token_rejected_when_disabled(client_and_session, monkeypatch):
    client, _ = client_and_session
    monkeypatch.setattr(settings, "ALLOW_MOCK_AUTH", False)

    resp = client.get("/whoami", headers={"Authorization": "Bearer MOCK_TOKEN"})
    assert resp.status_code == 401, resp.text


def test_mock_token_persona_rejected_when_disabled(client_and_session, monkeypatch):
    # Even a persona-scoped MOCK_TOKEN_<uid> must be rejected when disabled.
    client, SessionLocal = client_and_session
    monkeypatch.setattr(settings, "ALLOW_MOCK_AUTH", False)

    db = SessionLocal()
    db.add(User(google_uid="persona-uid", email="persona@upsc.local",
                full_name="Persona", role=RoleEnum.STUDENT))
    db.commit()
    db.close()

    resp = client.get("/whoami", headers={"Authorization": "Bearer MOCK_TOKEN_persona-uid"})
    assert resp.status_code == 401, resp.text


def test_mock_token_works_when_enabled(client_and_session, monkeypatch):
    client, _ = client_and_session
    monkeypatch.setattr(settings, "ALLOW_MOCK_AUTH", True)

    resp = client.get("/whoami", headers={"Authorization": "Bearer MOCK_TOKEN"})
    assert resp.status_code == 200, resp.text
    # The default branch provisions the dev validator account.
    assert resp.json()["email"] == "validator@upsc.local"


def test_mock_token_persona_resolves_when_enabled(client_and_session, monkeypatch):
    # When enabled, a persona-scoped token is honored (resolves to *some* user).
    # NOTE: this only asserts the bypass is active (status 200) — the exact uid
    # extraction is pre-existing behavior and out of scope for this gate test.
    client, SessionLocal = client_and_session
    monkeypatch.setattr(settings, "ALLOW_MOCK_AUTH", True)

    db = SessionLocal()
    db.add(User(google_uid="persona-uid", email="persona@upsc.local",
                full_name="Persona", role=RoleEnum.STUDENT))
    db.commit()
    db.close()

    resp = client.get("/whoami", headers={"Authorization": "Bearer MOCK_TOKEN_persona-uid"})
    assert resp.status_code == 200, resp.text


def test_no_token_is_401_regardless_of_flag(client_and_session, monkeypatch):
    client, _ = client_and_session
    monkeypatch.setattr(settings, "ALLOW_MOCK_AUTH", True)
    resp = client.get("/whoami")
    assert resp.status_code == 401, resp.text
