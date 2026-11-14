"""SPHEREx FLAGS bitmask (int32).

Bit names and descriptions come from the FLAGS extension header (MSKNnnnn / MSKDnnnn cards),
checked on a QR3 file with pipeline tag l2b-v27 on 2026-11-14. Always prefer the header of the
file at hand (`flag_bits_from_header`) — the defaults below are only a fallback and the source
of the group / masking policy.

Groups:
  bad         — unusable data: masked in stacks
  saturation  — saturated or nonlinear: masked in stacks, shown as "saturated" in the UI
  artifact    — instrumental artifacts: shown as overlay, NOT masked (masking could hide real sources)
  info        — informational (e.g. SOURCE = pixel belongs to a known source): never masked
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import FlagBit, FlagGroup

_DEFAULTS: tuple[tuple[int, str, str, FlagGroup], ...] = (
    (0, "TRANSIENT", "Transient detected during SUR", "bad"),
    (1, "OVERFLOW", "Overflow detected during SUR", "saturation"),
    (2, "SUR_ERROR", "Error in onboard processing", "bad"),
    (6, "NONFUNC", "Permanently unusable", "bad"),
    (7, "DICHROIC", "Low efficiency due to dichroic", "info"),
    (9, "MISSING_DATA", "Onboard data lost", "bad"),
    (10, "HOT", "Hot pixel", "bad"),
    (11, "COLD", "Anomalously low signal", "bad"),
    (12, "FULLSAMPLE", "Pixel full sample history is available", "info"),
    (14, "PHANMISS", "Phantom correction was not applied", "artifact"),
    (15, "NONLINEAR", "Nonlinearity correction cannot be applied reliably", "saturation"),
    (17, "PERSIST", "Persistent charge above threshold", "bad"),
    (19, "OUTLIER", "Pixel flagged by Detect Outliers", "bad"),
    (20, "CROSSTALK", "Pixel affected by crosstalk.", "artifact"),
    (21, "SOURCE", "Pixel mapped to a known source", "info"),
    (22, "GHOST", "Affected by a bright source inside the exposure", "artifact"),
    (23, "GHOST_FPA", "Affected by a bright source on another detector", "artifact"),
    (24, "GHOST_EXT", "Pixel affected by a bright source outside FOV", "artifact"),
    (25, "STREAK", "Pixel affected by a streak", "artifact"),
    (26, "BLOOM", "Pixel part of a bloom artifact", "artifact"),
    (27, "SNOWBALL", "Pixel part of a snowball artifact", "bad"),
    (28, "HALO", "Pixel part of a transient halo", "artifact"),
)

_MASKED_GROUPS: frozenset[FlagGroup] = frozenset({"bad", "saturation"})
_GROUP_BY_NAME: dict[str, FlagGroup] = {name: group for _, name, _, group in _DEFAULTS}


def _bit(bit: int, name: str, description: str, group: FlagGroup) -> FlagBit:
    return FlagBit(bit=bit, name=name, description=description, group=group, mask_in_stack=group in _MASKED_GROUPS)


DEFAULT_FLAG_BITS: tuple[FlagBit, ...] = tuple(_bit(*row) for row in _DEFAULTS)


def flag_bits_from_header(header: Mapping[str, Any]) -> list[FlagBit]:
    """Read MSKNnnnn/MSKDnnnn cards; unknown names fall into the 'artifact' group (shown, not masked)."""
    bits: list[FlagBit] = []
    for key in header:
        if not (isinstance(key, str) and key.startswith("MSKN") and key[4:].isdigit()):
            continue
        n = int(key[4:])
        name = str(header[key]).strip()
        description = str(header.get(f"MSKD{n:04d}", "")).strip()
        bits.append(_bit(n, name, description, _GROUP_BY_NAME.get(name, "artifact")))
    return sorted(bits, key=lambda b: b.bit) or list(DEFAULT_FLAG_BITS)


def stack_mask_bits(bits: list[FlagBit] | tuple[FlagBit, ...] = DEFAULT_FLAG_BITS) -> int:
    """Bitmask of planes that must be excluded when stacking."""
    mask = 0
    for b in bits:
        if b.mask_in_stack:
            mask |= 1 << b.bit
    return mask
