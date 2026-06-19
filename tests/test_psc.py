"""Smoke tests for map_psc_event."""

from __future__ import annotations

from bods_mapper import map_psc_event, validate_shape


def _event(kind: str, natures, *, ceased_on=None, etag="e1", number="01234567"):
    data = {"etag": etag, "kind": kind, "name": "Jane Q Public", "natures_of_control": natures}
    if ceased_on:
        data["ceased_on"] = ceased_on
    return {
        "resource_kind": "persons-with-significant-control",
        "resource_uri": f"/company/{number}/persons-with-significant-control/individual/{etag}",
        "data": data,
        "event": {"type": "changed", "timepoint": 1, "published_at": "2024-09-04T10:00:00"},
    }


def test_individual_changed_event_maps_to_valid_bods():
    ev = _event("individual-person-with-significant-control", ["ownership-of-shares-25-to-50-percent"])
    stmts = list(map_psc_event(ev))
    assert [s["recordType"] for s in stmts] == ["entity", "person", "relationship"]
    assert validate_shape(stmts) == []
    rel = stmts[-1]
    assert rel["recordStatus"] == "new"
    interest = rel["recordDetails"]["interests"][0]
    assert interest["type"] == "shareholding"
    assert interest["details"] == "Ownership of shares – More than 25% but not more than 50%"
    assert interest["share"] == {"exclusiveMinimum": 25, "maximum": 50}


def test_ceased_event_maps_to_closed_record():
    ev = _event(
        "individual-person-with-significant-control",
        ["ownership-of-shares-25-to-50-percent"],
        ceased_on="2024-09-03",
    )
    stmts = list(map_psc_event(ev))
    rel = [s for s in stmts if s["recordType"] == "relationship"][0]
    assert rel["recordStatus"] == "closed"
    assert rel["recordId"] != rel["statementId"]
    # BODS 0.4 links a record's versions via the shared recordId; the removed
    # replacesStatements field must not be emitted.
    assert "replacesStatements" not in rel
    assert rel["recordDetails"]["interests"][0]["endDate"] == "2024-09-03"
    assert validate_shape(stmts) == []


def test_deleted_event_yields_empty_bundle():
    ev = {"resource_uri": "/company/01234567/persons-with-significant-control/individual/x",
          "event": {"type": "deleted"}}
    assert len(map_psc_event(ev)) == 0


_NOMINEE_CODE = "registered-owner-as-nominee-person-england-wales-registered-overseas-entity"


def test_nominee_event_builds_arrangement_not_bare_interest():
    ev = _event("individual-person-with-significant-control", [_NOMINEE_CODE])
    stmts = list(map_psc_event(ev))

    # entity (overseas entity) + person (nominator) + arrangement entity + 2 rels
    assert [s["recordType"] for s in stmts] == [
        "entity", "person", "entity", "relationship", "relationship"
    ]
    assert validate_shape(stmts) == []

    arrangement = stmts[2]
    assert arrangement["recordDetails"]["entityType"]["type"] == "arrangement"
    assert arrangement["recordDetails"]["entityType"]["subtype"] == "nomination"
    assert arrangement["recordDetails"]["entityType"]["details"]  # CH descriptor preserved
    arrangement_sid = arrangement["statementId"]

    oe_sid = stmts[0]["statementId"]              # overseas entity = nominee
    nominator_person_sid = stmts[1]["statementId"]

    rels = {r["recordDetails"]["interests"][0]["type"]: r for r in stmts[3:]}
    assert set(rels) == {"nominee", "nominator"}

    # nominee = the overseas entity; nominator = the PSC person; both point at the arrangement
    assert rels["nominee"]["recordDetails"]["interestedParty"] == oe_sid
    assert rels["nominee"]["recordDetails"]["subject"] == arrangement_sid
    assert rels["nominee"]["recordDetails"]["interests"][0]["beneficialOwnershipOrControl"] is False
    assert rels["nominator"]["recordDetails"]["interestedParty"] == nominator_person_sid
    assert rels["nominator"]["recordDetails"]["subject"] == arrangement_sid
    assert rels["nominator"]["recordDetails"]["interests"][0]["beneficialOwnershipOrControl"] is True

    # the old (wrong) shape — a bare `nominee` interest on a party->company rel — must not appear
    for r in stmts[3:]:
        assert r["recordDetails"]["subject"] == arrangement_sid


def test_nominee_ceased_closes_both_relationships():
    ev = _event(
        "individual-person-with-significant-control", [_NOMINEE_CODE], ceased_on="2024-09-03"
    )
    stmts = list(map_psc_event(ev))
    rels = [s for s in stmts if s["recordType"] == "relationship"]
    assert len(rels) == 2
    for r in rels:
        assert r["recordStatus"] == "closed"
        assert r["recordDetails"]["interests"][0]["endDate"] == "2024-09-03"
        assert "replacesStatements" not in r
    assert validate_shape(stmts) == []


def test_super_secure_carries_official_descriptor():
    ev = _event("super-secure-person-with-significant-control", [])
    ev["data"]["description"] = "super-secure-persons-with-significant-control"
    stmts = list(map_psc_event(ev))
    assert validate_shape(stmts) == []

    person = [s for s in stmts if s["recordType"] == "person"][0]
    assert person["recordDetails"]["personType"] == "anonymousPerson"

    interest = [s for s in stmts if s["recordType"] == "relationship"][0]["recordDetails"]["interests"][0]
    assert interest["type"] == "unpublishedInterest"
    assert "restrictions on disclosing" in interest["details"]   # official CH text, not "Anonymous PSC"


def test_corporate_psc_is_entity_to_entity():
    ev = _event("corporate-entity-person-with-significant-control", ["voting-rights-75-to-100-percent"])
    ev["data"]["identification"] = {"registration_number": "09999999", "place_registered": "Companies House"}
    stmts = list(map_psc_event(ev))
    assert [s["recordType"] for s in stmts].count("entity") == 2
    rel = [s for s in stmts if s["recordType"] == "relationship"][0]
    assert rel["recordDetails"]["interests"][0]["beneficialOwnershipOrControl"] is False
    assert validate_shape(stmts) == []
