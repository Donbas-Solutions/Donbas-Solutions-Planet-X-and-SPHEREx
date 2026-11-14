"""A window of a full SPHEREx L2 file read with HTTP range requests (OD-4), written like a stripped IRSA cutout.

Only the HDUs the pipeline needs are read: the 4 MB EPSF that every IRSA cutout carries is skipped. S3 gets one
range per request (it answers a multi-range request with `200` and the whole 62 MB file); IRSA `ibe` gets
multipart range requests of up to 100 ranges (101+ also turn into `200` and the whole file).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import anyio
import httpx
import numpy as np
import numpy.typing as npt
from astropy.io import fits
from astropy.io.fits.hdu.compressed._codecs import Rice1  # no public per-tile decoder; pinned by uv.lock
from astropy.wcs import WCS

from ..config import settings
from ..grid import SPHEREX_PIXSCALE_ARCSEC
from .cutouts import shift_crpix, write_atomic
from .http import ATTEMPTS, RETRY_STATUS, ArchiveError, Http, backoff_s, raise_first

logger = logging.getLogger(__name__)

BLOCK: Final = 2880
HEADER_CHUNK: Final = 12 * BLOCK
MAX_RANGES_PER_REQUEST: Final = 100
FLOAT_HDUS: Final = ("IMAGE", "VARIANCE", "ZODI")
LAST_HDU: Final = "WCS-WAVE"
IBE_PREFIX: Final = "https://irsa.ipac.caltech.edu/ibe/data/spherex/"
_TABLE_CARD = re.compile(r"^(XTENSION|BITPIX|NAXIS\d*|PCOUNT|GCOUNT|TFIELDS|TTYPE\d+|TFORM\d+|THEAP|Z\w+)$")
_CONTENT_RANGE = re.compile(r"bytes (\d+)-(\d+)/")


class OffDetectorError(ArchiveError):
    """The requested window does not overlap the detector; no other source can do better."""


@dataclass(frozen=True)
class HduLayout:
    name: str
    header: fits.Header
    raw_header: bytes
    data_offset: int
    data_size: int


@dataclass(frozen=True)
class Window:
    """0-based, half-open pixel box [x0, x1) × [y0, y1) inside the detector."""

    x0: int
    x1: int
    y0: int
    y1: int


@dataclass(frozen=True)
class WindowBytes:
    floats: dict[str, bytes]
    flag_descriptors: bytes
    flag_heap: bytes
    flag_heap_start: int
    wave_data: bytes


def s3_url(access_url: str) -> str:
    if not access_url.startswith(IBE_PREFIX):
        raise ArchiveError(f"No S3 path for {access_url}")
    return settings.s3_base_url + access_url.removeprefix(IBE_PREFIX)


async def read_ranges(http: Http, url: str, ranges: Sequence[tuple[int, int]], *, multi: bool) -> list[bytes]:
    """Bytes of each half-open range [start, end). `multi` only for servers that answer multipart/byteranges."""
    batches = [ranges[i : i + MAX_RANGES_PER_REQUEST] for i in range(0, len(ranges), MAX_RANGES_PER_REQUEST)]
    if not multi:
        batches = [[r] for r in ranges]
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(_request(http, url, batch)) for batch in batches]
    except* ArchiveError as failures:
        raise_first(failures)
    return [part for task in tasks for part in task.result()]


async def _request(http: Http, url: str, ranges: Sequence[tuple[int, int]]) -> list[bytes]:
    spec = ",".join(f"{start}-{end - 1}" for start, end in ranges)
    for attempt in range(1, ATTEMPTS + 1):
        status: int | None = None
        try:
            async with http.limit, http.client.stream("GET", url, headers={"Range": f"bytes={spec}"}) as response:
                status = response.status_code
                if status == httpx.codes.PARTIAL_CONTENT:
                    await response.aread()
                    return _split(response, ranges)
                if status not in RETRY_STATUS:
                    # Never read the body: a 200 here is the whole 62 MB file.
                    raise ArchiveError(f"HTTP {status} instead of 206 for a range request", status)
                last = response
        except httpx.TransportError as exc:
            if attempt == ATTEMPTS:
                raise ArchiveError(f"Range request failed: {type(exc).__name__}") from exc
            last = None
        if attempt == ATTEMPTS:
            raise ArchiveError(f"HTTP {status} for a range request after {ATTEMPTS} attempts", status)
        await asyncio.sleep(backoff_s(attempt, last))
    raise AssertionError("unreachable")


def _split(response: httpx.Response, ranges: Sequence[tuple[int, int]]) -> list[bytes]:
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("multipart/byteranges"):
        match = _CONTENT_RANGE.match(response.headers.get("content-range", ""))
        if len(ranges) != 1 or match is None or int(match.group(1)) != ranges[0][0]:
            raise ArchiveError("Unexpected range response")
        return [response.content]
    boundary = re.search(r'boundary="?([^";]+)"?', content_type)
    if boundary is None:
        raise ArchiveError("Multipart response without a boundary")
    parts: dict[int, bytes] = {}
    for chunk in response.content.split(b"--" + boundary.group(1).encode()):
        head, separator, body = chunk.partition(b"\r\n\r\n")
        found = re.search(rb"content-range: bytes (\d+)-(\d+)/", head, re.IGNORECASE)
        if separator and found:
            start, end = int(found.group(1)), int(found.group(2)) + 1
            parts[start] = body[: end - start]
    try:
        return [parts[start] for start, _ in ranges]
    except KeyError as exc:
        raise ArchiveError("Multipart response is missing a range") from exc


def _header_end(raw: bytes) -> int | None:
    for i in range(0, len(raw) - 79, 80):
        if raw[i : i + 8] == b"END     ":
            return math.ceil((i + 80) / BLOCK) * BLOCK
    return None


def _data_size(header: fits.Header) -> int:
    naxis = int(header.get("NAXIS", 0))
    if naxis == 0:
        return 0
    n = math.prod(int(header[f"NAXIS{i}"]) for i in range(1, naxis + 1))
    size = abs(int(header["BITPIX"])) // 8 * int(header.get("GCOUNT", 1)) * (n + int(header.get("PCOUNT", 0)))
    return math.ceil(size / BLOCK) * BLOCK


def _parse_header(raw: bytes) -> fits.Header:
    return fits.Header.fromstring(raw.decode("ascii"))


async def read_layout(http: Http, url: str, *, multi: bool) -> dict[str, HduLayout]:
    """Headers and data offsets of every HDU up to WCS-WAVE (one request per header)."""
    layout: dict[str, HduLayout] = {}
    offset = 0
    while LAST_HDU not in layout:
        raw = b""
        while (end := _header_end(raw)) is None:
            (chunk,) = await read_ranges(
                http, url, [(offset + len(raw), offset + len(raw) + HEADER_CHUNK)], multi=multi
            )
            if not chunk:
                raise ArchiveError(f"No {LAST_HDU} HDU in {url}")
            raw += chunk
        header = await anyio.to_thread.run_sync(_parse_header, raw[:end])
        name = str(header.get("EXTNAME", "PRIMARY"))
        layout[name] = HduLayout(name, header, raw[:end], offset + end, _data_size(header))
        offset += end + layout[name].data_size
    return layout


def pixel_window(header: fits.Header, center: tuple[float, float], size_deg: float) -> Window:
    """Pixels whose centres lie within ±size/2 of the target, clipped to the detector (IRSA does not pad)."""
    x, y = WCS(header).all_world2pix([[center[0], center[1]]], 0)[0]
    half = size_deg * 3600 / SPHEREX_PIXSCALE_ARCSEC / 2
    nx, ny = int(header["NAXIS1"]), int(header["NAXIS2"])
    window = Window(
        x0=max(0, math.ceil(x - half)),
        x1=min(nx, math.floor(x + half) + 1),
        y0=max(0, math.ceil(y - half)),
        y1=min(ny, math.floor(y + half) + 1),
    )
    if window.x1 <= window.x0 or window.y1 <= window.y0:
        raise OffDetectorError(f"Target at pixel ({x:.0f}, {y:.0f}) is off the {nx}x{ny} detector")
    return window


def _tile_descriptors(flags: fits.Header, raw: bytes) -> npt.NDArray[np.int64]:
    """(n_rows, 2) array of (byte count, heap offset): one RICE tile per image row."""
    if int(flags.get("TFIELDS", 0)) != 1 or flags.get("ZCMPTYPE") != "RICE_1" or int(flags.get("ZTILE2", 0)) != 1:
        raise ArchiveError("Unsupported FLAGS compression layout")
    wide = str(flags["TFORM1"]).lstrip("0123456789").startswith("Q")
    return np.frombuffer(raw, ">i8" if wide else ">i4").reshape(-1, 2).astype(np.int64)


def _heap_start(flags: HduLayout) -> int:
    header = flags.header
    return flags.data_offset + int(header.get("THEAP", int(header["NAXIS1"]) * int(header["NAXIS2"])))


def flag_descriptor_range(flags: HduLayout, window: Window) -> tuple[int, int]:
    row_bytes = int(flags.header["NAXIS1"])
    return flags.data_offset + window.y0 * row_bytes, flags.data_offset + window.y1 * row_bytes


def flag_heap_range(flags: HduLayout, descriptors: bytes) -> tuple[int, int]:
    tiles = _tile_descriptors(flags.header, descriptors)
    counts, offsets = tiles[:, 0], tiles[:, 1]
    return _heap_start(flags) + int(np.min(offsets)), _heap_start(flags) + int(np.max(offsets + counts))


def float_ranges(hdu: HduLayout, window: Window, *, multi: bool) -> list[tuple[int, int]]:
    """Row segments of the window (multi-range servers) or one block of whole rows (single-range servers)."""
    nx, bpp = int(hdu.header["NAXIS1"]), abs(int(hdu.header["BITPIX"])) // 8
    start = hdu.data_offset
    if multi:
        return [
            (start + (y * nx + window.x0) * bpp, start + (y * nx + window.x1) * bpp)
            for y in range(window.y0, window.y1)
        ]
    return [(start + window.y0 * nx * bpp, start + window.y1 * nx * bpp)]


def _float_window(hdu: HduLayout, window: Window, raw: bytes, *, multi: bool) -> npt.NDArray[np.float32]:
    rows = window.y1 - window.y0
    if multi:
        return np.frombuffer(raw, ">f4").reshape(rows, window.x1 - window.x0)
    return np.frombuffer(raw, ">f4").reshape(rows, int(hdu.header["NAXIS1"]))[:, window.x0 : window.x1]


def _flags_window(flags: HduLayout, window: Window, data: WindowBytes) -> npt.NDArray[np.int32]:
    header = flags.header
    codec = Rice1(blocksize=int(header["ZVAL1"]), bytepix=int(header["ZVAL2"]), tilesize=int(header["ZNAXIS1"]))
    heap = np.frombuffer(data.flag_heap, np.uint8)
    base = _heap_start(flags) - data.flag_heap_start
    rows = [
        np.asarray(codec.decode(heap[base + int(offset) : base + int(offset) + int(count)])).view(np.int32)
        for count, offset in _tile_descriptors(header, data.flag_descriptors)
    ]
    return np.stack(rows)[:, window.x0 : window.x1]


def _image_header(flags: fits.Header) -> fits.Header:
    return fits.Header([card for card in flags.cards if not _TABLE_CARD.match(card.keyword)])


def write_window_file(
    path: Path, layout: dict[str, HduLayout], window: Window, data: WindowBytes, *, multi: bool
) -> None:
    """Same HDUs, headers and pixels as `cutouts.strip_to_file` of an IRSA cutout of this window."""
    hdus: list[fits.PrimaryHDU | fits.ImageHDU | fits.BinTableHDU] = [fits.PrimaryHDU(header=layout["PRIMARY"].header)]
    for name in ("IMAGE", "FLAGS", "VARIANCE", "ZODI"):
        hdu = layout[name]
        if name == "FLAGS":
            array: npt.NDArray[np.generic] = _flags_window(hdu, window, data)
            header = _image_header(hdu.header)
        else:
            array = _float_window(hdu, window, data.floats[name], multi=multi)
            header = hdu.header
        hdus.append(fits.ImageHDU(data=np.ascontiguousarray(array), header=shift_crpix(header, window.x0, window.y0)))
    wave = layout[LAST_HDU]
    wave_hdul = fits.HDUList.fromstring(layout["PRIMARY"].raw_header + wave.raw_header + data.wave_data)
    hdus.append(fits.BinTableHDU(data=wave_hdul[1].data.copy(), header=wave_hdul[1].header))
    write_atomic(fits.HDUList(hdus), path)


async def fetch_window(
    http: Http, url: str, center: tuple[float, float], size_deg: float, path: Path, *, multi: bool
) -> None:
    """Read the window around `center` from the full file at `url` and write it to `path`."""
    layout = await read_layout(http, url, multi=multi)
    window = await anyio.to_thread.run_sync(pixel_window, layout["IMAGE"].header, center, size_deg)
    flags, wave = layout["FLAGS"], layout[LAST_HDU]

    async def floats(name: str) -> bytes:
        return b"".join(await read_ranges(http, url, float_ranges(layout[name], window, multi=multi), multi=multi))

    async def flag_bytes() -> tuple[bytes, bytes, int]:
        (descriptors,) = await read_ranges(http, url, [flag_descriptor_range(flags, window)], multi=multi)
        start, end = flag_heap_range(flags, descriptors)
        (heap,) = await read_ranges(http, url, [(start, end)], multi=multi)
        return descriptors, heap, start

    try:
        async with asyncio.TaskGroup() as group:
            float_tasks = {name: group.create_task(floats(name)) for name in FLOAT_HDUS}
            flag_task = group.create_task(flag_bytes())
            wave_task = group.create_task(
                read_ranges(http, url, [(wave.data_offset, wave.data_offset + wave.data_size)], multi=multi)
            )
    except* ArchiveError as failures:
        raise_first(failures)
    descriptors, heap, heap_start = flag_task.result()
    data = WindowBytes(
        floats={name: task.result() for name, task in float_tasks.items()},
        flag_descriptors=descriptors,
        flag_heap=heap,
        flag_heap_start=heap_start,
        wave_data=wave_task.result()[0],
    )
    await anyio.to_thread.run_sync(functools.partial(write_window_file, path, layout, window, data, multi=multi))
