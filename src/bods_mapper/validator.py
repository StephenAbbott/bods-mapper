"""Lightweight BODS v0.4 shape checks.

A fast sanity check (required fields, valid enums, resolvable relationship
references) — not a full conformance test. For authoritative validation run the
output through ``lib-cove-bods``.
"""

from __future__ import annotations

from typing import Any, Iterable

VALID_RECORD_TYPES = {"entity", "person", "relationship"}
VALID_RECORD_STATUSES = {"new", "updated", "closed"}
VALID_INTEREST_TYPES = {
    "shareholding", "votingRights", "appointmentOfBoard", "otherInfluenceOrControl",
    "seniorManagingOfficial", "settlor", "trustee", "protector",
    "beneficiaryOfLegalArrangement", "rightsToSurplusAssetsOnDissolution",
    "rightsToProfitOrIncome", "rightsGrantedByContract",
    "conditionalRightsGrantedByContract", "controlViaCompanyRulesOrArticles",
    "controlByLegalFramework", "boardMember", "boardChair", "unknownInterest",
    "unpublishedInterest", "enjoymentAndUseOfAssets",
    "rightToProfitOrIncomeFromAssets", "nominee", "nominator",
}


def _is_unspecified(party: Any) -> bool:
    return isinstance(party, dict) and ("reason" in party or "unspecifiedReason" in party)


def validate_shape(statements: Iterable[dict[str, Any]]) -> list[str]:
    """Return a list of human-readable issues. Empty means OK."""
    statements = list(statements)
    known_ids: set[str | None] = set()
    for s in statements:
        known_ids.add(s.get("statementId"))
        known_ids.add(s.get("recordId"))

    issues: list[str] = []
    for s in statements:
        sid = s.get("statementId", "?")
        for key in ("statementId", "recordId", "recordType", "recordStatus", "recordDetails"):
            if key not in s:
                issues.append(f"{sid}: missing {key}")
        rt = s.get("recordType")
        if rt not in VALID_RECORD_TYPES:
            issues.append(f"{sid}: bad recordType {rt!r}")
        if s.get("recordStatus") not in VALID_RECORD_STATUSES:
            issues.append(f"{sid}: bad recordStatus {s.get('recordStatus')!r}")
        rd = s.get("recordDetails") or {}
        if rt == "relationship":
            for party_key in ("subject", "interestedParty"):
                party = rd.get(party_key)
                if _is_unspecified(party):
                    continue
                if party not in known_ids:
                    issues.append(f"{sid}: {party_key} references unknown statement {party!r}")
            for interest in rd.get("interests") or []:
                it = interest.get("type")
                if it not in VALID_INTEREST_TYPES:
                    issues.append(f"{sid}: bad interest type {it!r}")
    return issues


__all__ = ["validate_shape", "VALID_INTEREST_TYPES"]
