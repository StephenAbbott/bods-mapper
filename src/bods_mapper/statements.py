"""BODS v0.4 statement factories and the bundle container.

Deterministic statement/record IDs are derived from a source id plus a stable
local key, so re-mapping the same input always yields the same IDs. ``recordId``
is stable across an element's lifecycle (new -> updated -> closed) while each
``statementId`` is unique per statement, per the BODS *Information updates* and
*Record identifiers* modelling requirements.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable

from .countries import country_object

BODS_VERSION = "0.4"
DEFAULT_PUBLISHER = "bods-stream"


def stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"bods-stream-{digest[:24]}"


def _today() -> str:
    return date.today().isoformat()


def _publication_details(publication_date: str | None = None, publisher: str = DEFAULT_PUBLISHER) -> dict[str, Any]:
    return {
        "bodsVersion": BODS_VERSION,
        "publicationDate": publication_date or _today(),
        "publisher": {"name": publisher},
    }


def _source_block(source_id: str, source_url: str | None, description: str) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": ["officialRegister"],
        "description": description,
        "retrievedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if source_url:
        block["url"] = source_url
    return block


@dataclass
class BODSBundle:
    """An ordered collection of BODS statements."""

    statements: list[dict[str, Any]] = field(default_factory=list)

    def __iter__(self):
        return iter(self.statements)

    def __len__(self) -> int:
        return len(self.statements)


def make_entity_statement(
    *,
    source_id: str,
    local_id: str,
    name: str,
    jurisdiction: tuple[str, str] | None = None,
    identifiers: Iterable[dict[str, str]] = (),
    founding_date: str | None = None,
    dissolution_date: str | None = None,
    addresses: Iterable[dict[str, str]] = (),
    entity_type: str = "registeredEntity",
    entity_subtype: str | None = None,
    entity_details: str | None = None,
    source_url: str | None = None,
    source_description: str = "UK Companies House",
    publication_date: str | None = None,
) -> dict[str, Any]:
    statement_id = stable_id(source_id, "entity", local_id)
    record_id = statement_id
    entity_type_obj: dict[str, Any] = {"type": entity_type}
    if entity_subtype:
        entity_type_obj["subtype"] = entity_subtype
    if entity_details:
        entity_type_obj["details"] = entity_details
    record_details: dict[str, Any] = {
        "isComponent": False,
        "entityType": entity_type_obj,
        "name": name,
        "identifiers": list(identifiers),
    }
    if jurisdiction:
        record_details["jurisdiction"] = {"name": jurisdiction[0], "code": jurisdiction[1]}
    if founding_date:
        record_details["foundingDate"] = founding_date
    if dissolution_date:
        record_details["dissolutionDate"] = dissolution_date
    addresses = list(addresses)
    if addresses:
        record_details["addresses"] = addresses
    return {
        "statementId": statement_id,
        "recordId": record_id,
        "declarationSubject": record_id,
        "recordType": "entity",
        "recordStatus": "new",
        "statementDate": _today(),
        "publicationDetails": _publication_details(publication_date),
        "recordDetails": record_details,
        "source": _source_block(source_id, source_url, source_description),
    }


def make_person_statement(
    *,
    source_id: str,
    local_id: str,
    full_name: str,
    person_type: str = "knownPerson",
    nationalities: Iterable[dict[str, str]] = (),
    birth_date: str | None = None,
    addresses: Iterable[dict[str, str]] = (),
    source_url: str | None = None,
    source_description: str = "UK Companies House",
    publication_date: str | None = None,
) -> dict[str, Any]:
    statement_id = stable_id(source_id, "person", local_id)
    record_id = statement_id
    record_details: dict[str, Any] = {
        "isComponent": False,
        "personType": person_type,
        "names": [{"type": "legal", "fullName": full_name}],
    }
    nationalities = list(nationalities)
    if nationalities:
        record_details["nationalities"] = nationalities
    if birth_date:
        record_details["birthDate"] = birth_date
    addresses = list(addresses)
    if addresses:
        record_details["addresses"] = addresses
    return {
        "statementId": statement_id,
        "recordId": record_id,
        "declarationSubject": record_id,
        "recordType": "person",
        "recordStatus": "new",
        "statementDate": _today(),
        "publicationDetails": _publication_details(publication_date),
        "recordDetails": record_details,
        "source": _source_block(source_id, source_url, source_description),
    }


def make_relationship_statement(
    *,
    source_id: str,
    local_id: str,
    subject_statement_id: str,
    interested_party_statement_id: str,
    interests: Iterable[dict[str, Any]] = (),
    source_url: str | None = None,
    source_description: str = "UK Companies House",
    publication_date: str | None = None,
    record_status: str = "new",
    replaces_statements: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Build a relationship statement.

    ``recordId`` is derived purely from ``local_id`` so it is stable across the
    record's lifecycle. For non-``new`` lifecycle stages the ``statementId`` is
    varied (status + publication date) so the closed/updated statement is a
    distinct statement, and ``replacesStatements`` auto-points at the original
    ``new`` statement unless the caller supplies an explicit list.
    """
    record_id = stable_id(source_id, "relationship-record", local_id)
    if record_status == "new":
        statement_id = stable_id(source_id, "relationship", local_id)
        replaced: list[str] | None = list(replaces_statements) if replaces_statements else None
    else:
        statement_id = stable_id(source_id, "relationship", local_id, record_status, publication_date or "")
        replaced = (
            list(replaces_statements)
            if replaces_statements is not None
            else [stable_id(source_id, "relationship", local_id)]
        )
    statement: dict[str, Any] = {
        "statementId": statement_id,
        "recordId": record_id,
        "declarationSubject": subject_statement_id,
        "recordType": "relationship",
        "recordStatus": record_status,
        "statementDate": _today(),
        "publicationDetails": _publication_details(publication_date),
        "recordDetails": {
            "isComponent": False,
            "subject": subject_statement_id,
            "interestedParty": interested_party_statement_id,
            "interests": list(interests),
        },
        "source": _source_block(source_id, source_url, source_description),
    }
    if replaced:
        statement["replacesStatements"] = replaced
    return statement


__all__ = [
    "BODSBundle",
    "stable_id",
    "make_entity_statement",
    "make_person_statement",
    "make_relationship_statement",
    "country_object",
]
