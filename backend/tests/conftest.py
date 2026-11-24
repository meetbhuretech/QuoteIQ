"""Test environment. Uses one shared in-memory SQLite database."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
os.environ["DATABASE_URL"] = "sqlite+pysqlite://"
os.environ["JWT_SECRET"] = "test-secret-not-for-production-32b"
os.environ["PROCESS_SYNC"] = "true"
os.environ["PROCESS_INLINE"] = "false"
os.environ["ENVIRONMENT"] = "test"
os.environ["STORAGE_DIR"] = str(ROOT / ".test-storage")
os.environ["MODEL_ARTIFACT_DIR"] = str(REPO / "ml" / "artifacts")
os.environ["MLFLOW_TRACKING_URI"] = ""

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def auth(client, email="ada@example.com", organization="Ada CNC", password="correct-horse-1", name="Ada Engineer"):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": name, "organization_name": organization},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body
