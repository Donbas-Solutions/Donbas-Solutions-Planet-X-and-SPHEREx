from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from ..archive.resolve import ResolveError
from ..models import ResolveResult
from .deps import NameResolver, SharedHttp

router = APIRouter(prefix="/api")


@router.get("/resolve", response_model=ResolveResult)
async def resolve(
    http: SharedHttp, resolver: NameResolver, name: Annotated[str, Query(min_length=1, max_length=100)]
) -> ResolveResult:
    try:
        result = await resolver.resolve(http, name)
    except ResolveError as exc:
        raise HTTPException(status_code=503, detail="SIMBAD is unreachable; enter coordinates instead.") from exc
    if result is None:
        raise HTTPException(status_code=404, detail=f"{name!r} is not known to SIMBAD")
    return result
