"""Gaia DR3 stars of a field, propagated to a frame's epoch (FR-18), from the first TAP mirror that answers."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

import numpy as np

from ..astrometry import FloatArray, positions_at
from ..grid import SPHEREX_PIXSCALE_ARCSEC
from ..models import GaiaStar
from .http import ArchiveError, Http, get

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GaiaServer:
    name: str
    url: str
    table: str


# ESA's archive, its Heidelberg mirror and VizieR did not answer on 2026-11-15 while MAST and GAVO did (10′ field:
# 1.3 s and 0.6 s). GAVO's `dr3lite` timed out on a 30′ field at the Galactic centre, MAST took 3.5 s.
GAIA_SERVERS: Final = (
    GaiaServer("MAST", "https://mast.stsci.edu/vo-tap/api/v0.1/gaiadr3/sync", "dbo.gaia_source"),
    GaiaServer("GAVO", "https://dc.g-vo.org/tap/sync", "gaia.dr3lite"),
    GaiaServer("ESA", "https://gea.esac.esa.int/tap-server/tap/sync", "gaiadr3.gaia_source"),
)
GAIA_EPOCH: Final = 2016.0
SERVER_TIMEOUT_S: Final = 15.0
DOWN_TTL_S: Final = 60.0
CACHE_SIZE: Final = 64
MAX_STARS: Final = 500
G_LIMIT_MAG: Final = 19.0
# Barnard's Star, the fastest star in the sky (10.4″/yr), is 2.4′ away from its Gaia position by 2030.
PM_MARGIN_ARCMIN: Final = 2.5

FieldKey = tuple[float, float, float]


class GaiaError(Exception):
    """No Gaia server could answer."""


@dataclass(frozen=True)
class GaiaSource:
    """A Gaia DR3 row: ICRS position at epoch 2016.0; `pmra_masyr` includes cos(dec)."""

    source_id: str
    ra_deg: float
    dec_deg: float
    pmra_masyr: float | None
    pmdec_masyr: float | None
    g_mag: float | None


def query_radius_deg(fov_arcmin: float) -> float:
    """The circle around the square field, widened so a fast star inside the field at any epoch is caught."""
    return (fov_arcmin / 2 * math.sqrt(2) + PM_MARGIN_ARCMIN) / 60


def field_adql(table: str, ra_deg: float, dec_deg: float, radius_deg: float) -> str:
    """The brightest stars first: a crowded field is cut at `MAX_STARS`. The G limit also drops rows without G,
    which sort first on MAST."""
    circle = f"CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.5f})"
    return (
        f"SELECT TOP {MAX_STARS} source_id, ra, dec, pmra, pmdec, phot_g_mean_mag FROM {table} "  # noqa: S608 - only our table names and formatted numbers
        f"WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), {circle}) "
        f"AND phot_g_mean_mag <= {G_LIMIT_MAG} ORDER BY phot_g_mean_mag"
    )


def _number(value: str) -> float | None:
    return float(value) if value.strip() else None


def parse_sources(text: str) -> tuple[GaiaSource, ...]:
    """Rows of the TAP CSV answer; a missing column (an error document) raises `KeyError`."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "source_id" not in reader.fieldnames:
        raise KeyError("source_id")
    return tuple(
        GaiaSource(
            source_id=row["source_id"].strip(),
            ra_deg=float(row["ra"]),
            dec_deg=float(row["dec"]),
            pmra_masyr=_number(row["pmra"]),
            pmdec_masyr=_number(row["pmdec"]),
            g_mag=_number(row["phot_g_mean_mag"]),
        )
        for row in reader
    )


