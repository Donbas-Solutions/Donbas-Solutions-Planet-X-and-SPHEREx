"""Shared domain types: the seam between the archive layer (Track A) and the science pipeline (Track C).

Track A turns a Target into Cutouts; Track C turns Cutouts into a SequenceResult. Neither side imports the other.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt
from astropy.io import fits

from .models import Sequence as SequenceModel

DETECTORS: Final[tuple[int, ...]] = (1, 2, 3, 4, 5, 6)

ProgressCallback = Callable[[str, int, int], None]
"""Called as (stage, done, total). May be called from worker threads: keep it fast and thread-safe."""


@dataclass(frozen=True)
class Target:
    """Sky position in ICRS degrees at `ref_epoch` (Julian year); `pmra_masyr` includes cos(dec)."""

    ra_deg: float
    dec_deg: float
    ref_epoch: float = 2000.0
    pmra_masyr: float | None = None
    pmdec_masyr: float | None = None
    name: str | None = None

    @property
    def has_proper_motion(self) -> bool:
        return self.pmra_masyr is not None and self.pmdec_masyr is not None


@dataclass(frozen=True)
class ExposureMeta:
    """One detector image of one exposure, as listed by SIA.

    An `obs_id` is shared by the two detectors that see the same sky through the dichroic, so the unique key is
    (obs_id, detector) — never deduplicate by `obs_id` alone.
    """

    obs_id: str
    detector: int
    collection: str
    access_url: str
    mjd_start: float
    mjd_end: float
    lambda_min_um: float
    lambda_max_um: float

    @property
    def key(self) -> str:
        return f"{self.obs_id}_D{self.detector}"

    @property
    def mjd_mid(self) -> float:
        return (self.mjd_start + self.mjd_end) / 2


@dataclass(frozen=True)
class Visit:
    """Exposures of one survey pass (or one fixed time bin of a deep-field cluster), in time order."""

    id: str
    mjd_start: float
    mjd_end: float
    binned: bool
    exposures: tuple[ExposureMeta, ...]


@dataclass(frozen=True, eq=False)
class Cutout:
    """Pixel data of one ExposureMeta around the target (EPSF dropped). All arrays share the shape [ny, nx].

    `image` and `zodi` are surface brightness in MJy/sr, `variance` in (MJy/sr)^2, `flags` the raw FLAGS bits.
    `wavelength_um` / `bandwidth_um` are the per-pixel LVF centre and width. `header` is the IMAGE header,
    which holds the celestial WCS (TAN-SIP).
    """

    meta: ExposureMeta
    visit_id: str
    mjd_avg: float
    image: npt.NDArray[np.float32]
    variance: npt.NDArray[np.float32]
    zodi: npt.NDArray[np.float32]
    flags: npt.NDArray[np.uint32]
    wavelength_um: npt.NDArray[np.float32]
    bandwidth_um: npt.NDArray[np.float32]
    header: fits.Header


@dataclass(frozen=True)
class SequenceParams:
    fov_arcmin: float = 10.0
    detectors: tuple[int, ...] = DETECTORS
    mode: Literal["visit_stack", "exposures"] = "visit_stack"


@dataclass(frozen=True, eq=False)
class FrameArrays:
    data: npt.NDArray[np.float32]
    flags: npt.NDArray[np.uint32]


@dataclass(frozen=True, eq=False)
class SequenceResult:
    """A Sequence manifest plus the arrays of each frame, keyed by `Frame.id`."""

    sequence: SequenceModel
    arrays: Mapping[str, FrameArrays]
