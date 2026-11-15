"""Gaia DR3 overlay (FR-18): query, parsing, propagation to a frame epoch, mirrors, cache. No network."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.archive import http as archive_http
from app.archive.gaia import (
    DOWN_TTL_S,
    GaiaCatalog,
    GaiaError,
    GaiaServer,
    GaiaSource,
    field_adql,
    parse_sources,
    query_radius_deg,
    stars_at,
)
from app.archive.http import Http, make_http
from app.astrometry import position_at
from app.domain import Target

pytestmark = pytest.mark.anyio

# Recorded from MAST on 2026-11-15: the 40 brightest stars of a 4′ field at Barnard's Star (prebaked grid centre).
BARNARD_FIELD_CSV = (Path(__file__).parent / "fixtures" / "gaia" / "barnard_fov4.csv").read_text(encoding="utf-8")
HEADER = "source_id,ra,dec,pmra,pmdec,phot_g_mean_mag\n"
BARNARD_ID = "4472832130942575872"
CENTER_RA, CENTER_DEC, FOV = 269.4462, 4.7687, 4.0
FIRST_VISIT_MJD, LAST_VISIT_MJD = 60923.7664, 61275.1145
SIMBAD_BARNARD = Target(ra_deg=269.4520769586187, dec_deg=4.693364966576667, pmra_masyr=-801.551, pmdec_masyr=10362.394)
MJD_2016, MJD_2026 = 57388.5, 61041.0
FIRST = GaiaServer("first", "https://first.example/tap/sync", "one.gaia_source")
SECOND = GaiaServer("second", "https://second.example/tap/sync", "two.gaia_source")

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive_http, "backoff_s", lambda attempt, response: 0.0)


def mock_http(handler: Handler) -> Http:
    return make_http(max_concurrency=2, transport=httpx.MockTransport(handler))


def recording(calls: list[str], answer: Callable[[str], httpx.Response]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return answer(request.url.host)

    return handler


def barnard(mjd: float) -> tuple[float, float]:
    stars = stars_at(parse_sources(BARNARD_FIELD_CSV), CENTER_RA, CENTER_DEC, FOV, mjd)
    star = next(s for s in stars if s.source_id == BARNARD_ID)
    return star.ra, star.dec


def source(ra_deg: float, dec_deg: float, pmdec_masyr: float | None = None) -> GaiaSource:
    pmra_masyr = None if pmdec_masyr is None else 0.0
    return GaiaSource(
        source_id="1", ra_deg=ra_deg, dec_deg=dec_deg, pmra_masyr=pmra_masyr, pmdec_masyr=pmdec_masyr, g_mag=12.0
    )


def test_query_circle_covers_the_square_field_and_fast_stars() -> None:
    assert query_radius_deg(10.0) == pytest.approx((5 * math.sqrt(2) + 2.5) / 60)


def test_adql_asks_for_the_brightest_stars_of_the_circle() -> None:
    adql = field_adql("dbo.gaia_source", 269.4462, 4.7687, 0.0888)
    assert adql.startswith("SELECT TOP 500 source_id, ra, dec, pmra, pmdec, phot_g_mean_mag FROM dbo.gaia_source ")
    assert "CIRCLE('ICRS', 269.446200, 4.768700, 0.08880)" in adql
    assert adql.endswith("AND phot_g_mean_mag <= 19.0 ORDER BY phot_g_mean_mag")


def test_parse_keeps_the_source_id_as_text() -> None:
    sources = parse_sources(BARNARD_FIELD_CSV)
    assert len(sources) == 40
    assert sources[0].source_id == BARNARD_ID


def test_parse_reads_gaia_units() -> None:
    star = parse_sources(BARNARD_FIELD_CSV)[0]
    assert (star.ra_deg, star.dec_deg, star.pmra_masyr, star.pmdec_masyr, star.g_mag) == pytest.approx(
        (269.44850252543836, 4.739420051112412, -801.5509783684709, 10362.394206546573, 8.193974494934082)
    )


def test_parse_missing_motion_is_none() -> None:
    (star,) = parse_sources(HEADER + "7,10.0,20.0,,,18.5\n")
    assert (star.pmra_masyr, star.pmdec_masyr) == (None, None)


def test_parse_empty_field_is_no_stars() -> None:
    assert parse_sources(HEADER) == ()


def test_parse_rejects_an_error_document() -> None:
    with pytest.raises(KeyError):
        parse_sources('<?xml version="1.0"?>\n<VOTABLE><INFO name="QUERY_STATUS" value="ERROR"/></VOTABLE>\n')


def test_barnard_lands_on_its_simbad_position() -> None:
    ra_deg, dec_deg = barnard(LAST_VISIT_MJD)
    simbad_ra, simbad_dec = position_at(SIMBAD_BARNARD, LAST_VISIT_MJD)
    assert (dec_deg - simbad_dec) * 3600 == pytest.approx(0.0, abs=0.05)
    assert (ra_deg - simbad_ra) * 3600 * math.cos(math.radians(dec_deg)) == pytest.approx(0.0, abs=0.05)


def test_gaia_marker_moves_with_barnard_between_visits() -> None:
    (first_ra, first_dec), (last_ra, last_dec) = barnard(FIRST_VISIT_MJD), barnard(LAST_VISIT_MJD)
    years = (LAST_VISIT_MJD - FIRST_VISIT_MJD) / 365.25
    assert (last_dec - first_dec) * 3600 == pytest.approx(10.3624 * years, abs=0.01)
    assert (last_ra - first_ra) * 3600 * math.cos(math.radians(last_dec)) == pytest.approx(-0.8016 * years, abs=0.01)


def test_stars_keep_the_catalog_order() -> None:
    stars = stars_at(parse_sources(BARNARD_FIELD_CSV), CENTER_RA, CENTER_DEC, FOV, LAST_VISIT_MJD)
    magnitudes = [s.g for s in stars if s.g is not None]
    assert magnitudes == sorted(magnitudes)


def test_star_without_proper_motion_stays_put() -> None:
    (star,) = stars_at([source(10.0, 20.0)], 10.0, 20.0, 4.0, MJD_2026)
    assert (star.ra, star.dec) == pytest.approx((10.0, 20.0), abs=1e-9)
    assert star.pmra is None


@pytest.mark.parametrize(
    ("east_arcmin", "north_arcmin", "is_inside"),
    [(0.0, 0.0, True), (1.9, 1.9, True), (-1.9, -1.9, True), (2.5, 0.0, False), (0.0, -2.5, False)],
)
def test_only_stars_inside_the_square_field_are_returned(
    east_arcmin: float, north_arcmin: float, *, is_inside: bool
) -> None:
    ra_deg = 10.0 + east_arcmin / 60 / math.cos(math.radians(20.0))
    stars = stars_at([source(ra_deg, 20.0 + north_arcmin / 60)], 10.0, 20.0, 4.0, MJD_2016)
    assert (len(stars) == 1) is is_inside


def test_fast_star_that_moved_into_the_field_is_returned() -> None:
    south_of_the_field = source(10.0, 20.0 - 2.5 / 60, pmdec_masyr=10000.0)
    assert stars_at([south_of_the_field], 10.0, 20.0, 2.0, MJD_2016) == []
    (star,) = stars_at([south_of_the_field], 10.0, 20.0, 2.0, MJD_2026)
    assert (star.dec - 20.0) * 60 == pytest.approx(-2.5 + 10.0 * (MJD_2026 - MJD_2016) / 365.25 / 60, abs=0.01)


def test_no_sources_is_no_stars() -> None:
    assert stars_at([], 10.0, 20.0, 4.0, MJD_2026) == []


async def test_catalog_falls_back_to_the_next_server_and_prefers_it_afterwards() -> None:
    calls: list[str] = []
    answer = lambda host: httpx.Response(404) if host == "first.example" else httpx.Response(200, text=HEADER)  # noqa: E731
    catalog = GaiaCatalog(servers=(FIRST, SECOND))
    http = mock_http(recording(calls, answer))
    async with http.client:
        await catalog.sources(http, 10.0, 20.0, 4.0)
        await catalog.sources(http, 30.0, 40.0, 4.0)
    assert calls == ["first.example", "second.example", "second.example"]


async def test_catalog_asks_each_server_for_its_own_table() -> None:
    queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(request.url.params["QUERY"])
        return httpx.Response(200, text=BARNARD_FIELD_CSV)

    catalog = GaiaCatalog(servers=(SECOND,))
    http = mock_http(handler)
    async with http.client:
        sources = await catalog.sources(http, CENTER_RA, CENTER_DEC, FOV)
    assert len(sources) == 40
    assert "FROM two.gaia_source WHERE" in queries[0]


async def test_catalog_remembers_a_field() -> None:
    calls: list[str] = []
    catalog = GaiaCatalog(servers=(FIRST,))
    http = mock_http(recording(calls, lambda host: httpx.Response(200, text=BARNARD_FIELD_CSV)))
    async with http.client:
        first = await catalog.sources(http, CENTER_RA, CENTER_DEC, FOV)
        again = await catalog.sources(http, CENTER_RA, CENTER_DEC, FOV)
    assert again is first
    assert len(calls) == 1


async def test_frames_of_one_sequence_share_one_query() -> None:
    calls: list[str] = []
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        await release.wait()
        return httpx.Response(200, text=BARNARD_FIELD_CSV)

    catalog = GaiaCatalog(servers=(FIRST,))
    http = make_http(max_concurrency=2, transport=httpx.MockTransport(handler))
    async with http.client, asyncio.timeout(5), asyncio.TaskGroup() as group:
        waiting = [group.create_task(catalog.sources(http, CENTER_RA, CENTER_DEC, FOV)) for _ in range(5)]
        await asyncio.sleep(0)
        release.set()
    assert all(len(task.result()) == 40 for task in waiting)
    assert len(calls) == 1


async def test_catalog_error_document_counts_as_a_failed_server() -> None:
    catalog = GaiaCatalog(servers=(FIRST,))
    http = mock_http(lambda request: httpx.Response(200, text="<VOTABLE/>"))
    async with http.client:
        with pytest.raises(GaiaError):
            await catalog.sources(http, 10.0, 20.0, 4.0)


async def test_hung_server_is_given_up_for_the_next_one() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "first.example":
            await asyncio.sleep(10)
        return httpx.Response(200, text=HEADER)

    catalog = GaiaCatalog(servers=(FIRST, SECOND), timeout_s=0.05)
    http = make_http(max_concurrency=2, transport=httpx.MockTransport(handler))
    async with http.client, asyncio.timeout(5):
        assert await catalog.sources(http, 10.0, 20.0, 4.0) == ()


async def test_gaia_outage_is_not_retried_for_every_frame() -> None:
    calls: list[str] = []
    now = 0.0
    catalog = GaiaCatalog(servers=(FIRST, SECOND), clock=lambda: now)
    http = mock_http(recording(calls, lambda host: httpx.Response(404)))
    async with http.client:
        with pytest.raises(GaiaError):
            await catalog.sources(http, 10.0, 20.0, 4.0)
        with pytest.raises(GaiaError):
            await catalog.sources(http, 10.0, 20.0, 4.0)
        assert len(calls) == 2
        now = DOWN_TTL_S + 1
        with pytest.raises(GaiaError):
            await catalog.sources(http, 10.0, 20.0, 4.0)
    assert len(calls) == 4


async def test_aclose_cancels_a_running_query() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, text=HEADER)

    catalog = GaiaCatalog(servers=(FIRST,))
    http = make_http(max_concurrency=2, transport=httpx.MockTransport(handler))
    async with http.client, asyncio.timeout(5):
        waiting = asyncio.create_task(catalog.sources(http, 10.0, 20.0, 4.0))
        await asyncio.sleep(0.01)
        await catalog.aclose()
        with pytest.raises(asyncio.CancelledError):
            await waiting
