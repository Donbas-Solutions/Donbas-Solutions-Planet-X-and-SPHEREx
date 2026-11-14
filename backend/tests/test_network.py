"""Live IRSA checks for the naive and the async fetchers. Deselected by default; run with: uv run pytest -m network"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.archive.collections import CollectionDiscovery
from app.archive.fetch import fetch_one as async_fetch_one
from app.archive.fetch import query_exposures as async_query_exposures
from app.archive.http import make_http
from app.archive.naive import fetch_one, make_client, query_exposures
from app.archive.visits import group_visits
from app.astrometry import position_at
from app.config import configure_ssl, settings
from app.domain import Target

pytestmark = pytest.mark.network

BARNARD = Target(ra_deg=269.452077, dec_deg=4.693365, pmra_masyr=-801.551, pmdec_masyr=10362.394)


def test_sia_lists_barnard_visits() -> None:
    configure_ssl()
    with make_client() as client:
        exposures = query_exposures(client, BARNARD, settings.fallback_collections)
    assert len(exposures) >= 363
    assert len(group_visits(exposures)) >= 3


def test_one_cutout_downloads_and_loads(tmp_path: Path) -> None:
    configure_ssl()
    with make_client() as client:
        exposures = query_exposures(client, BARNARD, ("spherex_qr3",))
        meta = exposures[0]
        center = position_at(BARNARD, meta.mjd_mid)
        cutout = fetch_one(client, meta, "v1", center, 0.05, tmp_path)
    # Near a detector edge IRSA truncates the cutout instead of padding it, so only consistency is checked.
    assert cutout.image.size > 0
    assert cutout.flags.shape == cutout.image.shape
    assert cutout.meta.detector == meta.detector


@pytest.mark.anyio
async def test_async_discovery_and_query_find_barnard() -> None:
    configure_ssl()
    discovery = CollectionDiscovery()
    http = make_http()
    async with http.client:
        collections = await discovery.collections(http)
        exposures = await async_query_exposures(http, BARNARD, collections)
    assert discovery.source == "tap"
    assert "spherex_dr1" in collections
    assert len(exposures) >= 363
    assert len(group_visits(exposures)) >= 3


@pytest.mark.anyio
async def test_s3_and_ibe_range_reads_give_the_same_window(tmp_path: Path) -> None:
    configure_ssl()
    http = make_http()
    async with http.client:
        exposures = await async_query_exposures(http, BARNARD, ("spherex_qr3",))
        meta = exposures[len(exposures) // 2]
        center = position_at(BARNARD, meta.mjd_mid)
        from_s3 = await async_fetch_one(http, meta, "v1", center, 0.05, tmp_path / "s3", sources=("s3",))
        from_ibe = await async_fetch_one(http, meta, "v1", center, 0.05, tmp_path / "ibe", sources=("ibe",))
    for name in ("image", "variance", "zodi", "flags", "wavelength_um"):
        np.testing.assert_array_equal(getattr(from_s3, name), getattr(from_ibe, name), err_msg=name)
