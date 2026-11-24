import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# database.py opens a Postgres pool and a Redis client at import time.
# Replace both with mocks so the tests need no running services.
import psycopg2.pool  # noqa: E402
import redis  # noqa: E402

mock.patch.object(psycopg2.pool, "SimpleConnectionPool", mock.MagicMock()).start()
mock.patch.object(redis, "Redis", mock.MagicMock()).start()
os.environ.setdefault("PUBLIC_BASE_URL", "https://hop.test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-0123456789")


import pytest  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """One app instance for the whole run: the MCP session manager can only be started once per process."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app, base_url="https://hop.test", follow_redirects=False) as c:
        yield c
