"""IRSA SIA2 queries and parsing of their CSV responses into ExposureMeta."""

from __future__ import annotations

import csv
import io
import logging
import re
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Final

from ..domain import ExposureMeta

logger = logging.getLogger(__name__)

SIA_URL: Final = "https://irsa.ipac.caltech.edu/SIA"
SEARCH_RADIUS_DEG: Final = 0.01
_BANDPASS = re.compile(r"^SPHEREx-D([1-6])$")
_METRES_TO_UM: Final = 1e6
CACHE_TTL_S: Final = 3600.0
CACHE_SIZE: Final = 256


def sia_params(collection: str, ra_deg: float, dec_deg: float, radius_deg: float) -> dict[str, str]:
    return {
        "COLLECTION": collection,
        "POS": f"circle {ra_deg:.6f} {dec_deg:.6f} {radius_deg:.6f}",
        "RESPONSEFORMAT": "CSV",
    }


class SiaCache:
    """Answers of single collections, kept for an hour. IRSA answered 502 to most SIA requests on 2026-11-15 and
    let one through now and then: a retried search then repeats only the collections that failed, instead of
    needing every collection to answer within one attempt."""

    def __init__(self, ttl_s: float = CACHE_TTL_S, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._answers: OrderedDict[tuple[str, str], tuple[float, str]] = OrderedDict()

    @staticmethod
    def _key(params: Mapping[str, str]) -> tuple[str, str]:
        return params["COLLECTION"], params["POS"]

    def get(self, params: Mapping[str, str]) -> str | None:
        entry = self._answers.get(self._key(params))
        if entry is None or self._clock() - entry[0] > self._ttl_s:
            return None
        return entry[1]

    def put(self, params: Mapping[str, str], text: str) -> None:
        key = self._key(params)
        self._answers[key] = (self._clock(), text)
        self._answers.move_to_end(key)
        if len(self._answers) > CACHE_SIZE:
            self._answers.popitem(last=False)


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
