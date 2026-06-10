"""Country resolution for BODS ``country`` objects.

BODS ``Country`` requires ``name`` and only SHOULD carry a 2-letter ISO 3166-1
code (``maxLength``/``minLength`` 2). We resolve free-text country strings to a
valid alpha-2 code where possible and **omit the code** otherwise, rather than
emit an over-long value that fails schema validation (e.g. real Companies House
PSC addresses with "Great Britain" or "Turkey", which pycountry no longer
resolves).
"""

from __future__ import annotations

from typing import Any

import pycountry

# Native-language / English variants pycountry can't resolve on its own.
_NATIVE_NAMES: dict[str, str] = {
    "England": "GB",
    "Scotland": "GB",
    "Wales": "GB",
    "Northern Ireland": "GB",
    "Great Britain": "GB",
    "United Kingdom": "GB",
    # pycountry renamed Turkey -> Türkiye, so the English name no longer resolves
    "Turkey": "TR",
}


def country_object(value: str) -> dict[str, str] | None:
    """Return a BODS ``{"name", "code"?}`` object, or ``None`` for empty input.

    ``code`` is included only when a valid ISO 3166-1 alpha-2 code can be
    resolved; otherwise the name is preserved and the code omitted.
    """
    if not value:
        return None
    stripped = value.strip()
    upper = stripped.upper()

    c = pycountry.countries.get(alpha_2=upper)
    if c:
        return {"name": c.name, "code": c.alpha_2}
    c = pycountry.countries.get(alpha_3=upper)
    if c:
        return {"name": c.name, "code": c.alpha_2}
    try:
        c = pycountry.countries.lookup(stripped)
        return {"name": c.name, "code": c.alpha_2}
    except LookupError:
        pass

    alpha2 = _NATIVE_NAMES.get(stripped) or _NATIVE_NAMES.get(stripped.title())
    if alpha2:
        c = pycountry.countries.get(alpha_2=alpha2)
        if c:
            return {"name": c.name, "code": c.alpha_2}

    # Unresolvable — keep the name, omit the (would-be invalid) code.
    return {"name": stripped}


def address(type_: str, text: str, country_code: str = "") -> dict[str, Any]:
    """Build a single BODS address dict with an optional resolved country."""
    d: dict[str, Any] = {"type": type_, "address": text}
    co = country_object(country_code)
    if co:
        d["country"] = co
    return d
