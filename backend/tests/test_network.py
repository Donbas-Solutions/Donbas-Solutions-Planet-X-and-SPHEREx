"""Live IRSA checks for the naive fetcher. Deselected by default; run with: uv run pytest -m network"""

from __future__ import annotations

from pathlib import Path

import pytest

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
