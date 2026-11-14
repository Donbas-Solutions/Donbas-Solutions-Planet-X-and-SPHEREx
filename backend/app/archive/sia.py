"""IRSA SIA2 queries and parsing of their CSV responses into ExposureMeta."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Final

from ..domain import ExposureMeta

logger = logging.getLogger(__name__)

SIA_URL: Final = "https://irsa.ipac.caltech.edu/SIA"
SEARCH_RADIUS_DEG: Final = 0.01
_BANDPASS = re.compile(r"^SPHEREx-D([1-6])$")
_METRES_TO_UM: Final = 1e6


def sia_params(collection: str, ra_deg: float, dec_deg: float, radius_deg: float) -> dict[str, str]:
    return {
        "COLLECTION": collection,
        "POS": f"circle {ra_deg:.6f} {dec_deg:.6f} {radius_deg:.6f}",
        "RESPONSEFORMAT": "CSV",
    }


def parse_sia_csv(text: str) -> list[ExposureMeta]:
    """Rows of one or more SIA CSV responses → unique exposures sorted by time, then detector."""
    exposures: dict[str, ExposureMeta] = {}
    for row in csv.DictReader(io.StringIO(text)):
        match = _BANDPASS.match(row["energy_bandpassname"])
        if match is None:
            logger.warning("Skipping SIA row with unknown bandpass %r", row["energy_bandpassname"])
            continue
        meta = ExposureMeta(
            obs_id=row["obs_id"],
            detector=int(match.group(1)),
            collection=row["obs_collection"],
            access_url=row["access_url"],
            mjd_start=float(row["t_min"]),
            mjd_end=float(row["t_max"]),
            lambda_min_um=float(row["em_min"]) * _METRES_TO_UM,
            lambda_max_um=float(row["em_max"]) * _METRES_TO_UM,
        )
        exposures.setdefault(meta.key, meta)
    return sorted(exposures.values(), key=lambda m: (m.mjd_start, m.detector))
