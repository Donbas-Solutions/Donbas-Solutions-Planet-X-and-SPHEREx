"""Object names → position and proper motion via SIMBAD TAP (FR-2), with the Harvard mirror as fallback."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
from collections import OrderedDict
from collections.abc import Sequence
from typing import Final

from ..models import ResolveResult
from .http import ArchiveError, Http, get

logger = logging.getLogger(__name__)

# The Strasbourg server answered 404 for every query on 2026-11-14 while the Harvard mirror worked.
SIMBAD_SERVERS: Final = ("simbad.cds.unistra.fr", "simbad.harvard.edu")
SERVER_TIMEOUT_S: Final = 15.0
CACHE_SIZE: Final = 256
SIMBAD_EPOCH: Final = 2000.0
_DISPLAY_PREFIX = re.compile(r"^(NAME|V\*|\*\*?)\s+")


class ResolveError(Exception):
    """No SIMBAD server could answer."""


def tap_url(server: str) -> str:
    return f"https://{server}/simbad/sim-tap/sync"


def adql_for(name: str) -> str:
    """SIMBAD matches `ident.id` ignoring case and repeated spaces, so the name is passed as typed."""
    literal = " ".join(name.split()).replace("'", "''")
    return (
        "SELECT TOP 1 b.main_id, b.ra, b.dec, b.pmra, b.pmdec, b.plx_value "  # noqa: S608 - ADQL has no bind params; quotes doubled
        "FROM basic AS b JOIN ident AS i ON b.oid = i.oidref "
        f"WHERE i.id = '{literal}'"
    )


def _number(value: str) -> float | None:
    return float(value) if value.strip() else None


def parse_result(text: str, server: str) -> ResolveResult | None:
    """SIMBAD `basic` positions are ICRS at epoch J2000; `pmra` already includes cos(dec)."""
    for row in csv.DictReader(io.StringIO(text)):
        ra, dec = _number(row["ra"]), _number(row["dec"])
        if ra is None or dec is None:
            return None
        return ResolveResult(
            name=_DISPLAY_PREFIX.sub("", row["main_id"]).strip(),
            ra=ra,
            dec=dec,
            ref_epoch=SIMBAD_EPOCH,
            pmra=_number(row["pmra"]),
            pmdec=_number(row["pmdec"]),
            parallax=_number(row["plx_value"]),
            source=f"SIMBAD ({server})",
        )
    return None


class Resolver:
    """Tries the server that answered last first, and remembers recent answers (presets resolve again and again)."""

    def __init__(self, servers: Sequence[str] = SIMBAD_SERVERS, timeout_s: float = SERVER_TIMEOUT_S) -> None:
        self._servers = list(servers)
        self._timeout_s = timeout_s
        self._cache: OrderedDict[str, ResolveResult | None] = OrderedDict()

    async def resolve(self, http: Http, name: str) -> ResolveResult | None:
        """The object, `None` if SIMBAD does not know the name; `ResolveError` if no server answers."""
        key = " ".join(name.lower().split())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        result = await self._query(http, name)
        self._cache[key] = result
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return result

    async def _query(self, http: Http, name: str) -> ResolveResult | None:
        params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql_for(name)}
        errors: list[str] = []
        for server in list(self._servers):
            try:
                async with asyncio.timeout(self._timeout_s):
                    response = await get(http, tap_url(server), params)
                result = parse_result(response.text, server)
            except (ArchiveError, TimeoutError, KeyError, ValueError) as exc:
                logger.warning("SIMBAD %s failed: %s", server, exc or type(exc).__name__)
                errors.append(server)
                continue
            if server != self._servers[0]:
                self._servers.remove(server)
                self._servers.insert(0, server)
            return result
        raise ResolveError(f"No SIMBAD server answered ({', '.join(errors)})")
