# bods-mapper

Map UK **Companies House PSC** (persons with significant control) data to the
**[Beneficial Ownership Data Standard (BODS) v0.4](https://standard.openownership.org/en/0.4.0/)**.

This is the shared mapping core extracted from
[OpenCheck](https://github.com/StephenAbbott/opencheck), so OpenCheck and the
[bods-stream](https://github.com/StephenAbbott/bods-stream) live demo use one
canonical mapper and can't drift apart.

## What it does

Given a single Companies House PSC **streaming event** (the `data` block is the
same resource the REST PSC endpoint returns), `map_psc_event` emits BODS v0.4:

- the **subject company** entity statement,
- the **interested party** — a person (individual PSC), an entity (corporate /
  legal-person PSC), or an `anonymousPerson` (super-secure PSC),
- an **ownership-or-control relationship** statement.

Highlights:

- **All 86 official `natures_of_control` codes** map to a valid BODS
  `interestType`, and each carries the official Companies House short
  descriptor in `interest.details`.
- **Cessation lifecycle** — a ceased PSC produces a relationship with
  `recordStatus: "closed"` (stable `recordId`, distinct `statementId`,
  `interest.endDate`, and `replacesStatements` → the original `new`), per the
  BODS *Information updates* / *Record identifiers* modelling rules.
- **Robust country handling** — emits a BODS `Country` `code` only when a valid
  2-letter ISO code resolves (never an over-long value).

## Install

```bash
pip install -e .          # or: uv add --editable /path/to/bods-mapper
```

Requires Python ≥ 3.10 and `pycountry`.

## Usage

```python
from bods_mapper import map_psc_event, validate_shape

event = {
    "resource_uri": "/company/01234567/persons-with-significant-control/individual/abc",
    "data": {
        "etag": "abc", "kind": "individual-person-with-significant-control",
        "name": "Jane Q Public", "nationality": "British",
        "natures_of_control": ["ownership-of-shares-25-to-50-percent"],
    },
    "event": {"type": "changed", "timepoint": 1},
}

bundle = map_psc_event(event)
statements = list(bundle)          # entity + person + relationship
assert validate_shape(statements) == []
```

For authoritative validation, run the output through
[`lib-cove-bods`](https://github.com/openownership/lib-cove-bods).

## Public API

`map_psc_event`, `company_number_from_uri`, `parse_nature`, `describe_nature`,
`PSC_NATURE_DESCRIPTIONS`, `country_object`, the statement factories
(`make_entity_statement`, `make_person_statement`, `make_relationship_statement`),
`BODSBundle`, `stable_id`, `validate_shape`.

## Tests

```bash
PYTHONPATH=src python -m pytest
```

## Licence

Code: [MIT](LICENSE). The vendored Companies House nature descriptors
(`natures_data.py`) are public sector information licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
