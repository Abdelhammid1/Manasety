"""Canonical page <title>: every public page carries the brand "\u0645\u0646\u0635\u062a\u064a - Manasety"."""
import re

from markupsafe import Markup

_AR = "\u0645\u0646\u0635\u062a\u064a"
BRAND = _AR + " - Manasety"
_BRAND_FORMS = {_AR, "manasety", BRAND.lower(), _AR + "-manasety"}


def _is_brand(seg: str) -> bool:
    return seg.strip().lower() in _BRAND_FORMS


def brand_title(value) -> Markup:
    """Brand first -> "BRAND | rest"; brand in the middle -> "before | BRAND"; brand last/missing -> "title | BRAND"."""
    text = str(value).strip()
    parts = [p.strip() for p in re.split(r"\s*\|\s*", text) if p.strip()]
    if not parts:
        return Markup(BRAND)
    idx = next((i for i, p in enumerate(parts) if _is_brand(p)), None)
    if idx == 0:
        out = " | ".join([BRAND] + [p for p in parts[1:] if not _is_brand(p)])
    elif idx is None:
        out = " | ".join(parts + [BRAND])
    else:
        out = " | ".join(parts[:idx] + [BRAND])
    return Markup(out)
