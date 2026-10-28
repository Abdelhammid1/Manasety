"""Public-side data access. Every rule about what may appear publicly lives here:
consent before client names/logos, source + verification date before numbers,
feature status, FAQ visibility, scheduled publishing."""
from __future__ import annotations

import re
from typing import Any, Optional

from flask import g
from markupsafe import Markup, escape

from .extensions import db
from .models import (Article, CaseStudy, Client, DisplayFile, Fact, FaqItem, Feature, Page, utcnow)
from .security import add_revision, audit, clean_rich

# ───────── facts inside text ─────────
# [[fact:key]]               → the verified value, or nothing
# [[if:key]] … [[/if]]       → the whole segment only when the fact is publishable
_FACT_RE = re.compile(r"\[\[fact:([a-z0-9_\-]+)\]\]")
_IF_RE = re.compile(r"\[\[if:([a-z0-9_\-]+)\]\](.*?)\[\[/if\]\]", re.S)


def _facts() -> dict[str, Fact]:
    if "_facts" not in g:
        g._facts = {f.key: f for f in db.session.query(Fact).all()}
    return g._facts


def publishable_fact(key: str) -> Optional[Fact]:
    fact = _facts().get(key)
    return fact if fact and fact.is_publishable else None


def resolve_facts(text: str, html: bool = False) -> str:
    """Substitute verified facts. With html=True the fact value is escaped, because the
    surrounding rich text is marked safe and the value never went through the sanitiser."""
    if not text or "[[" not in text:
        return text or ""

    def value(key: str) -> str:
        fact = publishable_fact(key)
        if fact is None:
            return ""
        return str(escape(fact.value)) if html else fact.value

    text = _IF_RE.sub(lambda m: m.group(2) if publishable_fact(m.group(1)) else "", text)
    return _FACT_RE.sub(lambda m: value(m.group(1)), text)


def render_text(text: Any) -> Markup:
    """Plain-text field → escaped HTML with facts resolved and line breaks kept."""
    resolved = resolve_facts(str(text or ""))
    return Markup("<br>".join(str(escape(line)) for line in resolved.strip().split("\n")))


def render_rich(html: Any) -> Markup:
    """Rich field with facts resolved. Sanitised again *after* substitution: removing an
    [[if]] segment can splice fragments into new markup, so the save-time clean isn't enough."""
    return Markup(clean_rich(resolve_facts(str(html or ""), html=True)))


# ───────── page builder ─────────

def draft_snapshot(page: Page) -> list[dict]:
    return [s.to_snapshot() for s in sorted(page.sections, key=lambda s: s.position)]


def publish_page(page: Page, note: str = "نشر") -> None:
    before = page.published_snapshot
    page.published_snapshot = draft_snapshot(page)
    page.published_seo = dict(page.seo or {})
    page.published_at = utcnow()
    page.scheduled_snapshot = None
    page.scheduled_at = None
    add_revision("page", page.id, {"sections": page.published_snapshot, "seo": page.seo}, note=note)
    audit("publish", "page", page.id, before=before, after=page.published_snapshot, summary=f"نشر صفحة {page.slug}")


def schedule_page(page: Page, when) -> None:
    # Sections and SEO are frozen together so later draft edits can't leak into the scheduled release.
    page.scheduled_snapshot = {"sections": draft_snapshot(page), "seo": dict(page.seo or {})}
    page.scheduled_at = when
    audit("schedule", "page", page.id, after={"at": when}, summary=f"جدولة نشر {page.slug}")


def apply_scheduled() -> int:
    """Publish anything whose time has come. Called lazily on public requests and by `flask publish-scheduled`."""
    now = utcnow()
    count = 0
    for page in db.session.query(Page).filter(Page.scheduled_at.isnot(None), Page.scheduled_at <= now).all():
        snap = page.scheduled_snapshot or {}
        page.published_snapshot = snap.get("sections", [])
        page.published_seo = dict(snap.get("seo") or {})
        page.published_at = now
        add_revision("page", page.id, {"sections": page.published_snapshot, "seo": page.published_seo}, note="نشر مجدول")
        page.scheduled_snapshot = None
        page.scheduled_at = None
        count += 1
    for art in db.session.query(Article).filter(Article.status == "scheduled", Article.published_at <= now).all():
        art.status = "published"
        count += 1
    if count:
        db.session.commit()
    return count


def visible_sections(snapshot: Optional[list]) -> list[dict]:
    return [s for s in (snapshot or []) if s.get("is_visible")]


def section_content(section: dict, lang: str) -> dict:
    content = section.get("content") or {}
    return content.get(lang) or ({} if lang != "ar" else {})


# ───────── library data ─────────

def public_features(module: str) -> list[Feature]:
    return (db.session.query(Feature)
            .filter(Feature.module == module, Feature.status != "hidden")
            .order_by(Feature.position, Feature.id).all())


def public_clients() -> list[Client]:
    """Consent is enforced in SQL *and* by the model property (defence in depth)."""
    rows = (db.session.query(Client)
            .filter(Client.is_visible.is_(True), Client.consent.is_(True),
                    Client.consent_date.isnot(None), Client.consent_proof_id.isnot(None))
            .order_by(Client.position, Client.id).all())
    return [c for c in rows if c.is_publishable]


def public_case_studies() -> list[CaseStudy]:
    return (db.session.query(CaseStudy).filter(CaseStudy.is_visible.is_(True))
            .order_by(CaseStudy.position, CaseStudy.id).all())


def public_faq(home_only: bool = False, category: str = "", article_id: Optional[int] = None) -> list[FaqItem]:
    q = db.session.query(FaqItem).filter(FaqItem.is_visible.is_(True))
    if home_only:
        q = q.filter(FaqItem.show_on_home.is_(True))
    if category:
        q = q.filter(FaqItem.category == category)
    items = q.order_by(FaqItem.position, FaqItem.id).all()
    if article_id is not None:
        items = [i for i in items if article_id in (i.article_ids or [])]
    return [i for i in items if not i.validation_errors()]


def public_files(placement: str) -> list[DisplayFile]:
    rows = (db.session.query(DisplayFile).filter(DisplayFile.is_visible.is_(True))
            .order_by(DisplayFile.position, DisplayFile.id).all())
    return [f for f in rows if placement in (f.placements or [])]


def live_articles(lang: str = "ar", limit: Optional[int] = None, category_id: Optional[int] = None,
                  audience: Optional[str] = None) -> list[Article]:
    q = (db.session.query(Article)
         .filter(Article.lang == lang, Article.status == "published", Article.published_at <= utcnow()))
    if category_id:
        q = q.filter(Article.category_id == category_id)
    if audience in ("schools", "business"):
        q = q.filter(Article.audience.in_([audience, "both"]))
    q = q.order_by(Article.published_at.desc())
    if limit:
        q = q.limit(limit)
    return q.all()


def related_articles(article: Article, count: int = 3) -> list[Article]:
    if article.related_mode == "manual" and article.related_ids:
        rows = db.session.query(Article).filter(Article.id.in_(article.related_ids)).all()
        by_id = {a.id: a for a in rows if a.is_live}
        return [by_id[i] for i in article.related_ids if i in by_id][:count]
    aud = article.audience if article.audience in ("schools", "business") else None
    pool = [a for a in live_articles(article.lang, category_id=article.category_id, audience=aud) if a.id != article.id]
    if len(pool) < count:
        pool += [a for a in live_articles(article.lang, audience=aud) if a.id != article.id and a not in pool]
    return pool[:count]
