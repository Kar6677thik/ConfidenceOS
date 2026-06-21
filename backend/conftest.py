import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DB = Path(__file__).with_name("test_confidenceos_pytest.db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TEST_DB.as_posix()}")
os.environ.setdefault("CONFIDENCEOS_JWT_SECRET", "confidenceos-test-jwt-secret")
os.environ.setdefault("CONFIDENCEOS_BCRYPT_ROUNDS", "4")


DEMO_CREDENTIALS = {
    "Operator": ("operator", "ConfidenceOS-Op-2025"),
    "Maintenance": ("maint", "ConfidenceOS-Maint-2025"),
    "Engineer": ("engineer", "ConfidenceOS-Eng-2025"),
    "Manager": ("manager", "ConfidenceOS-Mgr-2025"),
    "Auditor": ("auditor", "ConfidenceOS-Aud-2025"),
}


@pytest.fixture
def client():
    """FastAPI test client with isolated DB and seeded demo users."""
    from database import init_db
    from auth import seed_demo_users
    import main

    init_db()
    seed_demo_users()
    return TestClient(main.app)


@pytest.fixture
def auth_headers(client):
    def _headers(role: str = "Engineer") -> dict:
        username, password = DEMO_CREDENTIALS[role]
        response = client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        assert response.status_code == 200, response.text
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _headers
