"""Finished sequence bundles and target spectra on disk (`settings.processed_dir`).

`<root>/<key>/` holds one bundle (`sequence.json`, frames, `spectrum.json`); `<root>/spectra/<target>.json` the latest
spectrum of each target, which `/api/spectrum` and `/api/lightcurve` serve. Both expire after the TTL: new data
releases arrive weekly.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Final

import anyio

from .domain import SequenceResult
from .models import Sequence, Spectrum
from .pipeline.bundle import MANIFEST, write_bundle

SPECTRUM: Final = "spectrum.json"
SPECTRA_DIR: Final = "spectra"
_SPECTRA_LOCK: Final = threading.Lock()


def with_file_urls(sequence: Sequence, url_prefix: str) -> Sequence:
    """Bundle URLs are relative to the manifest; `url_prefix` is where the API serves the bundle (docs/api.md)."""
    frames = [
        frame.model_copy(update={"data": f"{url_prefix}/{frame.data}", "flags": f"{url_prefix}/{frame.flags}"})
        for frame in sequence.frames
    ]
    meta = sequence.meta
    if meta.spectrum is not None:
        meta = meta.model_copy(update={"spectrum": f"{url_prefix}/{meta.spectrum}"})
    return sequence.model_copy(update={"frames": frames, "meta": meta})


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.part")
    try:
        temp.write_text(text, encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def store_spectrum(
    processed_dir: Path, bundle_key: str, target_id: str, spectrum: Spectrum, *, stale_before: float
) -> None:
    """The bundle's copy always; the per-target copy unless a fresh earlier job measured more exposures (all
    detectors, where this job had a selection). A per-target copy last written before `stale_before` (Unix time)
    has outlived the TTL and is replaced whatever its size."""
    text = spectrum.model_dump_json(indent=1) + "\n"
    _write_atomic(processed_dir / bundle_key / SPECTRUM, text)
    per_target = processed_dir / SPECTRA_DIR / f"{target_id}.json"
    # Jobs of one target with different FOV or detectors finish in parallel worker threads.
    with _SPECTRA_LOCK:
        existing = _fresh_spectrum(per_target, stale_before)
        if existing is None or len(spectrum.points) >= len(existing.points):
            _write_atomic(per_target, text)


def _fresh_spectrum(path: Path, stale_before: float) -> Spectrum | None:
    try:
        if path.stat().st_mtime < stale_before:
            return None
        return Spectrum.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


class BundleStore:
    """Reads are async (event loop); writes are blocking and run in a worker thread."""

    def __init__(self, root: Path, *, url_prefix: str, ttl_s: float, clock: Callable[[], float] = time.time) -> None:
        self.root = root
        self._url_prefix = url_prefix
        self._ttl_s = ttl_s
        self._clock = clock

    async def load(self, key: str, *, fresh_only: bool) -> Sequence | None:
        """The bundle with servable URLs; `fresh_only` treats a bundle older than the TTL as missing."""
        text = await self._read(self.root / key / MANIFEST, fresh_only=fresh_only)
        if text is None:
            return None
        return with_file_urls(Sequence.model_validate_json(text), f"{self._url_prefix}/{key}")

    async def spectrum(self, target_id: str) -> Spectrum | None:
        text = await self._read(self.root / SPECTRA_DIR / f"{target_id}.json", fresh_only=True)
        return None if text is None else Spectrum.model_validate_json(text)

    def write_bundle(self, result: SequenceResult, key: str) -> None:
        write_bundle(result, self.root / key)

    def store_spectrum(self, bundle_key: str, target_id: str, spectrum: Spectrum) -> None:
        store_spectrum(self.root, bundle_key, target_id, spectrum, stale_before=self._clock() - self._ttl_s)

    async def _read(self, path: Path, *, fresh_only: bool) -> str | None:
        file = anyio.Path(path)
        try:
            if fresh_only and self._clock() - (await file.stat()).st_mtime > self._ttl_s:
                return None
            return await file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
