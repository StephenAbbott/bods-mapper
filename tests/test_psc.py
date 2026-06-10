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
    assert rel["replacesStatements"]
    assert rel["recordDetails"]["interests"][0]["endDate"] == "2024-09-03"
    assert validate_shape(stmts) == []


def test_deleted_event_yields_empty_bundle():
    ev = {"resource_uri": "/company/01234567/persons-with-significant-control/individual/x",
          "event": {"type": "deleted"}}
    assert len(map_psc_event(ev)) == 0


def test_corporate_psc_is_entity_to_entity():
    ev = _event("corporate-entity-person-with-significant-control", ["voting-rights-75-to-100-percent"])
    ev["data"]["identification"] = {"registration_number": "09999999", "place_registered": "Companies House"}
    stmts = list(map_psc_event(ev))
    assert [s["recordType"] for s in stmts].count("entity") == 2
    rel = [s for s in stmts if s["recordType"] == "relationship"][0]
    assert rel["recordDetails"]["interests"][0]["beneficialOwnershipOrControl"] is False
    assert validate_shape(stmts) == []
