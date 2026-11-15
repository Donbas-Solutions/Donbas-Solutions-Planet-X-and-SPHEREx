"""Async archive layer (A1): HTTP retries, collection discovery, SIA queries. Recorded responses, no network."""

from __future__ import annotations

import asyncio
import csv
import gzip
import io
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.archive import http as archive_http
from app.archive.collections import (
    CACHE_TTL_S,
    FAILURE_TTL_S,
    CollectionDiscovery,
    parse_collection_counts,
    select_collections,
)
from app.archive.fetch import query_exposures
from app.archive.http import ArchiveError, Http, backoff_s, get, make_http
from app.archive.sia import CACHE_TTL_S as SIA_CACHE_TTL_S
from app.archive.sia import SiaCache
from app.domain import Target

pytestmark = pytest.mark.anyio

FIXTURES = Path(__file__).parent / "fixtures"
TAP_CSV = (FIXTURES / "tap_collections.csv").read_text(encoding="utf-8")
BARNARD = Target(ra_deg=269.452077, dec_deg=4.693365, pmra_masyr=-801.551, pmdec_masyr=10362.394)
FALLBACK = ("spherex_dr1", "spherex_qr3")
EMPTY_SIA = "obs_collection,obs_id,access_url,t_min,t_max,energy_bandpassname,em_min,em_max\n"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive_http, "backoff_s", lambda attempt, response: 0.0)


def mock_http(handler: Handler) -> Http:
    return make_http(max_concurrency=2, transport=httpx.MockTransport(handler))


def sia_rows_by_collection(target_id: str) -> dict[str, str]:
    text = gzip.decompress((FIXTURES / "sia" / f"{target_id}.csv.gz").read_bytes()).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    by_collection: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_collection.setdefault(row["obs_collection"], []).append(row)
    out: dict[str, str] = {}
    for collection, items in by_collection.items():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(items)
        out[collection] = buffer.getvalue()
    return out


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_backoff_honours_retry_after() -> None:
    response = httpx.Response(503, headers={"Retry-After": "5"})
    assert backoff_s(1, response) == 5.0


def test_backoff_is_capped() -> None:
    assert backoff_s(10, None) <= archive_http.MAX_BACKOFF_S * 1.5


async def test_get_retries_on_503_then_succeeds() -> None:
    statuses = iter([503, 503, 200])
    calls = Counter[str]()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(next(statuses), text="ok")

    http = mock_http(handler)
    async with http.client:
        response = await get(http, "https://irsa.example/SIA")
    assert response.text == "ok"
    assert calls["n"] == 3


async def test_get_does_not_retry_404() -> None:
    calls = Counter[str]()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404)

    http = mock_http(handler)
    async with http.client:
        with pytest.raises(ArchiveError) as info:
            await get(http, "https://irsa.example/missing")
    assert info.value.status == 404
    assert calls["n"] == 1


async def test_get_gives_up_after_all_attempts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    http = mock_http(handler)
    async with http.client:
        with pytest.raises(ArchiveError, match="unreachable"):
            await get(http, "https://irsa.example/SIA")


def test_select_newest_dr_and_qr_wide_and_deep() -> None:
    selected = select_collections(parse_collection_counts(TAP_CSV))
    assert selected == ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep")


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"spherex_qr2": 5, "spherex_qr3": 5, "spherex_qr3_deep": 1}, ("spherex_qr3", "spherex_qr3_deep")),
        ({"spherex_dr1": 5, "spherex_dr2": 5, "spherex_dr2_cal": 9}, ("spherex_dr2",)),
        ({"spherex_qr4": 0, "spherex_qr3": 7}, ("spherex_qr3",)),
        ({"spherex_qr": 3}, ("spherex_qr",)),
        ({"spherex_dr1_cube": 3, "other": 1}, ()),
    ],
)
def test_select_skips_old_empty_and_special_collections(counts: dict[str, int], expected: tuple[str, ...]) -> None:
    assert select_collections(counts) == expected


async def test_discovery_is_cached_for_six_hours() -> None:
    calls = Counter[str]()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["tap"] += 1
        return httpx.Response(200, text=TAP_CSV)

    clock = FakeClock()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=clock)
    http = mock_http(handler)
    async with http.client:
        first = await discovery.collections(http)
        clock.now = CACHE_TTL_S - 1
        await discovery.collections(http)
        assert calls["tap"] == 1
        clock.now = CACHE_TTL_S + 1
        await discovery.collections(http)
    assert calls["tap"] == 2
    assert first == ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep")
    assert discovery.source == "tap"


async def test_discovery_falls_back_when_tap_fails() -> None:
    http = mock_http(lambda request: httpx.Response(500))
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=FakeClock())
    async with http.client:
        assert await discovery.collections(http) == FALLBACK
    assert discovery.source == "fallback"


async def test_discovery_keeps_last_good_list_when_tap_fails_later() -> None:
    responses = iter([httpx.Response(200, text=TAP_CSV)] + [httpx.Response(503)] * archive_http.ATTEMPTS)
    clock = FakeClock()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=clock)
    http = mock_http(lambda request: next(responses))
    async with http.client:
        good = await discovery.collections(http)
        clock.now = CACHE_TTL_S + 1
        assert await discovery.collections(http) == good
    assert discovery.source == "tap"


async def test_discovery_retries_tap_soon_after_a_failure() -> None:
    calls = Counter[str]()

    def handler(request: httpx.Request) -> httpx.Response:
        calls["tap"] += 1
        return httpx.Response(404)

    clock = FakeClock()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=clock)
    http = mock_http(handler)
    async with http.client:
        await discovery.collections(http)
        await discovery.collections(http)
        clock.now = FAILURE_TTL_S + 1
        await discovery.collections(http)
    assert calls["tap"] == 2


