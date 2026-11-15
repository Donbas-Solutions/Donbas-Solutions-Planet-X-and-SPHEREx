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
_DASHES = str.maketrans(dict.fromkeys("‐‑‒–—−", "-"))
# Short survey designations as people write them ("WISE 0855-0714", challenge text); SIMBAD stores only the full ones.
_SHORT_DESIGNATION = re.compile(r"^(CWISE|WISEA?|2MASS[IWS]?)\s*J?\s*(\d{4})\s*([+-])\s*(\d{4})$", re.IGNORECASE)
# SIMBAD's catalogue prefixes per survey. A wildcard right after the survey name (`WISE% J0855…`) scans every
# WISE or 2MASS identifier: 2–15 s on simbad.harvard.edu, past the timeout; exact prefixes take 0.5 s (2026-11-15).
_SURVEY_PREFIXES: Final = {
    "CWISE": ("CWISE", "CWISEP"),
    "WISE": ("WISE", "WISEA", "WISEP", "WISEPA", "WISEPC", "WISEU"),
    "2MASS": ("2MASS", "2MASSI", "2MASSW", "2MASSS"),
}
_COLUMNS: Final = "b.oid, b.main_id, b.ra, b.dec, b.pmra, b.pmdec, b.plx_value"
_FROM: Final = "FROM basic AS b JOIN ident AS i ON b.oid = i.oidref"


class ResolveError(Exception):
    """No SIMBAD server could answer."""


def tap_url(server: str) -> str:
    return f"https://{server}/simbad/sim-tap/sync"


def normalize_name(name: str) -> str:
    return " ".join(name.translate(_DASHES).split())


def exact_adql(name: str) -> str:
    """SIMBAD matches `ident.id` ignoring case and repeated spaces, so the name is passed as typed."""
    literal = normalize_name(name).replace("'", "''")
    return f"SELECT TOP 1 {_COLUMNS} {_FROM} WHERE i.id = '{literal}'"


def designation_adql(name: str) -> str | None:
    """`WISE 0855-0714` → any `WISE…J0855…-0714…` identifier; `None` if the name is not a short designation."""
    match = _SHORT_DESIGNATION.match(normalize_name(name))
    if match is None:
        return None
    survey, ra_hhmm, sign, dec_ddmm = match.groups()
    root = next(r for r in _SURVEY_PREFIXES if survey.upper().startswith(r))
    where = " OR ".join(f"i.id LIKE '{p} J{ra_hhmm}%{sign}{dec_ddmm}%'" for p in _SURVEY_PREFIXES[root])
    # No TOP: on SIMBAD `DISTINCT TOP n` with LIKE took 35–45 s, plain DISTINCT 1.5–2 s (2026-11-14).
    return f"SELECT DISTINCT {_COLUMNS} {_FROM} WHERE {where}"


def _number(value: str) -> float | None:
    return float(value) if value.strip() else None


def parse_result(text: str, server: str, *, unique: bool = False) -> ResolveResult | None:
    """SIMBAD `basic` positions are ICRS at epoch J2000; `pmra` already includes cos(dec).

    With `unique`, more than one object (an ambiguous short designation) counts as not found.
    """
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or (unique and len(rows) > 1):
        return None
    row = rows[0]
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


class Resolver:
    """Tries the server that answered last first, and remembers recent answers (presets resolve again and again)."""

    def __init__(self, servers: Sequence[str] = SIMBAD_SERVERS, timeout_s: float = SERVER_TIMEOUT_S) -> None:
        self._servers = list(servers)
        self._timeout_s = timeout_s
        self._cache: OrderedDict[str, ResolveResult | None] = OrderedDict()

    async def resolve(self, http: Http, name: str) -> ResolveResult | None:
        """The object, `None` if SIMBAD does not know the name; `ResolveError` if no server answers."""
        key = normalize_name(name).lower()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        result = await self._answer(http, exact_adql(name), unique=False)
        if result is None and (adql := designation_adql(name)) is not None:
            result = await self._answer(http, adql, unique=True)
        self._cache[key] = result
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return result

    async def _answer(self, http: Http, adql: str, *, unique: bool) -> ResolveResult | None:
        params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": adql}
        errors: list[str] = []
        for server in list(self._servers):
            try:
                async with asyncio.timeout(self._timeout_s):
                    response = await get(http, tap_url(server), params)
                result = parse_result(response.text, server, unique=unique)
            except (ArchiveError, TimeoutError, KeyError, ValueError) as exc:
                logger.warning("SIMBAD %s failed: %s", server, exc or type(exc).__name__)
                errors.append(server)
                continue
            if server != self._servers[0]:
                self._servers.remove(server)
                self._servers.insert(0, server)
            return result
        raise ResolveError(f"No SIMBAD server answered ({', '.join(errors)})")
