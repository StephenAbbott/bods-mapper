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

from .natures import describe_nature, describe_super_secure, is_nominee, parse_nature
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


def _individual_party(source_id: str, number: str, data: dict[str, Any], url: str, pid: str) -> dict[str, Any]:
    ne = data.get("name_elements") or {}
    full_name = data.get("name") or " ".join(
        [ne.get("forename", ""), ne.get("middle_name", ""), ne.get("surname", "")]
    ).strip()

    dob = data.get("date_of_birth")
    birth_date = None
    if isinstance(dob, dict) and "year" in dob:
        birth_date = f"{dob['year']:04d}-{dob['month']:02d}" if "month" in dob else f"{dob['year']:04d}"

    nationalities = [{"name": data["nationality"]}] if data.get("nationality") else []
    return make_person_statement(
        source_id=source_id,
        local_id=f"{number}:psc:{pid}",
        full_name=full_name or "Unknown PSC",
        person_type="knownPerson",
        nationalities=nationalities,
        birth_date=birth_date,
        addresses=_addresses_from(data.get("address"), "service"),
        source_url=url,
    )


def _corporate_party(source_id: str, number: str, data: dict[str, Any], url: str, pid: str) -> dict[str, Any]:
    ident = data.get("identification") or {}
    identifiers = []
    reg_no = (ident.get("registration_number") or "").strip()
    if reg_no:
        identifiers.append({"id": reg_no, "scheme": "unknown", "schemeName": ident.get("place_registered", "")})
    return make_entity_statement(
        source_id=source_id,
        local_id=f"{number}:psc:{pid}",
        name=data.get("name") or "Corporate PSC",
        identifiers=identifiers,
        source_url=url,
    )


def _super_secure_party(source_id: str, number: str, data: dict[str, Any], url: str, pid: str) -> dict[str, Any]:
    # A super-secure PSC is known to CH but all particulars are withheld by court
    # order → anonymousPerson. The official explanation rides on the relationship
    # interest (see map_psc_event), not on a misleading placeholder name.
    return make_person_statement(
        source_id=source_id,
        local_id=f"{number}:anon:{pid}",
        full_name="Super-secure person",
        person_type="anonymousPerson",
        source_url=url,
    )


def _super_secure_code(data: dict[str, Any], natures: list[str]) -> str | None:
    """The CH super-secure code: the PSC's ``description`` field, else a super-
    secure nature code if one is present."""
    return data.get("description") or next(
        (n for n in natures if "super-secure" in (n or "").lower()), None
    )


