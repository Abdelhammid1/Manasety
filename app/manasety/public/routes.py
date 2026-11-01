"""Public site: landing page, blog, legal pages, files, lead intake, sitemap/robots/RSS."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Optional

from flask import (Blueprint, Response, abort, current_app, g, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from markupsafe import Markup

from ..config import LEGACY_DIRS, LEGACY_FILES
from ..extensions import csrf, db, limiter
from ..i18n import current_lang, english_live, english_path, english_visible, snapshot_has_english, t
from ..models import Article, Author, Category, DisplayFile, LegalPage, Page, SideCard, Tag, utcnow
from ..publishing import (live_articles, public_faq, related_articles, section_content, visible_sections)
from ..services import seo
from ..services.leads import build_lead, forward_lead
from ..settings_store import all_settings, get_setting

bp = Blueprint("public", __name__)


def _english_gate() -> None:
    """English pages are public once switched on; until then only logged-in staff can review them."""
    if not english_visible():
        abort(404)


def _render_page(page: Page, snapshot: Optional[list], lang: str, preview: bool = False, path: str = "") -> str:
    if snapshot is None:
        abort(404)
    from flask import g as _g
    _g.page_slug = page.slug
    _g.lang = lang  # previews pass ?lang=en on a path without the /en prefix
    if preview:
        _g.lang_alt = None
    s = all_settings()
    site = current_app.config["SITE_URL"]
    page_seo = ((page.seo if preview else page.published_seo) or {}).get(lang, {})
    sections = [{**sec, "c": section_content(sec, lang)} for sec in visible_sections(snapshot)]
    if lang == "en":  # a section with no English yet stays hidden rather than rendering empty
        sections = [sec for sec in sections if sec["c"]]
    hero = next((x["c"] for x in sections if x["block_type"] == "hero"), {})
    schema = [seo.organization_schema(s, site), seo.website_schema(s, site),
              seo.software_schema(site, page_seo.get("software_name") or t("منصتي-سكول (Manasety School)"),
                                  page_seo.get("description") or hero.get("subtitle", ""), lang)]
    faq_items = []
    faq_section = next((x for x in sections if x["block_type"] == "faq"), None)
    if faq_section:
        faq_items = public_faq(home_only=(page.slug in ("home", "business")), category=faq_section["c"].get("category", ""))
        if lang == "en":
            faq_items = [f for f in faq_items if f.question_en and f.answer_html_en]
        fs = seo.faq_schema([(f.question_en if lang == "en" and f.question_en else f.question,
                              f.answer_html_en if lang == "en" and f.answer_html_en else f.answer_html)
                             for f in faq_items])
        if fs:
            schema.append(fs)
    return render_template(
        "public/home.html", page=page, sections=sections, lang=lang, page_seo=page_seo, schema=schema,
        faq_items=faq_items, preview=preview,
        canonical=site + ("/en" if lang == "en" and path else "") + (path or ("/en/" if lang == "en" else "/")),
        hreflang=english_live() and not preview and snapshot_has_english(snapshot),
        path_ar=path or "/", path_en=f"/en{path}" if path else "/en/",
    )


@bp.route("/")
def home():
    page = db.session.query(Page).filter_by(slug="home").first_or_404()
    return _render_page(page, page.published_snapshot, "ar")


@bp.route("/en")
def home_en_redirect():
    return redirect("/en/", code=301)


@bp.route("/en/")
def home_en():
    _english_gate()
    page = db.session.query(Page).filter_by(slug="home").first_or_404()
    if not snapshot_has_english(page.published_snapshot):
        abort(404)
    return _render_page(page, page.published_snapshot, "en")


@bp.route("/en/<slug>")
def dynamic_page_en(slug):
    """The English version of /business, /training-institutes and any page from the dashboard."""
    _english_gate()
    if slug == "home" or not _DYN_SLUG.match(slug):
        abort(404)
    page = db.session.query(Page).filter_by(slug=slug).first_or_404()
    if not snapshot_has_english(page.published_snapshot):
        abort(404)
    return _render_page(page, page.published_snapshot, "en", path="/" + slug)


@bp.route("/business")
def business():
    page = db.session.query(Page).filter_by(slug="business").first_or_404()
    return _render_page(page, page.published_snapshot, "ar", path="/business")


@bp.route("/training-institutes")
def training_institutes():
    page = db.session.query(Page).filter_by(slug="training-institutes").first_or_404()
    return _render_page(page, page.published_snapshot, "ar", path="/training-institutes")


import re as _re
_DYN_SLUG = _re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@bp.route("/<slug>")
def dynamic_page(slug):
    """Any page created from the dashboard (admin/pages/new) is served at /<slug>."""
    if slug in ("home", "business"):
        abort(404)
    page = db.session.query(Page).filter_by(slug=slug).first() if _DYN_SLUG.match(slug) else None
    if page is None:  # /manasety-profile.pdf, /indexold….html and other root files must keep working
        return root_file(slug)
    return _render_page(page, page.published_snapshot, "ar", path="/" + slug)


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
    g.lang = "en" if form.get("lang") == "en" else "ar"  # the form's language: same address for both
    thanks = "public.thank_you_en" if g.lang == "en" else "public.thank_you"
    if (form.get("website") or "").strip():  # honeypot: bots fill every field
        return (jsonify(ok=True), 200) if wants_json else redirect(url_for(thanks))
    lead, errors = build_lead(form, form.get("form") or "demo")
    if errors or lead is None:
        errors = [t(e) for e in errors]
        if wants_json:
            return jsonify(ok=False, errors=errors), 400
        return Response("<br>".join(errors), 400)
    db.session.add(lead)
    db.session.commit()
    forward_lead(lead.id)
    if wants_json:
        return jsonify(ok=True, id=lead.id)
    return redirect(url_for(thanks))


@bp.route("/thank-you.html")
@bp.route("/thank-you")
def thank_you():
    return render_template("public/thank_you.html", lang="ar")


@bp.route("/en/thank-you")
def thank_you_en():
    _english_gate()
    return render_template("public/thank_you.html", lang="en")


# ───────── legal pages (same URLs that were filed with PayTabs) ─────────

@bp.route("/<any(privacy, terms, refund):slug>.html")
def legal(slug: str):
    page = db.session.query(LegalPage).filter_by(slug=slug).first_or_404()
    return render_template("legal/page.html", page=page)


# ───────── FAQ & files pages ─────────

def _faq_view(lang: str):
    from ..models import FAQ_CATEGORIES
    items = [f for f in public_faq() if f.show_on_faq_page]
    if lang == "en":
        items = [f for f in items if f.question_en and f.answer_html_en]
        schema = seo.faq_schema([(f.question_en, f.answer_html_en) for f in items])
    else:
        schema = seo.faq_schema([(f.question, f.answer_html) for f in items])
    path = "/en/faq" if lang == "en" else "/faq"
    return render_template("public/faq.html", items=items, categories=FAQ_CATEGORIES, lang=lang,
                           schema=[schema] if schema else [], canonical=current_app.config["SITE_URL"] + path)


@bp.route("/faq")
def faq_page():
    return _faq_view("ar")


@bp.route("/en/faq")
def faq_page_en():
    _english_gate()
    return _faq_view("en")


def _files_view(lang: str):
    from ..publishing import public_files
    path = "/en/files" if lang == "en" else "/files"
    return render_template("public/files.html", files=public_files("page"), lang=lang,
                           canonical=current_app.config["SITE_URL"] + path)


@bp.route("/files")
def files_page():
    return _files_view("ar")


@bp.route("/en/files")
def files_page_en():
    _english_gate()
    return _files_view("en")


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
    crumbs = [(t("الرئيسية"), site + ("/en/" if lang == "en" else "/")), (t("المقالات"), site + _blog_prefix(lang))]
    if category:
        crumbs.append((t(category.name), site + path))
    if tag:
        crumbs.append((t(tag.name), site + path))
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
    _english_gate()
    return _blog_index("en")


@bp.route("/en/blog/category/<slug>")
def blog_category_en(slug: str):
    _english_gate()
    cat = db.session.query(Category).filter_by(slug=slug).first_or_404()
    return _blog_index("en", category=cat)


@bp.route("/en/blog/tag/<slug>")
def blog_tag_en(slug: str):
    _english_gate()
    tag = db.session.query(Tag).filter_by(slug=slug).first_or_404()
    return _blog_index("en", tag=tag)


@bp.route("/blog/category/<slug>")
def blog_category(slug: str):
    cat = db.session.query(Category).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", category=cat)


@bp.route("/blog/tag/<slug>")
def blog_tag(slug: str):
    tag = db.session.query(Tag).filter_by(slug=slug).first_or_404()
    return _blog_index("ar", tag=tag)


@bp.route("/en/business/blog")
def blog_biz_en():
    _english_gate()
    return _blog_index("en", audience="business")


@bp.route("/en/business/blog/category/<slug>")
def blog_biz_category_en(slug: str):
    _english_gate()
    cat = db.session.query(Category).filter_by(slug=slug).first_or_404()
    return _blog_index("en", category=cat, audience="business")


@bp.route("/en/business/blog/tag/<slug>")
def blog_biz_tag_en(slug: str):
    _english_gate()
    tag = db.session.query(Tag).filter_by(slug=slug).first_or_404()
    return _blog_index("en", tag=tag, audience="business")


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
    return (db.session.query(SideCard).filter(SideCard.is_active.is_(True), SideCard.audience.in_([aud, "both"]), SideCard.page_slug == "")
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
    linked_faq = public_faq(article_id=art.id)
    if lang == "en":
        faq_pairs += [(f.question_en, f.answer_html_en) for f in linked_faq if f.question_en and f.answer_html_en]
    else:
        faq_pairs += [(f.question, f.answer_html) for f in linked_faq]
    biz = art.audience == "business" and lang != "en"
    g.lang = art.lang
    home_path, blog_path = ("/business", "/business/blog") if biz else (("/en/" if lang == "en" else "/"), _blog_prefix(lang))
    crumbs = [(t("الرئيسية"), site + home_path), (t("المقالات"), site + blog_path)]
    if art.category:
        crumbs.append((t(art.category.name), f"{site}{blog_path}/category/{art.category.slug}"))
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
    g.lang_alt = translation.path if translation is not None else None  # no translation: no language button
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
    _english_gate()
    return _article_view("en", slug)


def _author_view(slug: str, lang: str):
    person = db.session.query(Author).filter_by(slug=slug).first_or_404()
    site = current_app.config["SITE_URL"]
    articles = [a for a in live_articles(lang) if a.author_id == person.id]
    schema = [{"@context": "https://schema.org", **seo.person_schema(person, site)}]
    prefix = "/en" if lang == "en" else ""
    return render_template("public/author.html", author=person, articles=articles, lang=lang, schema=schema,
                           canonical=f"{site}{prefix}/authors/{slug}")


@bp.route("/authors/<slug>")
def author(slug: str):
    return _author_view(slug, "ar")


@bp.route("/en/authors/<slug>")
def author_en(slug: str):
    _english_gate()
    return _author_view(slug, "en")


@bp.route("/blog/feed.xml")
def rss():
    site = current_app.config["SITE_URL"]
    items = live_articles("ar", limit=30)
    xml = render_template("public/rss.xml", items=items, site=site,
                          now=format_datetime(datetime.now(timezone.utc)), fmt=lambda d: format_datetime(d) if d else "")
    return Response(xml, mimetype="application/rss+xml")


# ───────── sitemap / robots ─────────

def _english_sitemap_urls(site: str) -> list[dict[str, Any]]:
    """Only English addresses that really open: pages with English, and listings with English articles."""
    urls: list[dict[str, Any]] = []
    for page in db.session.query(Page).all():
        if snapshot_has_english(page.published_snapshot):
            path = "/en/" if page.slug == "home" else f"/en/{page.slug}"
            urls.append({"loc": site + path, "lastmod": page.published_at})
    if english_path("/faq"):
        urls.append({"loc": site + "/en/faq", "lastmod": None})
    arts = live_articles("en")
    if not arts:
        return urls
    dates = [d for d in (a.content_updated_at or a.published_at for a in arts) if d is not None]
    urls.append({"loc": site + "/en/blog", "lastmod": max(dates) if dates else None})
    if any(a.audience in ("business", "both") for a in arts):
        urls.append({"loc": site + "/en/business/blog", "lastmod": max(dates) if dates else None})
    for a in arts:
        if not (a.noindex or (a.canonical_url and a.canonical_url != site + a.path)):
            urls.append({"loc": site + a.path, "lastmod": a.content_updated_at or a.published_at})
    used_cats = {a.category_id for a in arts if a.category_id}
    for c in db.session.query(Category).filter(Category.id.in_(used_cats)).all() if used_cats else []:
        urls.append({"loc": f"{site}/en/blog/category/{c.slug}", "lastmod": None})
    for au in db.session.query(Author).all():
        if any(a.author_id == au.id for a in arts):
            urls.append({"loc": f"{site}/en/authors/{au.slug}", "lastmod": None})
    return urls


@bp.route("/sitemap.xml")
def sitemap():
    site = current_app.config["SITE_URL"]
    home = db.session.query(Page).filter_by(slug="home").first()
    urls = [{"loc": site + "/", "lastmod": home.published_at if home else None}]
    biz = db.session.query(Page).filter_by(slug="business").first()
    if biz is not None and biz.published_snapshot is not None:
        urls.append({"loc": site + "/business", "lastmod": biz.published_at})
    for extra in db.session.query(Page).filter(Page.slug.notin_(["home", "business"])).all():
        if extra.published_snapshot is not None:
            urls.append({"loc": f"{site}/{extra.slug}", "lastmod": extra.published_at})
    arts = live_articles("ar")
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
    if english_live():
        urls += _english_sitemap_urls(site)
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
    g.lang_alt = None
    # English stays hidden from visitors until it is switched on, even on a missing /en/ page
    g.lang = "en" if current_lang() == "en" and english_visible() else "ar"
    return render_template("public/404.html", lang=g.lang), 404


@bp.app_template_global()
def now_year() -> int:
    return utcnow().year


# ───────── site icons (favicon etc.), served from the site root ─────────
import os as _os

_ICONS_DIR = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "static", "icons"))
_ICON_NAMES = ("favicon.ico", "favicon.svg", "favicon-96x96.png", "apple-touch-icon.png", "site.webmanifest",
               "web-app-manifest-192x192.png", "web-app-manifest-512x512.png")


def _make_icon_view(name: str):
    def view():
        if not _os.path.isfile(_os.path.join(_ICONS_DIR, name)):
            abort(404)
        mt = "application/manifest+json" if name.endswith(".webmanifest") else None
        return send_from_directory(_ICONS_DIR, name, mimetype=mt, max_age=60 * 60 * 24 * 7)
    return view


for _n in _ICON_NAMES:
    bp.add_url_rule("/" + _n, endpoint="icon_" + _n.replace(".", "_").replace("-", "_"), view_func=_make_icon_view(_n))
