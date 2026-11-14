"""Async HTTP for archive requests: one shared client, a concurrency limit, retries with backoff and jitter."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

ATTEMPTS: Final = 5
MAX_BACKOFF_S: Final = 60.0
RETRY_STATUS: Final = frozenset({429, 500, 502, 503, 504})


class ArchiveError(Exception):
    """An archive request failed for good (after retries, or with a status that is not worth retrying)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Http:
    client: httpx.AsyncClient
    limit: asyncio.Semaphore


def make_http(max_concurrency: int | None = None, transport: httpx.AsyncBaseTransport | None = None) -> Http:
    concurrency = max_concurrency or settings.max_concurrency
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_s),
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
        limits=httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency),
        transport=transport,
    )
    return Http(client=client, limit=asyncio.Semaphore(concurrency))


def backoff_s(attempt: int, response: httpx.Response | None) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after is not None and retry_after.isdigit():
        return min(float(retry_after), MAX_BACKOFF_S)
    return min(2.0**attempt, MAX_BACKOFF_S) * random.uniform(0.5, 1.5)  # noqa: S311 - jitter, not crypto


def _host(url: str) -> str:
    return urlsplit(url).netloc


async def get(http: Http, url: str, params: Mapping[str, str] | None = None) -> httpx.Response:
    """GET with retries on transport errors, 429 and 5xx. Other statuses raise ArchiveError at once."""
    for attempt in range(1, ATTEMPTS + 1):
        response: httpx.Response | None = None
        try:
            async with http.limit:
                response = await http.client.get(url, params=params)
        except httpx.TransportError as exc:
            if attempt == ATTEMPTS:
                raise ArchiveError(f"{_host(url)} unreachable: {type(exc).__name__}") from exc
            logger.info("Attempt %d to %s failed: %s", attempt, _host(url), exc)
        else:
            if response.status_code < 400:
                return response
            if response.status_code not in RETRY_STATUS or attempt == ATTEMPTS:
                raise ArchiveError(f"HTTP {response.status_code} from {_host(url)}", response.status_code)
            logger.info("Attempt %d to %s got HTTP %d", attempt, _host(url), response.status_code)
        await asyncio.sleep(backoff_s(attempt, response))
    raise AssertionError("unreachable")