def map_psc_event(
    event: dict[str, Any],
    *,
    source_id: str = "companies_house",
    stable_psc_id: str | None = None,
    record_status: str | None = None,
    replaces_statement_id: str | None = None,
    end_date: str | None = None,
) -> BODSBundle:
    """Map one CH PSC stream event to a BODS bundle (entity + party + relationship).

    Lifecycle (driven by the calling service's state tracker, since the stream
    itself carries no new/updated/closed):

    * ``stable_psc_id`` — a stable identity for this PSC (e.g. the stream
      ``resource_id``). When given, the party's ``recordId`` is derived from it
      rather than the per-update ``etag``, so a PSC keeps one ``recordId`` across
      its lifecycle. Falls back to ``etag`` for one-shot mapping.
    * ``record_status`` — override the relationship's status ("updated" on a
      re-sighting, "closed" on a deletion). Defaults to "closed" when the event
      carries ``ceased_on``, else "new".
    * ``replaces_statement_id`` — the prior statement this one supersedes.
    * ``end_date`` — interest end date for a deletion-driven close (when there's
      no ``ceased_on`` date).
    """
    result = BODSBundle()
    data = event.get("data")
    number = company_number_from_uri(event.get("resource_uri", ""))
    if not data or not number:
        return result  # deleted / unmappable: caller closes prior record from last-state map

    url = _COMPANY_URL.format(number=number)
    pid = stable_psc_id or data.get("etag") or data.get("name") or "0"
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
        party = _corporate_party(source_id, number, data, url, pid)
        party_type = "entity"
    elif "individual" in kind:
        party = _individual_party(source_id, number, data, url, pid)
        party_type = "person"
    else:
        party = _super_secure_party(source_id, number, data, url, pid)
        party_type = "person"
    result.statements.append(party)

    natures = data.get("natures_of_control") or []
    ceased_on = data.get("ceased_on")
    status = record_status or ("closed" if ceased_on else "new")
    closure_date = end_date or ceased_on
    publication_date = closure_date or data.get("notified_on") or None

    # Nominee (Registered Overseas Entity) arrangements get the proper BODS model:
    # a synthetic `arrangement`/`nomination` entity with `nominator` + `nominee`
    # relationships, not a bare `nominee` interest. The overseas entity (the PSC
    # `entity`) is the registered owner = nominee; the PSC party is the nominator.
    # The held asset is UK land, which BODS 0.4 cannot represent (data-standard
    # issue #752), so the arrangement->asset link is intentionally omitted.
    nominee_natures = [n for n in natures if is_nominee(n)]
    if nominee_natures:
        _add_nominee_arrangement(
            result, source_id=source_id, number=number, pid=pid, url=url,
            nominee_party_sid=entity_sid, nominator_party_sid=party["statementId"],
            descriptor=describe_nature(nominee_natures[0]) or nominee_natures[0],
            status=status, closure_date=closure_date, publication_date=publication_date,
            replaces_statement_id=replaces_statement_id,
        )
        return result

    if "super-secure" in kind:
        # Particulars are withheld by court order → one `unpublishedInterest`
        # carrying CH's official explanatory text, not a bare unknownInterest.
        interests = [{
            "type": "unpublishedInterest",
            "directOrIndirect": "unknown",
            "beneficialOwnershipOrControl": True,
            "details": describe_super_secure(_super_secure_code(data, natures)),
        }]
    else:
        interests = [parse_nature(n) for n in natures] or [
            {"type": "unknownInterest", "directOrIndirect": "unknown", "beneficialOwnershipOrControl": True}
        ]
    if party_type == "entity":
        for interest in interests:
            interest["beneficialOwnershipOrControl"] = False

    if status == "closed" and closure_date:
        for interest in interests:
            interest["endDate"] = closure_date

    rel = make_relationship_statement(
        source_id=source_id,
        local_id=f"{number}:{party['statementId']}",
        subject_statement_id=entity_sid,
        interested_party_statement_id=party["statementId"],
        interests=interests,
        source_url=url,
        publication_date=publication_date,
        record_status=status,
        replaces_statements=[replaces_statement_id] if replaces_statement_id else None,
    )
    result.statements.append(rel)
    return result


def _add_nominee_arrangement(
    result: BODSBundle,
    *,
    source_id: str,
    number: str,
    pid: str,
    url: str,
    nominee_party_sid: str,
    nominator_party_sid: str,
    descriptor: str,
    status: str,
    closure_date: str | None,
    publication_date: str | None,
    replaces_statement_id: str | None,
) -> None:
    """Append the nomination arrangement entity + nominator/nominee relationships.

    Per the BODS nominee modelling guidance, a nominee fact is an Entity Statement
    with ``entityType.type = "arrangement"`` / ``subtype = "nomination"`` joined to
    its parties by relationships whose ``interest.type`` is *only* ``nominator`` or
    ``nominee``. The CH descriptor is preserved on both ``entityType.details`` and
    each ``interest.details``.
    """
    arrangement = make_entity_statement(
        source_id=source_id,
        local_id=f"{number}:nomination:{pid}",
        name="Nominee arrangement",
        entity_type="arrangement",
        entity_subtype="nomination",
        entity_details=descriptor,
        source_url=url,
    )
    result.statements.append(arrangement)
    arrangement_sid = arrangement["statementId"]

    def _interest(interest_type: str, is_bo: bool) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "type": interest_type,
            "directOrIndirect": "direct",
            "beneficialOwnershipOrControl": is_bo,
            "details": descriptor,
        }
        if status == "closed" and closure_date:
            entry["endDate"] = closure_date
        return entry

    # nominee = the registered owner (overseas entity); not the beneficial owner.
    result.statements.append(
        make_relationship_statement(
            source_id=source_id,
            local_id=f"{number}:nominee:{pid}",
            subject_statement_id=arrangement_sid,
            interested_party_statement_id=nominee_party_sid,
            interests=[_interest("nominee", False)],
            source_url=url,
            publication_date=publication_date,
            record_status=status,
            replaces_statements=[replaces_statement_id] if replaces_statement_id else None,
        )
    )
    # nominator = the PSC / beneficial owner on whose behalf the nominee holds.
    result.statements.append(
        make_relationship_statement(
            source_id=source_id,
            local_id=f"{number}:nominator:{pid}",
            subject_statement_id=arrangement_sid,
            interested_party_statement_id=nominator_party_sid,
            interests=[_interest("nominator", True)],
            source_url=url,
            publication_date=publication_date,
            record_status=status,
        )
    )


__all__ = ["map_psc_event", "company_number_from_uri"]
