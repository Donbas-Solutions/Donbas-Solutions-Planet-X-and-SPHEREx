"""Runtime settings, read once from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fallback when TAP collection discovery fails (verified 2026-11-14).
DEFAULT_COLLECTIONS = ("spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep")


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    cache_dir: Path = field(default_factory=lambda: Path(os.environ.get("SPHEREX_CACHE_DIR", REPO_ROOT / "cache")))
    fallback_collections: tuple[str, ...] = field(
        default_factory=lambda: _csv("SPHEREX_COLLECTIONS", DEFAULT_COLLECTIONS)
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _csv("CORS_ORIGINS", ("http://localhost:5173", "http://127.0.0.1:5173"))
    )
    max_concurrency: int = field(default_factory=lambda: int(os.environ.get("IRSA_MAX_CONCURRENCY", "8")))
    http_timeout_s: float = field(default_factory=lambda: float(os.environ.get("IRSA_TIMEOUT_S", "120")))
    raw_cache_max_mb: int = field(default_factory=lambda: int(os.environ.get("RAW_CACHE_MAX_MB", "5000")))
    s3_base_url: str = field(
        default_factory=lambda: os.environ.get("SPHEREX_S3_URL", "https://nasa-irsa-spherex.s3.amazonaws.com/")
    )
    live_cap_per_detector: int = field(default_factory=lambda: int(os.environ.get("LIVE_CAP_PER_DETECTOR", "8")))
    max_running_jobs: int = field(default_factory=lambda: int(os.environ.get("MAX_RUNNING_JOBS", "2")))
    pipeline_workers: int = field(default_factory=lambda: int(os.environ.get("PIPELINE_WORKERS", "2")))
    processed_ttl_h: float = field(default_factory=lambda: float(os.environ.get("PROCESSED_TTL_H", "24")))
    warm_collections: bool = field(default_factory=lambda: os.environ.get("WARM_COLLECTIONS", "1") != "0")
    user_agent: str = "spherex-blink/0.1"

    @property
    def raw_dir(self) -> Path:
        return self.cache_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.cache_dir / "processed"


def configure_ssl() -> None:
    """Use certifi's CA bundle unless the user configured one.

    python.org builds of Python on macOS ship without system CA certificates, so
    urllib-based downloads (astropy) fail with CERTIFICATE_VERIFY_FAILED.
    """
    if "SSL_CERT_FILE" in os.environ:
        return
    try:
        import certifi
    except ImportError:
        return
    os.environ["SSL_CERT_FILE"] = certifi.where()


settings = Settings()
