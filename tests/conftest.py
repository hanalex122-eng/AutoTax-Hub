"""
tests/conftest.py
Pytest fixtures — in-memory SQLite, test client, test users
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.core.config import settings
from main import app

# ── In-memory SQLite for tests ────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite:///./test.db"

engine_test = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
SessionTest  = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = SessionTest()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)
    import os
    if os.path.exists("test.db"):
        os.remove("test.db")


@pytest.fixture
def db():
    db = SessionTest()
    yield db
    db.close()


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def registered_user(client):
    """Creates and returns a verified test user."""
    payload = {"email": "test@example.com", "full_name": "Test User", "password": "Secret1!"}
    client.post("/api/v1/auth/register", json=payload)
    # Mark as verified in DB
    db = SessionTest()
    from app.models.user import User
    user = db.query(User).filter(User.email == payload["email"]).first()
    if user:
        user.is_verified = True
        db.commit()
    db.close()
    return payload


@pytest.fixture
def auth_headers(client, registered_user):
    """Returns Authorization headers for registered user."""
    r = client.post("/api/v1/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
