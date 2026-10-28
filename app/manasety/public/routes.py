"""Public site: landing page, blog, legal pages, files, lead intake, sitemap/robots/RSS."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Optional

from flask import (Blueprint, Response, abort, current_app, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from markupsafe import Markup

from ..config import LEGACY_DIRS, LEGACY_FILES
from ..extensions import csrf, db, limiter
from ..models import Article, Author, Category, DisplayFile, LegalPage, Page, SideCard, Tag, utcnow
from ..publishing import (live_articles, public_faq, related_articles, section_content, visible_sections)
from ..services import seo
from ..services.leads import build_lead, forward_lead
from ..settings_store import all_settings, get_setting

bp = Blueprint("public", __name__)


def _english_enabled() -> bool:
    return bool(get_setting("english_enabled"))


def _render_page(page: Page, snapshot: Optional[list], lang: str, preview: bool = False, path: str = "") -> str:
    if snapshot is None:
        abort(404)
    s = all_settings()
    site = current_app.config["SITE_URL"]
    page_seo = ((page.seo if preview else page.published_seo) or {}).get(lang, {})
    sections = [{**sec, "c": section_content(sec, lang)} for sec in visible_sections(snapshot)]
    hero = next((x["c"] for x in sections if x["block_type"] == "hero"), {})
    schema = [seo.organization_schema(s, site), seo.website_schema(s, site),
              seo.software_schema(site, page_seo.get("software_name") or "منصتي-سكول (Manasety School)",
                                  page_seo.get("description") or hero.get("subtitle", ""))]
    faq_items = []
    faq_section = next((x for x in sections if x["block_type"] == "faq"), None)
    if faq_section:
        faq_items = public_faq(home_only=True, category=faq_section["c"].get("category", ""))
        fs = seo.faq_schema([(f.question_en if lang == "en" and f.question_en else f.question,
                              f.answer_html_en if lang == "en" and f.answer_html_en else f.answer_html)
                             for f in faq_items])
        if fs:
            schema.append(fs)
    return render_template(
        "public/home.html", page=page, sections=sections, lang=lang, page_seo=page_seo, schema=schema,
        faq_items=faq_items, preview=preview,
        canonical=site + (path or ("/en/" if lang == "en" else "/")),
        hreflang=_english_enabled() and not path,
    )


@bp.route("/")
def home():
    page = db.session.query(Page).filter_by(slug="home").first_or_404()
    return _render_page(page, page.published_snapshot, "ar")


@bp.route("/en/")
def home_en():
    if not _english_enabled():
        abort(404)
    page = db.session.query(Page).filter_by(slug="home").first_or_404()
    return _render_page(page, page.published_snapshot, "en")


@bp.route("/business")
def business():
    page = db.session.query(Page).filter_by(slug="business").first_or_404()
    return _render_page(page, page.published_snapshot, "ar", path="/business")


@bp.route("/preview/<token>")
def preview(token: str):
    """Shareable draft preview (noindex). The token rotates from the dashboard."""
    page = db.session.query(Page).filter_by(preview_token=token).first_or_404()
    from ..publishing import draft_snapshot
    lang = request.args.get("lang", "ar")
    html = _render_page(page, draft_snapshot(page), "en" if lang == "en" else "ar", preview=True)
    resp = Response(html)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


# ───────── leads ─────────

@bp.route("/api/leads", methods=["POST"])
@csrf.exempt  # anonymous, state-free form: an expired token must never drop a lead
@limiter.limit("5 per minute; 30 per hour")
def submit_lead():
    wants_json = request.accept_mimetypes.best == "application/json" or request.is_json
    payload = request.get_json(silent=True) if request.is_json else None
    if request.is_json and not isinstance(payload, dict):
        return jsonify(ok=False, errors=["طلب غير صالح."]), 400
    form = {k: v for k, v in payload.items() if isinstance(v, str)} if payload is not None else request.form
    if (form.get("website") or "").strip():  # honeypot: bots fill every field
        return (jsonify(ok=True), 200) if wants_json else redirect(url_for("public.thank_you"))
    lead, errors = build_lead(form, form.get("form") or "demo")
    if errors or lead is None:
        if wants_json:
            return jsonify(ok=False, errors=errors), 400
        return Response("<br>".join(errors), 400)
    db.session.add(lead)
    db.session.commit()
    forward_lead(lead.id)
    if wants_json:
        return jsonify(ok=True, id=lead.id)
    return redirect(url_for("public.thank_you"))


@bp.route("/thank-you.html")
@bp.route("/thank-you")
def thank_you():
    return render_template("public/thank_you.html", lang="ar")


# ───────── legal pages (same URLs that were filed with PayTabs) ─────────

@bp.route("/<any(privacy, terms, refund):slug>.html")
def legal(slug: str):
    page = db.session.query(LegalPage).filter_by(slug=slug).first_or_404()
    return render_template("legal/page.html", page=page)


# ───────── FAQ & files pages ─────────

@bp.route("/faq")
def faq_page():
    from ..models import FAQ_CATEGORIES
    items = [f for f in public_faq() if f.show_on_faq_page]
    schema = seo.faq_schema([(f.question, f.answer_html) for f in items])
    return render_template("public/faq.html", items=items, categories=FAQ_CATEGORIES, lang="ar",
                           schema=[schema] if schema else [], canonical=current_app.config["SITE_URL"] + "/faq")


@bp.route("/files")
def files_page():
    from ..publishing import public_files
    return render_template("public/files.html", files=public_files("page"), lang="ar",
                           canonical=current_app.config["SITE_URL"] + "/files")


# ───────── blog ─────────

def _blog_prefix(lang: str) -> str:
    return "/en/blog" if lang == "en" else "/blog"


def _blog_index(lang: str, category: Optional[Category] = None, tag: Optional[Tag] = None, audience: str = "schools"):
    articles = live_articles(lang, category_id=category.id if category else None, audience=audience)
    if tag:
        articles = [a for a in articles if tag in a.tags]
    page_no = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = 12
    total_pages = max((len(articles) + per_page - 1) // per_page, 1)
    if page_no > total_pages:
        abort(404)
    site = current_app.config["SITE_URL"]
    path = request.path
    crumbs = [("الرئيسية", site + "/"), ("المقالات", site + _blog_prefix(lang))]
    if category:
        crumbs.append((category.name, site + path))
    if tag:
        crumbs.append((tag.name, site + path))
    return render_template(
        "public/blog_index.html", articles=articles[(page_no - 1) * per_page: page_no * per_page],
        categories=db.session.query(Category).order_by(Category.name).all(), category=category, tag=tag,
        page_no=page_no, total_pages=total_pages, lang=lang, blog_audience=audience,
        canonical=site + path + (f"?page={page_no}" if page_no > 1 else ""),
        schema=[seo.breadcrumb_schema(crumbs)], crumbs=crumbs,
    )


@bp.route("/blog")
def blog():
    return _blog_index("ar")


@bp.route("/en/blog")
def blog_en():
    if not _english_enabled():
        abort(404)
    return _blog_index("en")


@bp.route("/blog/category/<slug>")
def blog_category(slug: str):
    cat = db.session.query(Category).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", category=cat)


@bp.route("/blog/tag/<slug>")
def blog_tag(slug: str):
    tag = db.session.query(Tag).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", tag=tag)


@bp.route("/business/blog")
def blog_biz():
    return _blog_index("ar", audience="business")


@bp.route("/business/blog/category/<slug>")
def blog_biz_category(slug: str):
    cat = db.session.query(Category).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", category=cat, audience="business")


@bp.route("/business/blog/tag/<slug>")
def blog_biz_tag(slug: str):
    tag = db.session.query(Tag).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", tag=tag, audience="business")


def _side_cards(art: Article) -> list:
    aud = "business" if art.audience == "business" else "schools"
    return (db.session.query(SideCard).filter(SideCard.is_active.is_(True), SideCard.audience.in_([aud, "both"]))
            .order_by(SideCard.position, SideCard.id).all())


def _article_view(lang: str, slug: str, preview_article: Optional[Article] = None):
    art = preview_article or db.session.query(Article).filter_by(lang=lang, slug=slug).first()
    if art is None or (preview_article is None and not art.is_live):
        abort(404)
    site = current_app.config["SITE_URL"]
    body, toc = seo.add_heading_ids(art.content_html)
    cover = art.cover
    og = art.og_image or cover
    faq_pairs = [(x.get("q", ""), x.get("a", "")) for x in (art.faq or []) if x.get("q") and x.get("a")]
    faq_pairs += [(f.question, f.answer_html) for f in public_faq(article_id=art.id)]
    biz = art.audience == "business"
    home_path, blog_path = ("/business", "/business/blog") if biz else ("/", _blog_prefix(lang))
    crumbs = [("الرئيسية", site + home_path), ("المقالات", site + blog_path)]
    if art.category:
        crumbs.append((art.category.name, f"{site}{blog_path}/category/{art.category.slug}"))
    crumbs.append((art.title, site + art.path))
    schema: list[Any] = [seo.article_schema(art, site, (site + og.url) if og else ""), seo.breadcrumb_schema(crumbs)]
    fs = seo.faq_schema(faq_pairs)
    if fs:
        schema.append(fs)
    translation = None
    if art.translation_of_id:
        translation = art.translation_of
    else:
        translation = db.session.query(Article).filter_by(translation_of_id=art.id).first()
    if translation is not None and not translation.is_live:
        translation = None
    return render_template(
        "public/article.html", article=art, body=Markup(body), toc=toc if seo.word_count(body) > 900 else [],
        related=related_articles(art), faq_pairs=faq_pairs, lang=lang, schema=schema, crumbs=crumbs,
        canonical=art.canonical_url or site + art.path, og_image=(site + og.url) if og else "",
        noindex=art.noindex or preview_article is not None, translation=translation, side_cards=_side_cards(art),
    )


@bp.route("/blog/<slug>")
def article(slug: str):
    return _article_view("ar", slug)


@bp.route("/en/blog/<slug>")
def article_en(slug: str):
    if not _english_enabled():
        abort(404)
    return _article_view("en", slug)


@bp.route("/authors/<slug>")
def author(slug: str):
    person = db.session.query(Author).filter_by(slug=slug).first_or_404()
    site = current_app.config["SITE_URL"]
    articles = [a for a in live_articles("ar") if a.author_id == person.id]
    schema = [{"@context": "https://schema.org", **seo.person_schema(person, site)}]
    return render_template("public/author.html", author=person, articles=articles, lang="ar", schema=schema,
                           canonical=f"{site}/authors/{slug}")


@bp.route("/blog/feed.xml")
def rss():
    site = current_app.config["SITE_URL"]
    items = live_articles("ar", limit=30)
    xml = render_template("public/rss.xml", items=items, site=site,
                          now=format_datetime(datetime.now(timezone.utc)), fmt=lambda d: format_datetime(d) if d else "")
    return Response(xml, mimetype="application/rss+xml")


# ───────── sitemap / robots ─────────

@bp.route("/sitemap.xml")
def sitemap():
    site = current_app.config["SITE_URL"]
    home = db.session.query(Page).filter_by(slug="home").first()
    urls = [{"loc": site + "/", "lastmod": home.published_at if home else None}]
    biz = db.session.query(Page).filter_by(slug="business").first()
    if biz is not None and biz.published_snapshot is not None:
        urls.append({"loc": site + "/business", "lastmod": biz.published_at})
    if _english_enabled():
        urls.append({"loc": site + "/en/", "lastmod": home.published_at if home else None})
    arts = live_articles("ar") + (live_articles("en") if _english_enabled() else [])
    if arts:
        dates = [d for d in (a.content_updated_at or a.published_at for a in arts) if d is not None]
        urls.append({"loc": site + "/blog", "lastmod": max(dates) if dates else None})
        if any(a.audience in ("business", "both") for a in arts):
            urls.append({"loc": site + "/business/blog", "lastmod": max(dates) if dates else None})
    for a in arts:
        if a.noindex or (a.canonical_url and a.canonical_url != site + a.path):
            continue
        urls.append({"loc": site + a.path, "lastmod": a.content_updated_at or a.published_at})
    used_cats = {a.category_id for a in arts if a.category_id}
    for c in db.session.query(Category).filter(Category.id.in_(used_cats)).all() if used_cats else []:
        urls.append({"loc": f"{site}/blog/category/{c.slug}", "lastmod": None})
    for au in db.session.query(Author).all():
        if any(a.author_id == au.id for a in arts):
            urls.append({"loc": f"{site}/authors/{au.slug}", "lastmod": None})
    urls.append({"loc": site + "/faq", "lastmod": None})
    for slug in ("privacy", "terms", "refund"):
        lp = db.session.query(LegalPage).filter_by(slug=slug).first()
        if lp:
            urls.append({"loc": f"{site}/{slug}.html", "lastmod": lp.updated_at})
    xml = render_template("public/sitemap.xml", urls=urls)
    return Response(xml, mimetype="application/xml")


@bp.route("/robots.txt")
def robots():
    site = current_app.config["SITE_URL"]
    if current_app.config.get("STAGING"):
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = (f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /preview/\nDisallow: /api/\n"
                f"{get_setting('robots_extra') or ''}\nSitemap: {site}/sitemap.xml\n")
    return Response(body, mimetype="text/plain")


# ───────── display files & legacy static files (catch-all, keep last) ─────────

@bp.route("/sara")
def sara_root():
    return redirect("/sara/", code=301)


@bp.route("/<path:filename>")
def root_file(filename: str):
    df = db.session.query(DisplayFile).filter_by(public_path=filename).first()
    if df is not None:
        # Hiding a file removes it from pages only; the direct link keeps working
        # (Sector Bot sends it) unless the direct link is switched off explicitly.
        if not df.direct_link_enabled or df.external_url or not df.stored_filename:
            abort(404)
        df.download_count += 1
        db.session.commit()
        return send_from_directory(current_app.config["MEDIA_DIR"], df.stored_filename, mimetype=df.mime,
                                   max_age=300, download_name=Path(df.public_path).name)
    if filename in LEGACY_FILES:
        return send_from_directory(current_app.config["LEGACY_DIR"], filename, max_age=3600)
    top, _, rest = filename.partition("/")
    if top in LEGACY_DIRS:
        folder = Path(current_app.config["LEGACY_DIR"]) / top
        if rest and ".." not in rest.split("/") and (folder / rest).is_file():
            return send_from_directory(folder, rest, max_age=3600)  # safe_join inside
        return send_from_directory(folder, "index.html", max_age=300)
    abort(404)


@bp.app_errorhandler(404)
def not_found(_e):
    return render_template("public/404.html", lang="ar"), 404


@bp.app_template_global()
def now_year() -> int:
    return utcnow().year
