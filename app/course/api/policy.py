"""Public policy / consent document."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.course.ops.policy import policy_document
from app.course.settings import Settings, get_settings

router = APIRouter(tags=["policy"])


@router.get("/policy")
def get_policy(settings: Settings = Depends(get_settings)) -> dict:
    return policy_document(settings)
