"""Cache keys of sequences and target spectra: equal requests share one job and one bundle."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from ..domain import SequenceParams, Target


def target_key(target: Target) -> str:
    """Same position, motion and epoch → same key; the spectrum does not depend on FOV, detectors or mode."""
    return _digest(_target_parts(target))


def _target_parts(target: Target) -> tuple[str, ...]:
    return (
        f"{target.ra_deg:.5f}",
        f"{target.dec_deg:.5f}",
        f"{target.ref_epoch:.3f}",
        _pm(target.pmra_masyr),
        _pm(target.pmdec_masyr),
    )


def _digest(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class SequenceRequest:
    target: Target
    params: SequenceParams

    @property
    def key(self) -> str:
        """Same sequence → same key. Rounding to 1e-5° (0.04″) is far below the 6.2″ pixel."""
        p = self.params
        return _digest(
            (
                *_target_parts(self.target),
                f"{p.fov_arcmin:.1f}",
                ",".join(str(d) for d in sorted(set(p.detectors))),
                p.mode,
                str(p.include_allwise),
            )
        )


def _pm(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"
