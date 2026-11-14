"""Range reads of full L2 files (A2) against a synthetic full file built from the recorded cutout. No network."""

from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from app.archive import http as archive_http
from app.archive.cutouts import load_cutout
from app.archive.fetch import fetch_cutouts, fetch_one
from app.archive.http import ArchiveError, Http, make_http
from app.archive.ranges import IBE_PREFIX, OffDetectorError, fetch_window, pixel_window, read_ranges, s3_url
from app.config import settings
from app.domain import ExposureMeta, Visit
from app.grid import SPHEREX_PIXSCALE_ARCSEC

pytestmark = pytest.mark.anyio

FIXTURE = Path(__file__).parent / "fixtures" / "cutout_barnard_qr3_d3.fits"
ACCESS_URL = (
    IBE_PREFIX + "qr3/level2/2026W33_2A/l2b-v27-2026-241/3/level2_2026W33_2A_0594_4D3_spx_l2b-v27-2026-241.fits"
)
WINDOW_PX = 11


def full_file_bytes() -> bytes:
    """The recorded cutout dressed up as a full L2 file: RICE-tiled FLAGS (one tile per row) and an EPSF."""
    with fits.open(FIXTURE) as src:
        flags = np.asarray(src["FLAGS"].data, dtype=np.int32)
        hdus = [
            fits.PrimaryHDU(header=src[0].header),
            src["IMAGE"].copy(),
            fits.CompImageHDU(
                data=flags,
                header=src["FLAGS"].header,
                compression_type="RICE_1",
                tile_shape=(1, flags.shape[1]),
                name="FLAGS",
            ),
            src["VARIANCE"].copy(),
            src["ZODI"].copy(),
            fits.ImageHDU(data=np.ones((40, 50), dtype=np.float32), name="EPSF"),
            src["WCS-WAVE"].copy(),
        ]
        buffer = io.BytesIO()
        fits.HDUList(hdus).writeto(buffer)
    return buffer.getvalue()


FULL = full_file_bytes()


@dataclass
class FakeServer:
    """Answers like S3 (`multi=False`: multi-range → 200 + whole file) or like IRSA ibe (multipart, ≤100 ranges)."""

    content: bytes
    multi: bool
    status: int | None = None
    requests: Counter[str] = field(default_factory=Counter)
    max_ranges_seen: int = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests["n"] += 1
        if self.status is not None:
            return httpx.Response(self.status)
        spec = request.headers.get("Range")
        if spec is None:
            return httpx.Response(200, content=self.content)
        ranges = [(int(a), int(b) + 1) for a, b in re.findall(r"(\d+)-(\d+)", spec)]
        self.max_ranges_seen = max(self.max_ranges_seen, len(ranges))
        total = len(self.content)
        if len(ranges) == 1:
            start, end = ranges[0]
            end = min(end, total)
            return httpx.Response(
                206, content=self.content[start:end], headers={"Content-Range": f"bytes {start}-{end - 1}/{total}"}
            )
        if not self.multi or len(ranges) > 100:
            return httpx.Response(200, content=self.content)
        body = b""
        for start, end in ranges:
            body += (
                (
                    f"--XB\r\nContent-Type: application/fits\r\nContent-Range: bytes {start}-{end - 1}/{total}\r\n\r\n"
                ).encode()
                + self.content[start:end]
                + b"\r\n"
            )
        body += b"--XB--\r\n"
        return httpx.Response(206, content=body, headers={"Content-Type": "multipart/byteranges; boundary=XB"})


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive_http, "backoff_s", lambda attempt, response: 0.0)
    monkeypatch.setattr("app.archive.ranges.backoff_s", lambda attempt, response: 0.0)


def mock_http(handler: httpx.MockTransport | FakeServer) -> Http:
    transport = handler if isinstance(handler, httpx.MockTransport) else httpx.MockTransport(handler)
    return make_http(max_concurrency=4, transport=transport)


def sky_of_pixel(x: float, y: float) -> tuple[float, float]:
    with fits.open(FIXTURE) as src:
        ra, dec = WCS(src["IMAGE"].header).all_pix2world([[x, y]], 0)[0]
    return float(ra), float(dec)


def window_size_deg(px: int = WINDOW_PX) -> float:
    return px * SPHEREX_PIXSCALE_ARCSEC / 3600


def meta() -> ExposureMeta:
    return ExposureMeta(
        obs_id="2026W33_2A_0594_4",
        detector=3,
        collection="spherex_qr3",
        access_url=ACCESS_URL,
        mjd_start=61268.630,
        mjd_end=61268.633,
        lambda_min_um=1.6,
        lambda_max_um=2.5,
    )


def test_window_is_centred_and_clipped_to_the_detector() -> None:
    with fits.open(FIXTURE) as src:
        header = src["IMAGE"].header
    centred = pixel_window(header, sky_of_pixel(14, 14), window_size_deg())
    assert (centred.x0, centred.x1, centred.y0, centred.y1) == (9, 20, 9, 20)
    corner = pixel_window(header, sky_of_pixel(1, 2), window_size_deg())
    assert (corner.x0, corner.y0) == (0, 0)
    assert (corner.x1, corner.y1) == (7, 8)


