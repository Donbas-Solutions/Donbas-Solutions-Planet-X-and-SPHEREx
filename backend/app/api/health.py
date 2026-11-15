from __future__ import annotations

from fastapi import APIRouter

from ..models import Health
from .deps import Cache, Discovery

router = APIRouter(prefix="/api")


@router.get("/health", response_model=Health)
def health(discovery: Discovery, cache: Cache) -> Health:
    return Health(status="ok", collections=list(discovery.current), cache=cache.stats())
