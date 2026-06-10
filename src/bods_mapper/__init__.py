"""bods-mapper — Companies House PSC data -> BODS v0.4.

Shared mapping core extracted from OpenCheck, used by both OpenCheck and the
bods-stream live demo so the two can't drift apart.
"""

from __future__ import annotations

from .countries import country_object
from .natures import describe_nature, parse_nature
from .natures_data import PSC_NATURE_DESCRIPTIONS
from .psc import company_number_from_uri, map_psc_event
from .statements import (
    BODSBundle,
    make_entity_statement,
    make_person_statement,
    make_relationship_statement,
    stable_id,
)
from .validator import validate_shape

__version__ = "0.1.0"

__all__ = [
    "map_psc_event",
    "company_number_from_uri",
    "parse_nature",
    "describe_nature",
    "PSC_NATURE_DESCRIPTIONS",
    "country_object",
    "BODSBundle",
    "make_entity_statement",
    "make_person_statement",
    "make_relationship_statement",
    "stable_id",
    "validate_shape",
]
