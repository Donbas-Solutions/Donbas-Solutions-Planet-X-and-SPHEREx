"""Name resolution via SIMBAD TAP (FR-2): parsing, mirror fallback, cache. Recorded answers, no network."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.archive import http as archive_http
from app.archive.http import Http, make_http
from app.archive.resolve import ResolveError, Resolver, adql_for, parse_result

pytestmark = pytest.mark.anyio

HEADER = "main_id,ra,dec,pmra,pmdec,plx_value\n"
# Recorded from simbad.harvard.edu on 2026-11-14.
BARNARD_CSV = HEADER + '"NAME Barnard\'s star",269.4520769586187,4.693364966576667,-801.551,10362.394,546.9759\n'
RW_AUR_CSV = HEADER + '"V* RW Aur",76.95652603458333,30.401438173888888,7.23,-20.33,15.42\n'
CDS, HARVARD = "simbad.cds.unistra.fr", "simbad.harvard.edu"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive_http, "backoff_s", lambda attempt, response: 0.0)


def mock_http(handler: Handler) -> Http:
    return make_http(max_concurrency=2, transport=httpx.MockTransport(handler))


def cds_down_harvard(answer: str, calls: list[str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == CDS:
            return httpx.Response(404, text="<!doctype html><title>Page unavailable — CDS</title>")
        return httpx.Response(200, text=answer)

    return handler


def test_parse_strips_simbad_name_prefixes() -> None:
    result = parse_result(BARNARD_CSV, HARVARD)
    assert result is not None
    assert result.name == "Barnard's star"


def test_parse_keeps_simbad_units_and_epoch() -> None:
    result = parse_result(BARNARD_CSV, HARVARD)
    assert result is not None
    assert (result.ra, result.pmdec, result.parallax, result.ref_epoch) == pytest.approx(
        (269.4520769586187, 10362.394, 546.9759, 2000.0)
    )


def test_parse_missing_motion_is_none() -> None:
    result = parse_result(HEADER + '"Gal X",10.0,20.0,,,\n', HARVARD)
    assert result is not None
    assert result.pmra is None


def test_parse_no_rows_is_not_found() -> None:
    assert parse_result(HEADER, HARVARD) is None


def test_adql_escapes_quotes_and_collapses_spaces() -> None:
    assert adql_for("Barnard's   star").endswith("WHERE i.id = 'Barnard''s star'")


async def test_falls_back_to_the_mirror_and_prefers_it_afterwards() -> None:
    calls: list[str] = []
    resolver = Resolver()
    http = mock_http(cds_down_harvard(BARNARD_CSV, calls))
    async with http.client:
        first = await resolver.resolve(http, "Barnard's star")
        await resolver.resolve(http, "RW Aur")
    assert first is not None
    assert first.source == f"SIMBAD ({HARVARD})"
    assert calls == [CDS, HARVARD, HARVARD]


async def test_repeated_names_are_answered_from_the_cache() -> None:
    calls: list[str] = []
    resolver = Resolver(servers=(HARVARD,))
    http = mock_http(cds_down_harvard(RW_AUR_CSV, calls))
    async with http.client:
        await resolver.resolve(http, "RW Aur")
        again = await resolver.resolve(http, "rw  aur")
    assert again is not None
    assert len(calls) == 1


async def test_unknown_name_is_none() -> None:
    http = mock_http(cds_down_harvard(HEADER, []))
    async with http.client:
        assert await Resolver().resolve(http, "no such object") is None


async def test_all_servers_down_raises() -> None:
    http = mock_http(lambda request: httpx.Response(503))
    async with http.client:
        with pytest.raises(ResolveError):
            await Resolver().resolve(http, "R Dra")
