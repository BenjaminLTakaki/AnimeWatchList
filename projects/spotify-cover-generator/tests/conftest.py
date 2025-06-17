import pytest
import os
import tempfile
from app import app, db

@pytest.fixture(scope='session')
def temp_dir():
    """Create temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment variables"""
    monkeypatch.setenv('FLASK_SECRET_KEY', 'test-secret-key')
    monkeypatch.setenv('SPOTIFY_CLIENT_ID', 'test-client-id')
    monkeypatch.setenv('SPOTIFY_CLIENT_SECRET', 'test-client-secret')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-gemini-key')
    monkeypatch.setenv('STABILITY_API_KEY', 'test-stability-key')

@pytest.fixture
def app_context():
    """Provide application context for tests"""
    with app.app_context():
        yield app