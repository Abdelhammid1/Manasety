"""Articles: editor with SEO fields, quality checks, internal-link suggestions, workflow
(draft → review → scheduled/published → archived), revisions and preview."""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import ARTICLE_STATUSES, Article, Author, Category, Media, Revision, Tag, utcnow
from ..publishing import live_articles
from ..security import add_revision, audit, clean_rich, clean_text, permission_required
from ..services.seo import article_checks, slugify, suggest_internal_links
from ..settings_store import get_setting

bp = Blueprint("admin_articles", __name__, url_prefix="/admin/articles")

TEXT_FIELDS = ("title", "h1", "excerpt", "meta_title", "meta_description", "focus_keyword", "secondary_keywords", "canonical_url")


@bp.route("/")
@permission_required("articles")
def index():
    q = db.session.query(Article)
    status = request.args.get("status")
    if status in ARTICLE_STATUSES:
        q = q.filter_by(status=status)
    rows = q.order_by(Article.updated_at.desc()).all()
    return render_template("admin/articles.html", rows=rows, statuses=ARTICLE_STATUSES, status=status)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:aid>", methods=["GET", "POST"])
@permission_required("articles")
def edit(aid: int | None = None):
    art = db.session.get(Article, aid) if aid else Article(lang="ar", status="draft", related_mode="auto", faq=[], related_ids=[])
    if art is None:
        abort(404)
    if request.method == "POST":
        with db.session.no_autoflush:  # validation queries must not flush half-edited rows
            return _save(art, aid)
    return _render_form(art, aid)


def _save(art: Article, aid: int | None):
    before = art.to_snapshot() if aid else None
    old_status, old_content = art.status, art.content_html
    for key in TEXT_FIELDS:
        setattr(art, key, clean_text(request.form.get(key, ""))[:500])
    art.lang = "en" if request.form.get("lang") == "en" else "ar"
    art.content_html = clean_rich(request.form.get("content_html", ""))
    art.slug = slugify(request.form.get("slug") or art.title)
    art.noindex = request.form.get("noindex") == "on"
    art.audience = request.form.get("audience") if request.form.get("audience") in ("schools", "business") else "both"
    art.human_reviewed = request.form.get("human_reviewed") == "on"
    art.related_mode = "manual" if request.form.get("related_mode") == "manual" else "auto"
    art.related_ids = [int(x) for x in request.form.getlist("related_ids") if x.isdigit()][:6]
    for fk in ("category_id", "author_id", "cover_id", "og_image_id", "translation_of_id"):
        raw = request.form.get(fk, "")
        setattr(art, fk, int(raw) if raw.isdigit() else None)
    tag_ids = [int(x) for x in request.form.getlist("tag_ids") if x.isdigit()]
    art.tags = db.session.query(Tag).filter(Tag.id.in_(tag_ids)).all() if tag_ids else []
    art.faq = [{"q": clean_text(q), "a": clean_rich(a)}
               for q, a in zip(request.form.getlist("faq_q"), request.form.getlist("faq_a")) if clean_text(q) and a.strip()]

    errors = []
    if not art.title:
        errors.append("العنوان مطلوب.")
    clash = db.session.query(Article).filter(Article.lang == art.lang, Article.slug == art.slug, Article.id != (aid or 0)).first()
    if clash:
        errors.append(f"الرابط /{art.slug} مستخدم في مقال آخر.")
    new_status = request.form.get("status", art.status)
    if new_status not in ARTICLE_STATUSES:
        new_status = "draft"
    if new_status in ("published", "scheduled"):
        if not art.human_reviewed:
            errors.append("لا يُنشر مقال قبل المراجعة البشرية (فعّل «تمت المراجعة البشرية»).")
        if art.cover_id is None:
            errors.append("الصورة الرئيسية مطلوبة قبل النشر.")
        if not art.author_id:
            errors.append("حدد الكاتب قبل النشر.")
        if not art.meta_description:
            errors.append("الـ Meta Description مطلوب قبل النشر.")
    when = _parse_dt(request.form.get("published_at", ""))
    if new_status == "scheduled" and (when is None or when <= utcnow()):
        errors.append("حدد تاريخ نشر في المستقبل للجدولة.")
    if errors:
        for e in errors:
            flash(e, "error")
        return _render_form(art, aid)

    if new_status == "published":
        art.published_at = art.published_at if (old_status == "published" and art.published_at) else (when or utcnow())
    elif new_status == "scheduled":
        art.published_at = when
    art.status = new_status
    if old_status == "published" and old_content != art.content_html:
        art.content_updated_at = utcnow()  # shown to readers and used as dateModified
    if not aid:
        db.session.add(art)
    db.session.flush()
    if aid:
        add_revision("article", art.id, before, note="قبل التعديل")
    audit("update" if aid else "create", "article", art.id, before=before, after=art.to_snapshot(),
          summary=f"{art.title} ({ARTICLE_STATUSES[art.status]})")
    db.session.commit()
    flash("تم الحفظ.", "ok")
    return redirect(url_for("admin_articles.edit", aid=art.id))


def _render_form(art: Article, aid: int | None):
    others = [a for a in db.session.query(Article).order_by(Article.title).all() if a.id != aid]
    suggestions = suggest_internal_links(art, live_articles(art.lang or "ar")) if aid else []
    checks = article_checks(art, get_setting("product_page_url") or "/", int(get_setting("internal_links_min_related") or 2))
    return render_template(
        "admin/article_form.html", art=art, aid=aid, statuses=ARTICLE_STATUSES,
        categories=db.session.query(Category).order_by(Category.name).all(),
        tags=db.session.query(Tag).order_by(Tag.name).all(),
        authors=db.session.query(Author).order_by(Author.name).all(),
        images=db.session.query(Media).filter_by(kind="image").order_by(Media.id.desc()).limit(200).all(),
        others=others, suggestions=suggestions, checks=checks,
        revisions=(db.session.query(Revision).filter_by(entity_type="article", entity_id=aid)
                   .order_by(Revision.id.desc()).limit(30).all() if aid else []),
    )


@bp.route("/<int:aid>/preview")
@permission_required("articles")
def preview(aid: int):
    art = db.session.get(Article, aid) or abort(404)
    from ..public.routes import _article_view
    return _article_view(art.lang, art.slug, preview_article=art)


@bp.route("/<int:aid>/restore/<int:rid>", methods=["POST"])
@permission_required("articles")
def restore(aid: int, rid: int):
    art = db.session.get(Article, aid) or abort(404)
    rev = db.session.get(Revision, rid)
    if rev is None or rev.entity_type != "article" or rev.entity_id != aid:
        abort(404)
    before = art.to_snapshot()
    add_revision("article", art.id, before, note="قبل الاسترجاع")
    for key, value in rev.snapshot.items():
        if key in before:
            setattr(art, key, value)
    audit("restore", "article", art.id, before=before, after=art.to_snapshot())
    db.session.commit()
    flash("تم استرجاع النسخة.", "ok")
    return redirect(url_for("admin_articles.edit", aid=aid))


@bp.route("/<int:aid>/delete", methods=["POST"])
@permission_required("articles")
def delete(aid: int):
    art = db.session.get(Article, aid) or abort(404)
    if art.status == "published":
        flash("أرشِف المقال المنشور بدل حذفه، وأضف تحويل 301 لرابطه إن لزم.", "error")
        return redirect(url_for("admin_articles.edit", aid=aid))
    audit("delete", "article", aid, before=art.to_snapshot())
    db.session.delete(art)
    db.session.commit()
    flash("تم الحذف.", "ok")
    return redirect(url_for("admin_articles.index"))
