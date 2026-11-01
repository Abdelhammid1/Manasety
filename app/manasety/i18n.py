"""Arabic/English: which language this request is in, translated labels and settings, and localized URLs.

Arabic is the source language: with no /en/ prefix everything renders exactly as before.
English pages share the same templates; only the text comes from English fields.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from flask import g, has_request_context, request
from flask_login import current_user

from .extensions import db
from .i18n_catalog import CONTENT, UI
from .models import Article, FaqItem, Page, utcnow
from .settings_store import get_setting

AR_RE = re.compile(r"[؀-ۿ]")

# Settings whose value is Arabic text. In English they read from "<key>_en"; empty means "not translated",
# so the templates fall through to their general default instead of showing Arabic.
TRANSLATED_SETTINGS = {
    "footer_brand", "footer_about", "footer_note", "footer_social_text", "footer_tagline", "nav", "nav_cta_label",
    "footer_links", "thank_you_title", "thank_you_text", "whatsapp_prefill", "whatsapp_bubble", "cookie_banner_text",
    "blog_title", "blog_description", "blog_title_biz", "blog_description_biz", "nav_biz", "nav_cta_label_biz",
    "footer_about_biz", "footer_tagline_biz", "whatsapp_prefill_biz", "extra_pages", "nav_biz_pages", "nav_institutes",
    "nav_cta_label_institutes", "whatsapp_prefill_institutes",
}
_PAIRED_SETTINGS = {"brand_name_ar": "brand_name_en", "legal_name_ar": "legal_name_en", "address_ar": "address_en"}

# Fields of a per-page layout override that hold Arabic text; they apply only to the Arabic page.
LAYOUT_TEXT_KEYS = ("nav", "cta_label", "footer_about", "footer_tagline", "footer_pages", "whatsapp", "whatsapp_bubble")

_ALWAYS_EN = ("faq", "files", "thank-you")


def current_lang() -> str:
    if not has_request_context():
        return "ar"
    lang = g.get("lang")
    if lang:
        return lang
    return "en" if request.path == "/en" or request.path.startswith("/en/") else "ar"


def plain_path() -> str:
    """The request path without the /en prefix: page logic is the same in both languages."""
    path = request.path
    if path == "/en" or path.startswith("/en/"):
        return path[3:] or "/"
    return path


def _lookup(text: str) -> Optional[str]:
    """Same order as catalog(): a reviewed translation from the database beats the built-in copy."""
    extra = get_setting("translations_en")
    if isinstance(extra, dict) and extra.get(text):
        return extra[text]
    return CONTENT.get(text) or UI.get(text)


def t(text: Any) -> Any:
    """English for a fixed label or a database value with no English column. Arabic stays as written."""
    if current_lang() != "en" or not text:
        return text
    return _lookup(str(text)) or text


def t_or_empty(text: Any) -> Any:
    """For descriptions and bios: on an English page they stay hidden until translated, never shown in Arabic."""
    if current_lang() != "en" or not text:
        return text
    return _lookup(str(text)) or ""


def loc(obj: Any, field: str) -> Any:
    """`field` of a model in the current language: `<field>_en` when filled, else the dictionary."""
    value = getattr(obj, field, "")
    if current_lang() != "en":
        return value
    return getattr(obj, f"{field}_en", "") or t(value)


def setting(key: str, default: Any = None) -> Any:
    if current_lang() == "en":
        if key in _PAIRED_SETTINGS:
            return get_setting(_PAIRED_SETTINGS[key])
        if key in TRANSLATED_SETTINGS:
            return get_setting(f"{key}_en")
    return get_setting(key, default)


def num(value: Any) -> str:
    """Step numbers: Arabic-Indic digits on Arabic pages, Western digits on English ones."""
    text = str(value)
    if current_lang() == "en":
        return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return text.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


# ───────── availability ─────────

def english_live() -> bool:
    return bool(get_setting("english_enabled"))


def english_visible() -> bool:
    """Staff who are logged in can review the English site before it is switched on for everyone."""
    return english_live() or bool(current_user.is_authenticated)


def english_draft() -> bool:
    """An English page shown to staff only: never indexed, and labelled so nobody mistakes it for live."""
    return current_lang() == "en" and not english_live()


def snapshot_has_english(snapshot: Optional[list]) -> bool:
    return any((s.get("content") or {}).get("en") for s in (snapshot or []) if s.get("is_visible", True))


def page_has_english(slug: str) -> bool:
    cache = g.setdefault("_page_en", {})
    if slug not in cache:
        page = db.session.query(Page).filter_by(slug=slug).first()
        cache[slug] = bool(page is not None and snapshot_has_english(page.published_snapshot))
    return cache[slug]


def _has_english_articles() -> bool:
    if "_en_articles" not in g:
        g._en_articles = db.session.query(Article.id).filter(
            Article.lang == "en", Article.status == "published", Article.published_at <= utcnow()).first() is not None
    return g._en_articles


def _has_english_faq() -> bool:
    if "_en_faq" not in g:
        g._en_faq = db.session.query(FaqItem.id).filter(FaqItem.question_en != "").first() is not None
    return g._en_faq


def english_path(path: str) -> Optional[str]:
    """The English address of an Arabic path, or None when that page has no English version yet."""
    clean = path.split("#")[0].split("?")[0]
    if clean == "/":
        return "/en/" if page_has_english("home") else None
    parts = clean.strip("/").split("/")
    first = parts[0]
    if first in _ALWAYS_EN and len(parts) == 1:
        if first == "faq" and not _has_english_faq():
            return None
        return f"/en/{first}"
    if first in ("blog", "authors") or clean.startswith("/business/blog"):
        is_article = first == "blog" and len(parts) == 2  # its English address comes from its translation
        return f"/en{clean}" if _has_english_articles() and not is_article else None
    if len(parts) == 1 and "." not in first and page_has_english(first):
        return f"/en/{first}"
    return None


def lhref(href: Any) -> Any:
    """A link on the current page. In English, internal links go to the English page when there is one."""
    href = str(href or "")
    if current_lang() != "en" or not href.startswith("/") or href.startswith("//"):
        return href
    if href == "/en" or href.startswith("/en/"):
        return href
    target = english_path(href)
    if not target:
        return href
    suffix = re.search(r"[?#].*", href, re.S)  # keep ?utm_source=… and #section
    return target + (suffix.group() if suffix else "")


def lang_switch_url() -> Optional[str]:
    """Where the language button goes from this page; None hides it (no version in the other language)."""
    if not english_visible():
        return None
    if "lang_alt" in g:
        return g.lang_alt
    if current_lang() == "en":
        return plain_path()
    return english_path(request.path)


# ───────── filling English content from the catalog ─────────

def translate_text(text: str, table: dict[str, str]) -> Optional[str]:
    """English for one Arabic value (a single string, line-separated options, or a <p>-wrapped answer)."""
    if not AR_RE.search(text):
        return text
    if text in table:
        return table[text]
    wrapped = re.fullmatch(r"<p>(.*)</p>", text, re.S)
    if wrapped and wrapped.group(1) in table:
        return f"<p>{table[wrapped.group(1)]}</p>"
    if "\n" in text:
        lines = [translate_text(x, table) if x.strip() else x for x in text.split("\n")]
        return "\n".join(x for x in lines if x is not None) if None not in lines else None
    return None


def translate_tree(value: Any, table: dict[str, str], missing: set[str]) -> Any:
    """Copy a section's Arabic content, translating text and keeping icons, links and images as they are."""
    if isinstance(value, str):
        out = translate_text(value, table)
        if out is None:
            missing.add(value)
            return ""
        return out
    if isinstance(value, dict):
        return {k: translate_tree(v, table, missing) for k, v in value.items()}
    if isinstance(value, list):
        return [translate_tree(v, table, missing) for v in value]
    return value


def catalog() -> dict[str, str]:
    """Everything known: the built-in copy plus translations imported into the database."""
    extra = get_setting("translations_en")
    return {**UI, **CONTENT, **(extra if isinstance(extra, dict) else {})}
