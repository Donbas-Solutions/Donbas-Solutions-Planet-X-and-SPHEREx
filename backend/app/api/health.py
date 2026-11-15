from __future__ import annotations

from fastapi import APIRouter

from ..config import settings
from ..models import CacheStats, Health
from ..pipeline.bundle import MANIFEST
from .deps import Discovery

router = APIRouter(prefix="/api")


def _cache_stats() -> CacheStats:
    raw_bytes = sum(p.stat().st_size for p in settings.raw_dir.rglob("*") if p.is_file())
    processed = sum(1 for p in settings.processed_dir.glob(f"*/{MANIFEST}") if p.is_file())
    return CacheStats(raw_mb=round(raw_bytes / 1e6, 1), processed_items=processed)


@router.get("/health", response_model=Health)
def health(discovery: Discovery) -> Health:
    return Health(status="ok", collections=list(discovery.current), cache=_cache_stats())
