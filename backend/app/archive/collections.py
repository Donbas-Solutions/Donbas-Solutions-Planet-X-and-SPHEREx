"""Which SPHEREx collections to search (NFR-3): the newest DR and the newest QR, wide and deep, discovered via TAP."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Final, Literal

from ..config import settings
from .http import ArchiveError, Http, get

logger = logging.getLogger(__name__)

TAP_SYNC_URL: Final = "https://irsa.ipac.caltech.edu/TAP/sync"
DISCOVERY_QUERY: Final = (
    "SELECT obs_collection, COUNT(*) AS n FROM ivoa.obscore "
    "WHERE obs_collection LIKE 'spherex%' GROUP BY obs_collection"
)
CACHE_TTL_S: Final = 6 * 3600.0
FAILURE_TTL_S: Final = 10 * 60.0
_NAME = re.compile(r"^spherex_(dr|qr)(\d*)(_deep)?$")

CollectionSource = Literal["tap", "fallback"]


def parse_collection_counts(text: str) -> dict[str, int]:
    return {row["obs_collection"]: int(row["n"]) for row in csv.DictReader(io.StringIO(text))}


def select_collections(counts: Mapping[str, int]) -> tuple[str, ...]:
    """Newest DR + newest QR, each wide and deep; `_cal`, `_cube` and empty collections are skipped."""
    versions: dict[str, tuple[str, int, bool]] = {}
    for name, n in counts.items():
        match = _NAME.match(name)
        if match is not None and n > 0:
            versions[name] = (match.group(1), int(match.group(2) or 0), match.group(3) is not None)
    newest = {kind: max(v for k, v, _ in versions.values() if k == kind) for kind, _, _ in versions.values()}
    selected = [name for name, (kind, version, _) in versions.items() if version == newest[kind]]
    return tuple(sorted(selected, key=lambda name: (versions[name][0], versions[name][2])))


class CollectionDiscovery:
    """Caches the discovered collections for 6 h; on failure serves the last good list or the configured fallback,
    and retries TAP after 10 min (a TAP query takes ~10 s, so it must not run per request)."""

    def __init__(
        self,
        fallback: Sequence[str] = settings.fallback_collections,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fallback = tuple(fallback)
        self._clock = clock
        self._lock = asyncio.Lock()
        self._collections: tuple[str, ...] = ()
        self._source: CollectionSource = "fallback"
        self._expires_at = float("-inf")

    @property
    def source(self) -> CollectionSource:
        return self._source

    @property
    def current(self) -> tuple[str, ...]:
        """The last known list without querying TAP: the fallback until the first discovery has finished."""
        return self._collections or self._fallback

    async def collections(self, http: Http) -> tuple[str, ...]:
        async with self._lock:
            if self._clock() < self._expires_at:
                return self._collections
            try:
                response = await get(http, TAP_SYNC_URL, {"QUERY": DISCOVERY_QUERY, "LANG": "ADQL", "FORMAT": "csv"})
                selected = select_collections(parse_collection_counts(response.text))
            except (ArchiveError, KeyError, ValueError) as exc:
                logger.warning("Collection discovery failed (%s); using %s", exc, self._collections or "fallback")
                if not self._collections:
                    self._collections, self._source = self._fallback, "fallback"
                self._expires_at = self._clock() + FAILURE_TTL_S
                return self._collections
            if selected:
                self._collections, self._source = selected, "tap"
                self._expires_at = self._clock() + CACHE_TTL_S
            else:
                logger.warning("TAP listed no usable SPHEREx collection; using the fallback")
                self._collections, self._source = self._fallback, "fallback"
                self._expires_at = self._clock() + FAILURE_TTL_S
            return self._collections
