"""Per-page layout: top nav, footer and WhatsApp for each page, in one place.

Stored in the settings key "page_layout" as {slug: {...}}. A missing/empty field falls back to the
global settings for that kind of page, so pages without an entry look exactly as before."""
from __future__ import annotations

import copy
from typing import Any

from .extensions import db
from .security import clean_text
from .settings_store import get_setting, set_setting

_OK_HREF = ("/", "#", "https://", "http://")


def text_to_links(text: str) -> tuple:
    items, skipped = [], 0
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        label, sep, href = line.partition("|")
        label, href = clean_text(label.strip())[:60], href.strip()[:300]
        if sep and label and href.startswith(_OK_HREF):
            items.append({"label": label, "href": href})
        else:
            skipped += 1
    return items, skipped


def links_to_text(items: Any) -> str:
    return "\n".join(f"{i.get('label', '')} | {i.get('href', '')}" for i in (items or []) if isinstance(i, dict))


def _all() -> dict:
    data = get_setting("page_layout") or {}
    return data if isinstance(data, dict) else {}


def saved_layout(slug: str) -> dict:
    return dict(_all().get(slug) or {})


def save_layout(slug: str, layout: dict) -> None:
    data = copy.deepcopy(_all())
    if layout:
        data[slug] = layout
    else:
        data.pop(slug, None)
    set_setting("page_layout", data)


def reset_layout(slug: str) -> None:
    save_layout(slug, {})


def legacy_layout(slug: str) -> dict:
    """What the page uses today from the global settings (mirrors base.html's old fallbacks)."""
    g = get_setting
    biz_pages = [x.strip() for x in str(g("business_pages") or "").split("\n") if x.strip()]
    is_biz = slug == "business" or slug in biz_pages
    is_inst = slug == "training-institutes"
    if slug in biz_pages and g("nav_biz_pages"):
        nav = g("nav_biz_pages")
    elif is_biz and g("nav_biz"):
        nav = g("nav_biz")
    elif is_inst and g("nav_institutes"):
        nav = g("nav_institutes")
    else:
        nav = g("nav")
    if is_biz and g("nav_cta_label_biz"):
        cta_label, cta_href = g("nav_cta_label_biz"), g("nav_cta_href_biz")
    elif is_inst and g("nav_cta_label_institutes"):
        cta_label, cta_href = g("nav_cta_label_institutes"), g("nav_cta_href_institutes")
    else:
        cta_label, cta_href = g("nav_cta_label"), g("nav_cta_href")
    if is_biz and g("whatsapp_prefill_biz"):
        wa = g("whatsapp_prefill_biz")
    elif is_inst and g("whatsapp_prefill_institutes"):
        wa = g("whatsapp_prefill_institutes")
    else:
        wa = g("whatsapp_prefill")
    return {
        "style": "business" if is_biz else "schools",
        "nav": nav or [], "cta_label": cta_label or "", "cta_href": cta_href or "",
        "footer_about": (g("footer_about_biz") if is_biz and g("footer_about_biz") else g("footer_about")) or "",
        "footer_tagline": (g("footer_tagline_biz") if is_biz and g("footer_tagline_biz") else g("footer_tagline")) or "",
        "footer_pages": g("extra_pages") or [], "footer_pages_hide": False,
        "whatsapp": wa or "", "whatsapp_bubble": g("whatsapp_bubble") or "",
    }


def effective_layout(slug: str) -> dict:
    eff = legacy_layout(slug)
    for k, v in saved_layout(slug).items():
        if v not in ("", None, []):
            eff[k] = v
    return eff


def form_from_layout(eff: dict) -> dict:
    return {
        "style": eff.get("style") or "schools",
        "nav": links_to_text(eff.get("nav")),
        "cta_label": eff.get("cta_label") or "", "cta_href": eff.get("cta_href") or "",
        "footer_about": eff.get("footer_about") or "", "footer_tagline": eff.get("footer_tagline") or "",
        "footer_pages": links_to_text(eff.get("footer_pages")),
        "footer_pages_hide": bool(eff.get("footer_pages_hide")),
        "whatsapp": eff.get("whatsapp") or "", "whatsapp_bubble": eff.get("whatsapp_bubble") or "",
    }


def layout_from_form(f: Any) -> tuple:
    out, skipped = {}, 0
    if (f.get("style") or "") in ("schools", "business"):
        out["style"] = f.get("style")
    nav, s1 = text_to_links(f.get("nav", ""))
    fp, s2 = text_to_links(f.get("footer_pages", ""))
    skipped = s1 + s2
    if nav:
        out["nav"] = nav
    if fp:
        out["footer_pages"] = fp
    for k, n in (("cta_label", 60), ("footer_tagline", 200), ("whatsapp_bubble", 200), ("footer_about", 600), ("whatsapp", 300)):
        v = clean_text(f.get(k, "") or "")[:n]
        if v:
            out[k] = v
    href = (f.get("cta_href", "") or "").strip()[:300]
    if href.startswith(_OK_HREF):
        out["cta_href"] = href
    if (f.get("footer_pages_hide") or "") in ("on", "1", "true", "y"):
        out["footer_pages_hide"] = True
    return out, skipped


def overview_rows() -> list:
    from .models import Page
    rows = []
    for p in db.session.query(Page).order_by(Page.id).all():
        eff = effective_layout(p.slug)
        rows.append({"page": p, "eff": eff, "custom": bool(saved_layout(p.slug)),
                     "nav_text": " · ".join(i.get("label", "") for i in (eff.get("nav") or []) if isinstance(i, dict)),
                     "live": p.published_snapshot is not None})
    return rows
