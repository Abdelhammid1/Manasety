"""Jinja globals & filters shared by public pages and the dashboard."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import quote

from flask import Flask, current_app, request
from markupsafe import Markup, escape

from .extensions import db
from .icons import ICONS
from .models import Article, Fact, Integration, Media
from .publishing import (live_articles, public_case_studies, public_clients, public_features, public_files,
                         publishable_fact, render_rich, render_text)
from .services.seo import jsonld, wrap_tables
from .settings_store import get_setting


def icon_sprite() -> Markup:
    symbols = "".join(
        f'<symbol id="i-{k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{v}</symbol>' for k, v in ICONS.items())
    return Markup(f'<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">{symbols}</svg>')


def icon(name: str, cls: str = "ic") -> Markup:
    name = name if name in ICONS else "check"
    return Markup(f'<svg class="{escape(cls)}" aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>')


def media_obj(media_id: Any) -> Optional[Media]:
    if not media_id:
        return None
    try:
        return db.session.get(Media, int(media_id))
    except (TypeError, ValueError):
        return None


_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def ar_date(value: Any) -> str:
    if not isinstance(value, (date, datetime)):
        return ""
    return f"{value.day} {_AR_MONTHS[value.month - 1]} {value.year}"


def whatsapp_url(country: str = "eg") -> str:
    number = get_setting(f"whatsapp_{country}")
    from flask import g, request
    text = get_setting('whatsapp_prefill') or ''
    try:
        if (request.path.startswith('/business') or getattr(g, 'page_slug', '') in lines(get_setting('business_pages'))) and get_setting('whatsapp_prefill_biz'):
            text = get_setting('whatsapp_prefill_biz')
        elif (getattr(g, 'page_slug', '') == 'training-institutes' or request.path.startswith('/training-institutes')) \
                and get_setting('whatsapp_prefill_institutes'):
            text = get_setting('whatsapp_prefill_institutes')
    except RuntimeError:
        pass
    try:
        _ov = (page_layout() or {}).get("whatsapp")
        if _ov:
            text = _ov
    except RuntimeError:
        pass
    return f"https://wa.me/{number}?text={quote(text)}"


def integrations_for(placement: str) -> list[Integration]:
    rows = (db.session.query(Integration)
            .filter(Integration.is_active.is_(True), Integration.placement == placement)
            .order_by(Integration.position, Integration.id).all())
    return [i for i in rows if i.code and i.applies_to(request.path)]


def needs_consent_banner() -> bool:
    return (db.session.query(Integration)
            .filter(Integration.is_active.is_(True), Integration.requires_consent.is_(True)).count() > 0)


def fact_value(key: str) -> str:
    fact = publishable_fact(key)
    return fact.value if fact else ""


def lines(value: Any) -> list[str]:
    return [x.strip() for x in str(value or "").split("\n") if x.strip()]


def ring_position(index: int, total: int, radius: float = 42.0) -> tuple[float, float]:
    """Percent coordinates of a node around the 'core platform' circle (starts at 12 o'clock)."""
    angle = (index / max(total, 1)) * 2 * math.pi - math.pi / 2
    return round(50 + radius * math.cos(angle), 2), round(50 + radius * math.sin(angle), 2)


def featured_articles(slugs: Any, count: int, lang: str = "ar") -> list[Article]:
    from flask import request
    wanted = lines(slugs)
    if wanted:
        rows = db.session.query(Article).filter(Article.lang == lang, Article.slug.in_(wanted)).all()
        by_slug = {a.slug: a for a in rows if a.is_live}
        return [by_slug[s] for s in wanted if s in by_slug][:count]
    aud = "business" if request.path.startswith("/business") else "schools"
    return live_articles(lang, limit=count, audience=aud)


def verified_facts(keys: Any) -> list[Fact]:
    return [f for f in (publishable_fact(k) for k in lines(keys)) if f]


def media_list(limit: int = 300) -> list[Media]:
    return db.session.query(Media).order_by(Media.id.desc()).limit(limit).all()


def page_is_live(href: str) -> bool:
    """False for links to dashboard pages that exist but are not published yet (avoids 404 links)."""
    from .models import Page
    h = (href or "").split("#")[0].split("?")[0].strip("/")
    if not h or "/" in h or "." in h:
        return True
    page = db.session.query(Page).filter_by(slug=h).first()
    return True if page is None else page.published_snapshot is not None


def page_layout() -> dict:
    """Per-page overrides (top nav, footer, WhatsApp) saved from the dashboard; {} = use the global settings."""
    from flask import g
    slug = getattr(g, "page_slug", "") or ""
    if not slug:
        return {}
    data = get_setting("page_layout") or {}
    return dict(data.get(slug) or {}) if isinstance(data, dict) else {}


def side_cards_for(slug: str) -> list:
    from .models import SideCard
    if not slug:
        return []
    return (db.session.query(SideCard).filter(SideCard.is_active.is_(True), SideCard.page_slug == slug)
            .order_by(SideCard.position, SideCard.id).all())


def register_template_utils(app: Flask) -> None:
    app.jinja_env.filters.update(rt=render_text, rich=render_rich, tables=wrap_tables, ar_date=ar_date, lines=lines)
    app.jinja_env.globals.update(
        icon=icon, icon_sprite=icon_sprite, media_obj=media_obj, setting=get_setting, jsonld=jsonld,
        whatsapp_url=whatsapp_url, integrations_for=integrations_for, needs_consent_banner=needs_consent_banner,
        fact=fact_value, files_for=public_files, features_for=public_features, clients=public_clients,
        case_studies=public_case_studies, page_is_live=page_is_live, side_cards_for=side_cards_for, page_layout=page_layout, ring_position=ring_position, featured_articles=featured_articles,
        verified_facts=verified_facts, media_list=media_list, site_url=lambda: current_app.config["SITE_URL"],
    )
