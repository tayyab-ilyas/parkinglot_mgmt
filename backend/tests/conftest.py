import os

from sqlalchemy import create_engine, text

BASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://parking:parking@localhost:5432/parking")
TEST_URL = BASE_URL.rsplit("/", 1)[0] + "/parking_test"
os.environ["DATABASE_URL"] = TEST_URL  # before any app import

with create_engine(BASE_URL, isolation_level="AUTOCOMMIT").connect() as c:
    if not c.scalar(text("SELECT 1 FROM pg_database WHERE datname = 'parking_test'")):
        c.execute(text("CREATE DATABASE parking_test"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app import seed  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed.main()


def login(username: str, password: str) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    return client


@pytest.fixture
def admin():
    return login("admin", "admin123")


@pytest.fixture
def attendant():
    return login("attendant", "attendant123")
