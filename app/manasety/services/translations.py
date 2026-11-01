"""Copy English text into the database, and list the Arabic text that still has no translation.

Only empty English fields are filled, so anything edited from the dashboard is never overwritten,
and Arabic content is never changed. A section with an untranslated string stays hidden in English
rather than showing a half-empty block.
"""
from __future__ import annotations

from typing import Any, Iterable

from ..extensions import db
from ..i18n import AR_RE, catalog, translate_text, translate_tree
from ..models import (Author, CaseStudy, Category, Client, DisplayFile, Fact, FaqItem, Feature, Media, Page, Section,
                      SideCard, Tag)
from ..settings_store import get_setting, set_setting

_MODEL_FIELDS: tuple[tuple[Any, tuple[str, ...]], ...] = (
    (Feature, ("name", "description")),
    (FaqItem, ("question", "answer_html")),
    (CaseStudy, ("anonymous_label", "challenge", "built", "working_now")),
    (Client, ("name", "description")),
    (DisplayFile, ("display_name",)),
    (Media, ("alt",)),
)
# No English column: these are looked up in the dictionary when rendered.
_LOOKUP_FIELDS: tuple[tuple[Any, tuple[str, ...]], ...] = (
    (Category, ("name", "description")), (Tag, ("name",)), (Author, ("name", "job_title", "bio")), (Fact, ("label",)),
    (DisplayFile, ("description",)),
    (SideCard, ("title", "text", "button_label")),
)


def _fill_block(block: Any, table: dict[str, str], missing: set[str]) -> Any:
    """A {"ar": …, "en": …} value with English added when it is empty and every string has a translation."""
    if not isinstance(block, dict) or block.get("en") or not block.get("ar"):
        return block
    gaps: set[str] = set()
    english = translate_tree(block["ar"], table, gaps)
    if gaps:
        missing |= gaps
        return block
    return {**block, "en": english}


def _columns(rows: Iterable[Any], fields: tuple[str, ...]) -> Iterable[tuple[Any, str, str]]:
    for row in rows:
        for field in fields:
            value = getattr(row, field, "") or ""
            if AR_RE.search(value):
                yield row, field, value


def fill_english(extra: dict[str, str] | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Fill every empty English field that has a translation. Returns counts and what is still missing.

    An explicit action: English emptied by hand is filled again. With dry_run nothing is saved.
    """
    table = {**catalog(), **(extra or {})}
    missing: set[str] = set()
    filled = 0

    for section in db.session.query(Section).all():
        new = _fill_block(section.content or {}, table, missing)
        if new != (section.content or {}):
            section.content = new
            filled += 1

    for page in db.session.query(Page).all():
        if page.published_snapshot:
            snapshot = [{**s, "content": _fill_block(s.get("content") or {}, table, missing)} for s in page.published_snapshot]
            changed = sum(a != b for a, b in zip(snapshot, page.published_snapshot))
            if changed:
                page.published_snapshot = snapshot
                filled += changed
        for field in ("seo", "published_seo"):
            value = getattr(page, field)
            new_seo = _fill_block(value, table, missing)
            if new_seo != value:
                setattr(page, field, new_seo)
                filled += 1

    for model, fields in _MODEL_FIELDS:
        for row, field, value in _columns(db.session.query(model).all(), fields):
            if getattr(row, f"{field}_en", None):
                continue
            english = translate_text(value, table)
            if english is None:
                missing.add(value)
            else:
                setattr(row, f"{field}_en", english)
                filled += 1

    for model, fields in _LOOKUP_FIELDS:
        for _row, _field, value in _columns(db.session.query(model).all(), fields):
            if translate_text(value, table) is None:
                missing.add(value)

    if dry_run:
        db.session.rollback()
    else:
        db.session.commit()
    return {"filled": filled, "missing": sorted(missing)}


def import_translations(data: dict[str, str]) -> int:
    """Keep translations from a reviewed file (Arabic → English), then fill the database from them."""
    clean = {k: v.strip() for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}
    current = get_setting("translations_en")
    set_setting("translations_en", {**(current if isinstance(current, dict) else {}), **clean})
    db.session.commit()
    return len(clean)
