"""Application package.

`uvicorn app:app` loads the FastAPI instance lazily via ``__getattr__`` so
``import app.fix_pytree`` / ``import app.rag_backend`` does not bootstrap the API.
"""

from __future__ import annotations

from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from app.api.app import app as fastapi_app

        return fastapi_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
