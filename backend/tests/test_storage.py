"""Cache statistics behind /api/health."""

from __future__ import annotations

from pathlib import Path

from app.storage import CacheMeter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_cache_meter_recounts_only_after_its_ttl(tmp_path: Path) -> None:
    raw, processed, clock = tmp_path / "raw", tmp_path / "processed", FakeClock()
    raw.mkdir()
    processed.mkdir()
    meter = CacheMeter(raw, processed, ttl_s=60.0, clock=clock)
    (raw / "a.fits").write_bytes(b"x" * 2_000_000)
    assert meter.stats().raw_mb == 2.0

    (raw / "b.fits").write_bytes(b"x" * 3_000_000)
    clock.now = 59.0
    assert meter.stats().raw_mb == 2.0
    clock.now = 60.0
    assert meter.stats().raw_mb == 5.0


def test_cache_meter_counts_finished_bundles(tmp_path: Path) -> None:
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    (processed / "k1").mkdir(parents=True)
    (processed / "k1" / "sequence.json").write_text("{}", encoding="utf-8")
    (processed / "spectra").mkdir()
    assert CacheMeter(raw, processed).stats().processed_items == 1
