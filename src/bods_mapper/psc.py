"""Map a Companies House PSC streaming event to BODS v0.4 statements.

A PSC stream event wraps a single PSC resource in ``data`` plus an ``event``
envelope (``type`` changed|deleted, ``timepoint``, ...). The company number is
carried in ``resource_uri`` (the PSC payload itself has no company number).

``map_psc_event`` produces, for one event:
  * the subject company entity statement,
  * the interested party (person / corporate entity / anonymous super-secure),
  * an ownership-or-control relationship statement.

When the PSC carries ``ceased_on``, the relationship is emitted with
``recordStatus: "closed"`` (interest ``endDate`` = ceased date,
``replacesStatements`` -> the original ``new``) per the BODS Information-updates
modelling rules. ``deleted`` events carry no ``data`` and yield an empty bundle;
the calling service is responsible for closing the prior record from its own
last-state map.
"""

from __future__ import annotations

from typing import Any

from .natures import parse_nature
from .statements import (
    BODSBundle,
    make_entity_statement,
    make_person_statement,
    make_relationship_statement,
)
from .countries import address as _address

_COMPANY_URL = "https://find-and-update.company-information.service.gov.uk/company/{number}"
_UK = ("United Kingdom", "GB")


def company_number_from_uri(resource_uri: str) -> str | None:
    """Extract the company number from a PSC ``resource_uri``.

    e.g. ``/company/01234567/persons-with-significant-control/individual/x`` -> ``01234567``.
    """
    parts = [p for p in (resource_uri or "").split("/") if p]
    if "company" in parts:
        i = parts.index("company")
        if i + 1 < len(parts):
            return parts[i + 1]
    return None


def _addresses_from(block: dict[str, Any] | None, addr_type: str) -> list[dict[str, str]]:
    block = block or {}
    parts = [
        block.get("premises"),
        block.get("address_line_1"),
        block.get("address_line_2"),
        block.get("locality"),
        block.get("region"),
        block.get("postal_code"),
        block.get("country"),
    ]
    joined = ", ".join([p for p in parts if p])
    return [_address(addr_type, joined, block.get("country", ""))] if joined else []


def _individual_party(source_id: str, number: str, data: dict[str, Any], url: str) -> dict[str, Any]:
    ne = data.get("name_elements") or {}
    full_name = data.get("name") or " ".join(
        [ne.get("forename", ""), ne.get("middle_name", ""), ne.get("surname", "")]
    ).strip()

    dob = data.get("date_of_birth")
    birth_date = None
    if isinstance(dob, dict) and "year" in dob:
        birth_date = f"{dob['year']:04d}-{dob['month']:02d}" if "month" in dob else f"{dob['year']:04d}"

    nationalities = [{"name": data["nationality"]}] if data.get("nationality") else []
    etag = data.get("etag") or full_name
    return make_person_statement(
        source_id=source_id,
        local_id=f"{number}:psc:{etag}",
        full_name=full_name or "Unknown PSC",
        person_type="knownPerson",
        nationalities=nationalities,
        birth_date=birth_date,
        addresses=_addresses_from(data.get("address"), "service"),
        source_url=url,
    )


def _corporate_party(source_id: str, number: str, data: dict[str, Any], url: str) -> dict[str, Any]:
    ident = data.get("identification") or {}
    identifiers = []
    reg_no = (ident.get("registration_number") or "").strip()
    if reg_no:
        identifiers.append({"id": reg_no, "scheme": "unknown", "schemeName": ident.get("place_registered", "")})
    etag = data.get("etag") or data.get("name", "")
    return make_entity_statement(
        source_id=source_id,
        local_id=f"{number}:psc:{etag}",
        name=data.get("name") or "Corporate PSC",
        identifiers=identifiers,
        source_url=url,
    )


def _super_secure_party(source_id: str, number: str, data: dict[str, Any], url: str) -> dict[str, Any]:
    # TODO: carry the official super_secure_description text (see opencheck ticket).
    return make_person_statement(
        source_id=source_id,
        local_id=f"{number}:anon:{data.get('etag', '0')}",
        full_name=data.get("name", "Anonymous PSC"),
        person_type="anonymousPerson",
        source_url=url,
    )


def map_psc_event(event: dict[str, Any], *, source_id: str = "companies_house") -> BODSBundle:
    """Map one CH PSC stream event to a BODS bundle (entity + party + relationship)."""
    result = BODSBundle()
    data = event.get("data")
    number = company_number_from_uri(event.get("resource_uri", ""))
    if not data or not number:
        return result  # deleted / unmappable: caller closes prior record from last-state map

    url = _COMPANY_URL.format(number=number)
    # The PSC payload carries no company name; enrichment (a REST profile lookup)
    # is the calling service's choice. Fall back to a stable placeholder.
    entity = make_entity_statement(
        source_id=source_id,
        local_id=number,
        name=data.get("company_name") or f"Company {number}",
        jurisdiction=_UK,
        identifiers=[{"id": number, "scheme": "GB-COH", "schemeName": "Companies House"}],
        source_url=url,
    )
    result.statements.append(entity)
    entity_sid = entity["statementId"]

    kind = (data.get("kind") or "").lower()
    if "corporate-entity" in kind or "legal-person" in kind:
        party = _corporate_party(source_id, number, data, url)
        party_type = "entity"
    elif "individual" in kind:
        party = _individual_party(source_id, number, data, url)
        party_type = "person"
    else:
        party = _super_secure_party(source_id, number, data, url)
        party_type = "person"
    result.statements.append(party)

    natures = data.get("natures_of_control") or []
    interests = [parse_nature(n) for n in natures] or [
        {"type": "unknownInterest", "directOrIndirect": "unknown", "beneficialOwnershipOrControl": True}
    ]
    if party_type == "entity":
        for interest in interests:
            interest["beneficialOwnershipOrControl"] = False

    ceased_on = data.get("ceased_on")
    if ceased_on:
        for interest in interests:
            interest["endDate"] = ceased_on

    rel = make_relationship_statement(
        source_id=source_id,
        local_id=f"{number}:{party['statementId']}",
        subject_statement_id=entity_sid,
        interested_party_statement_id=party["statementId"],
        interests=interests,
        source_url=url,
        publication_date=(ceased_on or data.get("notified_on") or None),
        record_status="closed" if ceased_on else "new",
    )
    result.statements.append(rel)
    return result


__all__ = ["map_psc_event", "company_number_from_uri"]
