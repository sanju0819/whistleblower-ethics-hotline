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
    """Flask test client with TESTING mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def mock_groq_success():
    """
    Reusable mock for a successful Groq API HTTP response.
    Use in service-level tests to avoid patching deep internals.
    """
    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"result": "ok"}'}}]
    }
    return mock_resp


@pytest.fixture
def sample_report_text():
    """Standard whistleblower report text used across multiple tests."""
    return "My manager has been falsifying expense reports for three months."


@pytest.fixture
def sample_harassment_text():
    """Harassment report text used across multiple tests."""
    return "A senior colleague is making inappropriate comments to junior staff."
