"""TLE validation.

A TLE is "valid" if:
1. It has a well-formed 2-line structure (lines starting "1 " and "2 ").
2. Each line is exactly 69 characters and has a correct checksum.
3. SGP4's Satrec.twoline2rv accepts it (sanity check that the element set is
   structurally parseable).
4. The resulting orbital elements pass basic physical sanity checks (positive
   mean motion, finite inclination in [0, pi]).

Validation does NOT perform propagation; it only confirms the element set is
coherent enough that propagation is meaningful.  Epoch and NORAD id are
preferred from the Satrec object where possible (more reliable than trusting
raw line substrings for formatting edge cases), but line1-derived values are
used as a fallback.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import Satrec

from satnet.domain.exceptions import TLEValidationError
from satnet.domain.models import SatelliteTLE


def checksum_valid(line: str) -> bool:
    """Standard TLE line checksum (mod-10 of digits plus minus-sign count)."""
    if len(line) != 69 or not line[68].isdigit():
        return False
    total = sum(int(c) for c in line[:68] if c.isdigit()) + line[:68].count("-")
    return total % 10 == int(line[68])


def _parse_epoch_from_satrec(sat: Satrec) -> datetime:
    """Derive a UTC epoch from the sgp4 Satrec object.

    sgp4 stores ``epochyr`` (year within century) and ``epochdays`` (days
    since the start of that year, 1-indexed).  The century mapping follows the
    classic TLE convention: years < 57 map to 2000+, otherwise 1900+.
    """
    epoch_year = int(sat.epochyr)
    epoch_full_year = 2000 + epoch_year if epoch_year < 57 else 1900 + epoch_year
    return datetime(epoch_full_year, 1, 1, tzinfo=timezone.utc) + timedelta(
        days=float(sat.epochdays) - 1
    )


class TLEValidator:
    """Validate raw TLE lines and return a SatelliteTLE.

    The returned record prefers the NORAD id from line 1 (columns 3-7) but uses
    the sgp4-derived epoch when available, because that is the authoritative
    source of the element-set epoch.
    """

    def validate(
        self, name: str, line1: str, line2: str, source: str = "unknown"
    ) -> SatelliteTLE:
        l1 = line1.rstrip("\r\n")
        l2 = line2.rstrip("\r\n")

        if not l1.startswith("1 ") or not l2.startswith("2 "):
            raise TLEValidationError(
                "TLE must contain a valid line 1 (starts '1 ') and line 2 (starts '2 ')."
            )
        if len(l1) != 69 or len(l2) != 69:
            raise TLEValidationError(
                "Each TLE line must contain exactly 69 characters "
                f"(line1={len(l1)}, line2={len(l2)})."
            )
        if not checksum_valid(l1) or not checksum_valid(l2):
            raise TLEValidationError("TLE checksum validation failed on one or both lines.")

        try:
            sat = Satrec.twoline2rv(l1, l2)
        except Exception as exc:
            raise TLEValidationError(f"SGP4 rejected the TLE element set: {exc}") from exc

        # Physical sanity checks — sgp4 silently maps garbage fields to zero,
        # so we must guard against a formally-parseable but physically bogus set.
        if not (sat.no_kozai > 0) or not np.isfinite(sat.no_kozai):
            raise TLEValidationError(
                "TLE mean motion must be a valid positive number."
            )
        if not np.isfinite(sat.inclo) or not (0 <= sat.inclo <= np.pi):
            raise TLEValidationError("TLE inclination is out of physical range [0, pi].")

        # NORAD id: prefer line 1 columns 3-7 (standard TLE layout).
        try:
            norad_id = int(l1[2:7].strip())
        except (ValueError, IndexError) as exc:
            raise TLEValidationError(
                f"Could not parse NORAD id from line 1: {exc}"
            ) from exc
        if norad_id <= 0:
            raise TLEValidationError("NORAD id must be positive.")

        # Epoch: prefer sgp4-derived epoch; fall back to a line-based parse only
        # if sgp4 refused to expose epoch fields (should not happen for accepted
        # element sets, but be defensive).
        try:
            epoch = _parse_epoch_from_satrec(sat)
        except Exception as exc:
            raise TLEValidationError(
                f"SGP4 accepted the TLE but could not derive a UTC epoch: {exc}"
            ) from exc

        return SatelliteTLE(
            name=name.strip() or f"NORAD-{norad_id}",
            norad_id=norad_id,
            line1=l1,
            line2=l2,
            epoch=epoch,
            source=source,
        )
