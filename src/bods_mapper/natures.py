"""Companies House ``natures_of_control`` -> BODS v0.4 interest entries.

All 86 official CH codes map to a valid BODS ``interestType`` and carry the
official short descriptor in ``interest.details``. Nominee codes intentionally
stay as ``otherInfluenceOrControl`` pending a proper ``arrangement`` model.
"""

from __future__ import annotations

import re
from typing import Any

from .natures_data import describe_nature

# Prefix -> BODS interestType. Order matters: first startswith() wins.
_INTEREST_PREFIX = {
    "ownership-of-shares": "shareholding",
    "voting-rights": "votingRights",
    "right-to-appoint-and-remove-directors": "appointmentOfBoard",
    "right-to-appoint-and-remove-members": "appointmentOfBoard",
    # Scottish-partnership codes use the singular "person"; the singular prefix
    # matches singular and (any) plural form via startswith.
    "right-to-appoint-and-remove-person": "appointmentOfBoard",
    "right-to-share-surplus-assets": "rightsToSurplusAssetsOnDissolution",
    "part-right-to-share-surplus-assets": "rightsToSurplusAssetsOnDissolution",
    "significant-influence-or-control": "otherInfluenceOrControl",
    # NOTE: registered-owner-as-nominee-* is NOT mapped to `nominee` here. BODS
    # requires nominee arrangements to be modelled via an `arrangement`
    # (subtype `nomination`) entity with nominator/nominee relationships, not a
    # bare `nominee` interest. These fall through to otherInfluenceOrControl;
    # the descriptor in `details` preserves the meaning.
}

_SHARE_BAND_RE = re.compile(r"(\d+)-to-(\d+)-percent")


def parse_nature(nature: str) -> dict[str, Any]:
    """Return a BODS ``interests`` entry for one PSC nature-of-control code."""
    lowered = nature.lower()
    interest_type = "otherInfluenceOrControl"
    for prefix, mapped in _INTEREST_PREFIX.items():
        if lowered.startswith(prefix):
            interest_type = mapped
            break

    entry: dict[str, Any] = {
        "type": interest_type,
        "directOrIndirect": "direct",
        "beneficialOwnershipOrControl": True,
        "details": describe_nature(nature) or nature,
    }

    band = _SHARE_BAND_RE.search(lowered)
    if band:
        entry["share"] = {"exclusiveMinimum": int(band.group(1)), "maximum": int(band.group(2))}
    elif "75-to-100-percent" in lowered:
        entry["share"] = {"exclusiveMinimum": 75, "maximum": 100}

    return entry


__all__ = ["parse_nature", "describe_nature"]
