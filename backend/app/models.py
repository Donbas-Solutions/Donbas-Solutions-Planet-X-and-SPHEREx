"""API contract models. Human-readable spec: docs/api.md. Keep both in sync."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FrameKind = Literal["visit_stack", "exposure", "diff", "allwise"]
FlagGroup = Literal["bad", "saturation", "artifact", "info"]
JobState = Literal["queued", "running", "done", "error"]


class CacheStats(BaseModel):
    raw_mb: float
    processed_items: int


class Health(BaseModel):
    status: Literal["ok"]
    collections: list[str]
    cache: CacheStats


class ResolveResult(BaseModel):
    name: str
    ra: float = Field(description="ICRS degrees at ref_epoch")
    dec: float
    ref_epoch: float = Field(description="Julian year of the position, e.g. 2000.0")
    pmra: float | None = Field(None, description="mas/yr, includes cos(dec)")
    pmdec: float | None = Field(None, description="mas/yr")
    parallax: float | None = Field(None, description="mas")
    source: str


class Grid(BaseModel):
    ra: float
    dec: float
    fov_arcmin: float
    npix: int
    pixscale_arcsec: float
    wcs: dict[str, str | float | int] = Field(description="FITS header cards of the north-up TAN grid")


class Stretch(BaseModel):
    kind: Literal["asinh", "linear", "log"] = "asinh"
    vmin: float
    vmax: float
    a: float = 0.1


class PixelPos(BaseModel):
    x: float = Field(description="0-based column")
    y: float = Field(description="0-based row; row 0 = south (FITS order)")


class Frame(BaseModel):
    id: str
    kind: FrameKind
    label: str
    mjd_mid: float
    date_range: tuple[str, str]
    detectors: list[int]
    lambda_um: tuple[float, float]
    n_exposures: int
    data: str = Field(description="URL of float32 LE array, relative to the manifest URL or absolute path")
    flags: str | None = Field(None, description="URL of uint32 LE OR-combined FLAGS array, same shape")
    shape: tuple[int, int] = Field(description="[ny, nx]")
    expected_px: PixelPos | None = None
    warnings: list[str] = []


class FlagBit(BaseModel):
    bit: int
    name: str
    description: str
    group: FlagGroup
    mask_in_stack: bool


class SequenceMeta(BaseModel):
    target_name: str | None = None
    collections: list[str]
    n_exposures_total: int
    generated_at: str
    pipeline_tags: list[str]
    mock: bool = False


class Sequence(BaseModel):
    grid: Grid
    stretch: Stretch
    flag_bits: list[FlagBit]
    frames: list[Frame]
    meta: SequenceMeta


class JobAccepted(BaseModel):
    job_id: str


class JobProgress(BaseModel):
    stage: str
    done: int
    total: int


class JobStatus(BaseModel):
    status: JobState
    progress: JobProgress
    result: Sequence | None = None
    error: str | None = None


class SpectrumPoint(BaseModel):
    lambda_um: float
    flux_ujy: float | None
    err_ujy: float | None
    mjd: float
    detector: int
    visit: str
    saturated: bool
    flags: int


class Spectrum(BaseModel):
    points: list[SpectrumPoint]


class GaiaStar(BaseModel):
    source_id: int
    ra: float
    dec: float
    g: float | None
    pmra: float | None
    pmdec: float | None


class Asteroid(BaseModel):
    name: str
    ra: float
    dec: float
    v: float | None


class Overlays(BaseModel):
    gaia: list[GaiaStar]
    asteroids: list[Asteroid]
    unavailable: list[str] = Field([], description="Overlay sources that failed (e.g. 'skybot')")
