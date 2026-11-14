"""Entry point of the science pipeline (Track C: C1).

`build_sequence` is pure and synchronous: it may run in a process pool, so arguments and results must stay
picklable (pass `progress=None` there). Rules: SR-1 … SR-6 in docs/spec.md; output contract: docs/api.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..domain import Cutout, ProgressCallback, SequenceParams, SequenceResult, Target


def build_sequence(
    cutouts: Sequence[Cutout],
    target: Target,
    params: SequenceParams,
    progress: ProgressCallback | None = None,
) -> SequenceResult:
    raise NotImplementedError("Track C: C1")
