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
from .services.seo import jsonld
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
    return f"https://wa.me/{number}?text={quote(get_setting('whatsapp_prefill') or '')}"


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
    wanted = lines(slugs)
    if wanted:
        rows = db.session.query(Article).filter(Article.lang == lang, Article.slug.in_(wanted)).all()
        by_slug = {a.slug: a for a in rows if a.is_live}
        return [by_slug[s] for s in wanted if s in by_slug][:count]
    return live_articles(lang, limit=count)


def verified_facts(keys: Any) -> list[Fact]:
    return [f for f in (publishable_fact(k) for k in lines(keys)) if f]


def media_list(limit: int = 300) -> list[Media]:
    return db.session.query(Media).order_by(Media.id.desc()).limit(limit).all()


def register_template_utils(app: Flask) -> None:
    app.jinja_env.filters.update(rt=render_text, rich=render_rich, ar_date=ar_date, lines=lines)
    app.jinja_env.globals.update(
        icon=icon, icon_sprite=icon_sprite, media_obj=media_obj, setting=get_setting, jsonld=jsonld,
        whatsapp_url=whatsapp_url, integrations_for=integrations_for, needs_consent_banner=needs_consent_banner,
        fact=fact_value, files_for=public_files, features_for=public_features, clients=public_clients,
        case_studies=public_case_studies, ring_position=ring_position, featured_articles=featured_articles,
        verified_facts=verified_facts, media_list=media_list, site_url=lambda: current_app.config["SITE_URL"],
    )