def _tangent_offsets_arcmin(
    ra_deg: FloatArray, dec_deg: FloatArray, center_ra_deg: float, center_dec_deg: float
) -> tuple[FloatArray, FloatArray]:
    """Gnomonic (TAN) offsets east and north of the field centre, the projection of the frame grid."""
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    ra0, dec0 = math.radians(center_ra_deg), math.radians(center_dec_deg)
    cos_c = math.sin(dec0) * np.sin(dec) + math.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    east = np.cos(dec) * np.sin(ra - ra0) / cos_c
    north = (math.cos(dec0) * np.sin(dec) - math.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / cos_c
    return np.degrees(east) * 60, np.degrees(north) * 60


def stars_at(
    sources: Sequence[GaiaSource], ra_deg: float, dec_deg: float, fov_arcmin: float, mjd: float
) -> list[GaiaStar]:
    """Stars inside the square field at `mjd`, in the order given. Stars without a proper motion (two-parameter
    solutions) stay at their 2016.0 position."""
    if not sources:
        return []
    ra, dec = positions_at(
        np.array([s.ra_deg for s in sources]),
        np.array([s.dec_deg for s in sources]),
        np.array([s.pmra_masyr or 0.0 for s in sources]),
        np.array([s.pmdec_masyr or 0.0 for s in sources]),
        GAIA_EPOCH,
        mjd,
    )
    east, north = _tangent_offsets_arcmin(ra, dec, ra_deg, dec_deg)
    # The odd-sized grid is up to a pixel wider than the requested field.
    half_arcmin = fov_arcmin / 2 + SPHEREX_PIXSCALE_ARCSEC / 60
    inside = (np.abs(east) <= half_arcmin) & (np.abs(north) <= half_arcmin)
    return [
        GaiaStar(
            source_id=source.source_id,
            ra=float(ra[i]),
            dec=float(dec[i]),
            g=source.g_mag,
            pmra=source.pmra_masyr,
            pmdec=source.pmdec_masyr,
        )
        for i, source in enumerate(sources)
        if inside[i]
    ]


class GaiaCatalog:
    """Remembers the stars of recent fields (every frame of a sequence asks for the same field) and tries the server
    that answered last first. Concurrent requests for one field share one query; after every server has failed,
    Gaia counts as down for a minute, so the frames of a sequence do not each wait for the timeouts."""

    def __init__(
        self,
        servers: Sequence[GaiaServer] = GAIA_SERVERS,
        timeout_s: float = SERVER_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._servers = list(servers)
        self._timeout_s = timeout_s
        self._clock = clock
        self._cache: OrderedDict[FieldKey, tuple[GaiaSource, ...]] = OrderedDict()
        self._queries: dict[FieldKey, asyncio.Task[tuple[GaiaSource, ...]]] = {}
        self._down_until = float("-inf")

    async def sources(self, http: Http, ra_deg: float, dec_deg: float, fov_arcmin: float) -> tuple[GaiaSource, ...]:
        """Gaia DR3 rows (epoch 2016.0) around the field; `GaiaError` if no server answers."""
        key = (round(ra_deg, 4), round(dec_deg, 4), round(fov_arcmin, 1))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if self._clock() < self._down_until:
            raise GaiaError("Gaia was unreachable a moment ago")
        query = self._queries.get(key)
        if query is None:
            query = asyncio.create_task(self._fetch(http, key), name="gaia-field")
            self._queries[key] = query
            query.add_done_callback(lambda done: self._query_done(key, done))
        return await asyncio.shield(query)

    async def aclose(self) -> None:
        queries = list(self._queries.values())
        for query in queries:
            query.cancel()
        await asyncio.gather(*queries, return_exceptions=True)

    async def _fetch(self, http: Http, key: FieldKey) -> tuple[GaiaSource, ...]:
        ra_deg, dec_deg, fov_arcmin = key
        radius_deg = query_radius_deg(fov_arcmin)
        failed: list[str] = []
        for server in list(self._servers):
            params = {
                "REQUEST": "doQuery",
                "LANG": "ADQL",
                "FORMAT": "csv",
                "QUERY": field_adql(server.table, ra_deg, dec_deg, radius_deg),
            }
            try:
                async with asyncio.timeout(self._timeout_s):
                    response = await get(http, server.url, params)
                sources = parse_sources(response.text)
            except (ArchiveError, TimeoutError, KeyError, ValueError) as exc:
                logger.warning("Gaia %s failed: %s", server.name, exc or type(exc).__name__)
                failed.append(server.name)
                continue
            if server != self._servers[0]:
                self._servers.remove(server)
                self._servers.insert(0, server)
            self._cache[key] = sources
            if len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
            return sources
        self._down_until = self._clock() + DOWN_TTL_S
        raise GaiaError(f"No Gaia server answered ({', '.join(failed)})")

    def _query_done(self, key: FieldKey, query: asyncio.Task[tuple[GaiaSource, ...]]) -> None:
        self._queries.pop(key, None)
        if not query.cancelled():
            # Every waiter may have gone (client disconnect): mark the error as seen.
            query.exception()