def test_window_off_the_detector_is_refused() -> None:
    with fits.open(FIXTURE) as src:
        header = src["IMAGE"].header
    with pytest.raises(OffDetectorError):
        pixel_window(header, sky_of_pixel(200, 200), window_size_deg())


def test_s3_url_mirrors_the_ibe_path() -> None:
    assert s3_url(ACCESS_URL) == settings.s3_base_url + ACCESS_URL.removeprefix(IBE_PREFIX)


def test_s3_url_refuses_foreign_urls() -> None:
    with pytest.raises(ArchiveError):
        s3_url("https://example.org/file.fits")


@pytest.mark.parametrize("multi", [False, True])
async def test_window_file_matches_the_full_frame(tmp_path: Path, multi: bool) -> None:
    server = FakeServer(FULL, multi=multi)
    out = tmp_path / "window.fits"
    http = mock_http(server)
    async with http.client:
        await fetch_window(http, ACCESS_URL, sky_of_pixel(14, 14), window_size_deg(), out, multi=multi)

    window = load_cutout(out, meta(), "v1")
    whole = load_cutout(FIXTURE, meta(), "v1")
    box = np.s_[9:20, 9:20]
    for name in ("image", "variance", "zodi", "flags", "wavelength_um", "bandwidth_um"):
        np.testing.assert_array_equal(getattr(window, name), getattr(whole, name)[box], err_msg=name)
    assert window.mjd_avg == whole.mjd_avg


async def test_window_file_keeps_flag_names_and_shifts_every_crpix(tmp_path: Path) -> None:
    out = tmp_path / "window.fits"
    http = mock_http(FakeServer(FULL, multi=False))
    async with http.client:
        await fetch_window(http, ACCESS_URL, sky_of_pixel(14, 14), window_size_deg(), out, multi=False)
    with fits.open(out) as got, fits.open(FIXTURE) as src:
        assert [h.name for h in got] == ["PRIMARY", "IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE"]
        assert got["FLAGS"].header["MSKN0021"] == src["FLAGS"].header["MSKN0021"]
        for key in ("CRPIX1", "CRPIX1A", "CRPIX1W"):
            assert got["IMAGE"].header[key] == src["IMAGE"].header[key] - 9


async def test_s3_style_server_never_sends_the_whole_file(tmp_path: Path) -> None:
    server = FakeServer(FULL, multi=False)
    http = mock_http(server)
    async with http.client:
        with pytest.raises(ArchiveError, match="instead of 206"):
            await read_ranges(http, ACCESS_URL, [(0, 10), (20, 30)], multi=True)


async def test_multi_range_requests_stay_within_the_server_limit() -> None:
    server = FakeServer(FULL, multi=True)
    ranges = [(i * 10, i * 10 + 5) for i in range(150)]
    http = mock_http(server)
    async with http.client:
        parts = await read_ranges(http, ACCESS_URL, ranges, multi=True)
    assert parts == [FULL[a:b] for a, b in ranges]
    assert server.max_ranges_seen == 100
    assert server.requests["n"] == 2


def routed(by_host: dict[str, FakeServer]) -> httpx.MockTransport:
    unknown = FakeServer(b"", multi=False, status=503)
    return httpx.MockTransport(lambda request: by_host.get(request.url.host, unknown)(request))


S3_HOST = httpx.URL(settings.s3_base_url).host
IBE_HOST = "irsa.ipac.caltech.edu"


async def test_fetch_falls_back_from_s3_to_ibe_and_then_uses_the_cache(tmp_path: Path) -> None:
    s3 = FakeServer(FULL, multi=False, status=404)
    ibe = FakeServer(FULL, multi=True)
    http = mock_http(routed({S3_HOST: s3, IBE_HOST: ibe}))
    center, size = sky_of_pixel(14, 14), window_size_deg()
    async with http.client:
        first = await fetch_one(http, meta(), "v1", center, size, tmp_path / "not" / "yet")
        served = ibe.requests["n"]
        again = await fetch_one(http, meta(), "v1", center, size, tmp_path / "not" / "yet")
    assert served > 0
    assert ibe.requests["n"] == served
    np.testing.assert_array_equal(first.image, again.image)


async def test_fetch_cutouts_reports_failed_and_off_detector_exposures(tmp_path: Path) -> None:
    down = FakeServer(FULL, multi=False, status=503)
    http = mock_http(routed({S3_HOST: FakeServer(FULL, multi=False), IBE_HOST: down}))
    good = meta()
    broken = ExposureMeta(**{**good.__dict__, "access_url": "https://elsewhere.example/x.fits", "detector": 4})
    visit = Visit(id="v1", mjd_start=good.mjd_start, mjd_end=good.mjd_end, binned=False, exposures=(good, broken))
    calls: list[tuple[str, int, int]] = []

    async with http.client:
        result = await fetch_cutouts(
            http,
            [(visit, good), (visit, broken)],
            sky_of_pixel(14, 14),
            window_size_deg(),
            progress=lambda stage, done, total: calls.append((stage, done, total)),
            raw_dir=tmp_path,
        )
        far = await fetch_cutouts(http, [(visit, good)], sky_of_pixel(200, 200), window_size_deg(), raw_dir=tmp_path)
    assert [c.meta.key for c in result.cutouts] == [good.key]
    assert result.failed == [broken]
    assert calls[-1] == ("fetch", 2, 2)
    assert far.off_detector == [good]
    assert not far.failed
