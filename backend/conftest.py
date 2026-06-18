import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client for script-style backend tests."""
    from database import init_db
    import main

    init_db()
    return TestClient(main.app)
