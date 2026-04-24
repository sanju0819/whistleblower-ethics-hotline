"""
tests/conftest.py
Shared pytest fixtures for the ai-service test suite.

I-12 FIX: Moving the `client` fixture to conftest.py means every test file
gets it automatically — no copy-paste per file.
"""

import pytest
from app import app


@pytest.fixture
def client():
    """Provide a Flask test client with TESTING mode enabled."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
