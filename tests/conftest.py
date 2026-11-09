"""Pytest fixtures for exit-interview integration tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "repos"

# Configure env before importing the FastAPI app.
os.environ["TESTING"] = "1"
os.environ["REPO_FIXTURE_ROOT"] = str(FIXTURE_ROOT)
os.environ.setdefault("STORAGE_RECORDINGS_DIR", str(Path(__file__).resolve().parent / "_recordings"))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    recordings = tmp_path / "recordings"
    recordings.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setenv("CONVERSATION_DB_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REPO_FIXTURE_ROOT", str(FIXTURE_ROOT))
    monkeypatch.setenv("STORAGE_RECORDINGS_DIR", str(recordings))

    from app.seproject.settings import get_settings

    get_settings.cache_clear()

    from app.storage.conversation_store import ConversationStore
    from app.seproject.db import configure_engine
    from app.seproject import exit_models  # noqa: F401
    from app.seproject import db_models  # noqa: F401
    from sqlmodel import SQLModel
    from fastapi.testclient import TestClient

    # Fresh store for this test DB
    store = ConversationStore(f"sqlite:///{db_path.as_posix()}")
    store.init()
    configure_engine(store.engine)
    SQLModel.metadata.create_all(store.engine)
    store.create_user("instructor", "instructor-dev", role="admin", is_admin=True)
    store.create_user("studenta", "password123", role="student")
    store.create_user("studentb", "password123", role="student")

    # Import app after env is set; patch the module-level store
    import app.api.app as app_module

    app_module.conversation_store = store
    app_module.app.state.conversation_store = store
    app_module.app.state.get_current_user = app_module._get_current_user
    configure_engine(store.engine)

    with TestClient(app_module.app) as test_client:
        yield test_client

    get_settings.cache_clear()
