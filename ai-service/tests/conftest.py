"""
tests/conftest.py
Shared pytest fixtures for the ai-service test suite.

I-12 FIX: Moving the `client` fixture to conftest.py means every test file
gets it automatically — no copy-paste per file.

HI-12 FIX: Set a dummy GROQ_API_KEY before importing `app` so that
create_app() doesn't raise RuntimeError in CI environments where .env
does not exist.
"""

import os
import pytest

# HI-12 FIX: Ensure GROQ_API_KEY is set BEFORE app import triggers create_app().
# In CI/CD pipelines there is no .env file; without this, every test crashes
# with "GROQ_API_KEY is missing" before any test function runs.
os.environ.setdefault("GROQ_API_KEY", "test-key-for-ci")

from app import app  # noqa: E402


@pytest.fixture
def client():
    """Provide a Flask test client with TESTING mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