def tap_answering_after(release: asyncio.Event, calls: Counter[str]) -> Http:
    async def handler(request: httpx.Request) -> httpx.Response:
        calls["tap"] += 1
        await release.wait()
        return httpx.Response(200, text=TAP_CSV)

    return make_http(max_concurrency=2, transport=httpx.MockTransport(handler))


async def test_hung_tap_is_waited_out_once_not_by_every_caller() -> None:
    calls = Counter[str]()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=FakeClock())
    http = tap_answering_after(asyncio.Event(), calls)
    async with http.client:
        assert await discovery.collections(http, wait_s=0.05) == FALLBACK
        async with asyncio.timeout(1):
            assert await discovery.collections(http, wait_s=30) == FALLBACK
        async with asyncio.timeout(1):
            await discovery.aclose()
    assert calls["tap"] == 1


async def test_late_tap_answer_is_kept_after_callers_gave_up() -> None:
    calls = Counter[str]()
    release = asyncio.Event()
    clock = FakeClock()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=clock)
    http = tap_answering_after(release, calls)
    async with http.client:
        assert await discovery.collections(http, wait_s=0.05) == FALLBACK
        release.set()
        clock.now = FAILURE_TTL_S + 1
        async with asyncio.timeout(1):
            latest = await discovery.collections(http)
        assert latest == (
            "spherex_dr1",
            "spherex_dr1_deep",
            "spherex_qr3",
            "spherex_qr3_deep",
        )
    assert calls["tap"] == 1


async def test_hung_tap_is_waited_for_again_after_the_failure_ttl() -> None:
    calls = Counter[str]()
    clock = FakeClock()
    discovery = CollectionDiscovery(fallback=FALLBACK, clock=clock)
    http = tap_answering_after(asyncio.Event(), calls)
    async with http.client:
        await discovery.collections(http, wait_s=0.05)
        clock.now = FAILURE_TTL_S + 1
        loop = asyncio.get_running_loop()
        started = loop.time()
        await discovery.collections(http, wait_s=0.2)
        waited_s = loop.time() - started
        await discovery.aclose()
    assert waited_s >= 0.15
    assert calls["tap"] == 1


async def test_query_exposures_merges_collections_like_the_recorded_coverage() -> None:
    by_collection = sia_rows_by_collection("barnard")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        collection = request.url.params["COLLECTION"]
        seen.append(collection)
        header = next(iter(by_collection.values())).splitlines()[0] + "\n"
        return httpx.Response(200, text=by_collection.get(collection, header))

    http = mock_http(handler)
    async with http.client:
        exposures = await query_exposures(http, BARNARD, ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3"))
    assert len(exposures) == 363
    assert sorted(seen) == ["spherex_dr1", "spherex_dr1_deep", "spherex_qr3"]
    assert [e.mjd_start for e in exposures] == sorted(e.mjd_start for e in exposures)


async def test_query_exposures_searches_at_the_propagated_position() -> None:
    positions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        positions.append(request.url.params["POS"])
        return httpx.Response(200, text=EMPTY_SIA)

    http = mock_http(handler)
    async with http.client:
        assert await query_exposures(http, BARNARD, ("spherex_qr3",)) == []
    dec_deg = positions[0].split()[2]
    assert float(dec_deg) - BARNARD.dec_deg > 0.07  # ~4.5' of northward motion since J2000


async def test_query_exposures_fails_when_one_collection_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["COLLECTION"] == "spherex_qr3":
            return httpx.Response(400)
        return httpx.Response(200, text=EMPTY_SIA)

    http = mock_http(handler)
    async with http.client:
        with pytest.raises(ArchiveError, match="HTTP 400") as info:
            await query_exposures(http, BARNARD, ("spherex_dr1", "spherex_qr3"))
    assert info.value.status == 400


def flaky_sia(calls: Counter[str], failing: set[str]) -> Handler:
    by_collection = sia_rows_by_collection("barnard")

    def handler(request: httpx.Request) -> httpx.Response:
        collection = request.url.params["COLLECTION"]
        calls[collection] += 1
        if collection in failing:
            return httpx.Response(502)
        return httpx.Response(200, text=by_collection.get(collection, EMPTY_SIA))

    return handler


async def test_retried_query_asks_only_for_the_collections_that_failed() -> None:
    calls = Counter[str]()
    failing = {"spherex_qr3"}
    cache = SiaCache()
    http = mock_http(flaky_sia(calls, failing))
    collections = ("spherex_dr1", "spherex_qr3")
    async with http.client:
        with pytest.raises(ArchiveError):
            await query_exposures(http, BARNARD, collections, cache=cache)
        failing.clear()
        exposures = await query_exposures(http, BARNARD, collections, cache=cache)
    assert calls == {"spherex_dr1": 1, "spherex_qr3": archive_http.ATTEMPTS + 1}
    assert {e.collection for e in exposures} == {"spherex_dr1", "spherex_qr3"}


async def test_sia_answers_are_asked_again_after_an_hour() -> None:
    calls = Counter[str]()
    clock = FakeClock()
    cache = SiaCache(clock=clock)
    http = mock_http(flaky_sia(calls, set()))
    async with http.client:
        await query_exposures(http, BARNARD, ("spherex_dr1",), cache=cache)
        clock.now = SIA_CACHE_TTL_S - 1
        await query_exposures(http, BARNARD, ("spherex_dr1",), cache=cache)
        assert calls["spherex_dr1"] == 1
        clock.now = SIA_CACHE_TTL_S + 1
        await query_exposures(http, BARNARD, ("spherex_dr1",), cache=cache)
    assert calls["spherex_dr1"] == 2
