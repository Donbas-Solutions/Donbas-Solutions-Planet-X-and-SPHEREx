"""Resolve the 5 official test targets in SIMBAD and write science/targets.json.

Run from the repo root with the backend venv:  python science/resolve_targets.py

For each target we also compare SIMBAD's J2000 position with the coordinates quoted in the
challenge / research doc and estimate the epoch those coordinates correspond to (offset projected
onto the proper-motion direction). This answers "which epoch are the given coordinates?".
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import astroquery
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import configure_ssl  # noqa: E402

configure_ssl()
from astroquery.simbad import Simbad  # noqa: E402

TARGETS = [
    {
        "id": "barnard",
        "name": "Barnard's Star",
        "simbad_query": "Barnard's star",
        "test": "motion",
        "doc_coords": ("17h57m48.50s", "+04d41m36.1s"),
        "notes": "Saturated in SPHEREx; motion visible as a shifted saturated blob. Centroid unreliable.",
    },
    {
        "id": "eps_ind_b",
        "name": "Epsilon Indi B (Ba/Bb)",
        "simbad_query": "eps Ind B",
        "test": "motion",
        "doc_coords": ("22h04m10.5s", "-56d46m58s"),
        "notes": "Unresolved T1+T6 pair (0.6-0.7 arcsec). Not saturated: best target for measured proper motion. "
        "eps Ind A (V 4.7) is only 6.7 arcmin to the west: its halo enters a 10 arcmin field.",
    },
    {
        "id": "wise0855",
        "name": "WISE 0855-0714",
        "simbad_query": "WISE J085510.83-071442.5",
        "test": "motion",
        "doc_coords": ("08h55m10.831s", "-07d14m42.53s"),
        "notes": "Y dwarf, J ~ 25: invisible at short wavelengths; only D5-D6 stacks have a chance. "
        "Report S/N or an upper limit, never claim a detection below 5 sigma.",
    },
    {
        "id": "rw_aur",
        "name": "RW Aurigae",
        "simbad_query": "RW Aur",
        "test": "brightness",
        "doc_coords": ("05h07m49.46s", "+30d24m04.8s"),
        "notes": "T Tauri star with irregular dimming events: light-curve test.",
    },
    {
        "id": "r_dra",
        "name": "R Draconis",
        "simbad_query": "R Dra",
        "test": "brightness",
        "doc_coords": ("16h32m40.3s", "+66d45m18s"),
        "notes": "Mira variable (~246 d). In the SPHEREx deep field near the NEP (dense time sampling). "
        "Likely saturated: mark, don't measure.",
    },
]


def _num(value: object) -> float | None:
    if value is None or np.ma.is_masked(value):
        return None
    value = float(value)
    return None if np.isnan(value) else value


SIMBAD_SERVERS = ("simbad.cds.unistra.fr", "simbad.harvard.edu")  # primary, mirror


def _simbad() -> tuple[Simbad, str]:
    """First SIMBAD server that answers (the Strasbourg one was down on 2026-11-14)."""
    from astroquery.simbad import conf

    errors = []
    for server in SIMBAD_SERVERS:
        conf.server = server
        try:
            simbad = Simbad()
            simbad.add_votable_fields("pmra", "pmdec", "plx_value", "coo_bibcode")
        except Exception as exc:  # noqa: BLE001 - pyvo raises many unrelated types for an unreachable TAP
            errors.append(f"{server}: {exc.__class__.__name__}")
        else:
            return simbad, server
    raise SystemExit("No SIMBAD server reachable: " + "; ".join(errors))


def main() -> None:
    simbad, server = _simbad()
    print(f"SIMBAD server: {server}")

    out = []
    for t in TARGETS:
        table = simbad.query_object(t["simbad_query"])
        if table is None or len(table) == 0:
            raise SystemExit(f"SIMBAD returned nothing for {t['simbad_query']!r}")
        row = table[0]
        ra, dec = float(row["ra"]), float(row["dec"])
        pmra, pmdec = _num(row["pmra"]), _num(row["pmdec"])
        simbad_c = SkyCoord(ra * u.deg, dec * u.deg)
        doc_c = SkyCoord(*t["doc_coords"], frame="icrs")
        offset = simbad_c.separation(doc_c).arcsec

        doc_epoch = None  # only meaningful for fast movers; slow ones differ by catalog precision only
        if pmra is not None and pmdec is not None and np.hypot(pmra, pmdec) > 500:
            # offset of doc position relative to SIMBAD J2000, in arcsec (east, north)
            d_east = (doc_c.ra - simbad_c.ra).wrap_at(180 * u.deg).to_value(u.arcsec) * np.cos(np.radians(dec))
            d_north = (doc_c.dec - simbad_c.dec).to_value(u.arcsec)
            pm = np.array([pmra, pmdec]) / 1000.0  # arcsec/yr
            doc_epoch = round(2000.0 + float(np.dot([d_east, d_north], pm) / np.dot(pm, pm)), 1)

        out.append(
            {
                "id": t["id"],
                "name": t["name"],
                "test": t["test"],
                "simbad_query": t["simbad_query"],
                "simbad_main_id": str(row["main_id"]),
                "ra": round(ra, 7),
                "dec": round(dec, 7),
                "ref_epoch": 2000.0,
                "pmra": pmra,
                "pmdec": pmdec,
                "parallax": _num(row["plx_value"]),
                "coo_bibcode": str(row["coo_bibcode"]),
                "doc_coords": list(t["doc_coords"]),
                "doc_offset_arcsec": round(offset, 1),
                "doc_epoch_estimate": doc_epoch,
                "notes": t["notes"],
            }
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": f"SIMBAD ({server}) via astroquery {astroquery.__version__}",
        "conventions": "ra/dec: ICRS degrees at ref_epoch (Julian year). pmra includes cos(dec). "
        "pm in mas/yr, parallax in mas. doc_epoch_estimate = epoch at which doc_coords match the PM track.",
        "targets": out,
    }
    path = ROOT / "science" / "targets.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for t in out:
        print(
            f"{t['id']:10s} {t['simbad_main_id']:28s} ra={t['ra']:.5f} dec={t['dec']:+.5f} "
            f'pm=({t["pmra"]}, {t["pmdec"]}) plx={t["parallax"]} doc_offset={t["doc_offset_arcsec"]}" '
            f"doc_epoch~{t['doc_epoch_estimate']}"
        )
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
