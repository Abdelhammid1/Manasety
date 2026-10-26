"""Media library: content-sniffed uploads, automatic WebP, mandatory alt, safe delete."""
from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user

from ..extensions import db
from ..models import (Article, Author, CaseStudy, Client, DisplayFile, FaqItem, LegalPage, Media, Page, Section,
                      Setting)
from ..security import audit, clean_text, permission_required, snapshot_model
from ..services.media import UploadError, media_dir, save_upload

bp = Blueprint("admin_media", __name__, url_prefix="/admin/media")


def _usages(m: Media) -> list[str]:
    """Where a media item is referenced, so it is never deleted out from under a page."""
    used = []
    used += [f"عميل: {c.name}" for c in db.session.query(Client).filter((Client.logo_id == m.id) | (Client.consent_proof_id == m.id))]
    used += [f"مقال: {a.title}" for a in db.session.query(Article).filter((Article.cover_id == m.id) | (Article.og_image_id == m.id))]
    used += [f"كاتب: {a.name}" for a in db.session.query(Author).filter(Author.photo_id == m.id)]
    used += [f"ملف: {f.display_name}" for f in db.session.query(DisplayFile).filter(DisplayFile.cover_id == m.id)]
    used += [f"دراسة حالة #{c.id}" for c in db.session.query(CaseStudy).all() if m.id in (c.media_ids or [])]
    for s in db.session.query(Section).all():
        if any(lang.get("image") == m.id for lang in (s.content or {}).values() if isinstance(lang, dict)):
            used.append(f"قسم (مسودة): {s.admin_label}")
    for p in db.session.query(Page).all():
        for snap in (p.published_snapshot, p.scheduled_snapshot):
            if snap and (f'"image": {m.id}' in json.dumps(snap) or m.filename in json.dumps(snap, ensure_ascii=False)):
                used.append(f"الصفحة المنشورة/المجدولة: {p.title}")
                break
        if m.filename in json.dumps([p.seo, p.published_seo], ensure_ascii=False):
            used.append(f"SEO الصفحة: {p.title}")
    texts = [("مقال", a.content_html) for a in db.session.query(Article).all()]
    texts += [("سؤال شائع", f"{q.answer_html} {q.answer_html_en}") for q in db.session.query(FaqItem).all()]
    texts += [("صفحة قانونية", lp.body_html) for lp in db.session.query(LegalPage).all()]
    texts += [("قسم نص حر", json.dumps(s.content, ensure_ascii=False)) for s in db.session.query(Section).all()]
    texts += [("الإعدادات", json.dumps(st.value, ensure_ascii=False)) for st in db.session.query(Setting).all()]
    for label, text in texts:
        if m.filename in (text or ""):
            used.append(f"داخل نص: {label}")
    return sorted(set(used))


@bp.route("/", methods=["GET", "POST"])
@permission_required("media")
def index():
    if request.method == "POST":
        try:
            m = save_upload(request.files.get("file"), request.form.get("alt", ""), request.form.get("alt_en", ""))  # type: ignore[arg-type]
            m.is_demo_data_checked = request.form.get("demo_checked") == "on"
            if m.kind == "image" and not m.is_demo_data_checked:
                (media_dir() / m.filename).unlink(missing_ok=True)
                raise UploadError("أكّد أن الصورة لا تحتوي اسم أو صورة أو درجة طالب حقيقي.")
            db.session.add(m)
            db.session.flush()
            audit("upload", "media", m.id, after=snapshot_model(m))
            db.session.commit()
            flash("تم الرفع.", "ok")
        except UploadError as exc:
            flash(str(exc), "error")
        return redirect(url_for("admin_media.index"))
    kind = request.args.get("kind")
    q = db.session.query(Media)
    if kind in ("image", "pdf", "video"):
        q = q.filter_by(kind=kind)
    items = q.order_by(Media.id.desc()).limit(500).all()
    return render_template("admin/media.html", items=items, kind=kind,
                           max_mb=current_app.config["MAX_IMAGE_MB"])


@bp.route("/<int:mid>", methods=["GET", "POST"])
@permission_required("media")
def detail(mid: int):
    m = db.session.get(Media, mid) or abort(404)
    if request.method == "POST":
        before = snapshot_model(m)
        alt = clean_text(request.form.get("alt", ""))
        if m.kind == "image" and not alt:
            flash("النص البديل (alt) إلزامي.", "error")
        else:
            m.alt, m.alt_en = alt, clean_text(request.form.get("alt_en", ""))
            audit("update", "media", m.id, before=before, after=snapshot_model(m))
            db.session.commit()
            flash("تم الحفظ.", "ok")
        return redirect(url_for("admin_media.detail", mid=mid))
    return render_template("admin/media_detail.html", m=m, usages=_usages(m))


@bp.route("/<int:mid>/file")
@permission_required("media")
def raw(mid: int):
    """Admin-side view of any media item, including private consent proofs."""
    m = db.session.get(Media, mid) or abort(404)
    return send_from_directory(media_dir(), m.filename, mimetype=m.mime)


@bp.route("/<int:mid>/delete", methods=["POST"])
@permission_required("media")
def delete(mid: int):
    m = db.session.get(Media, mid) or abort(404)
    used = _usages(m)
    if used:
        flash("لا يمكن الحذف؛ الملف مستخدم في: " + "، ".join(used), "error")
        return redirect(url_for("admin_media.detail", mid=mid))
    audit("delete", "media", m.id, before=snapshot_model(m))
    (media_dir() / m.filename).unlink(missing_ok=True)
    db.session.delete(m)
    db.session.commit()
    flash("تم الحذف.", "ok")
    return redirect(url_for("admin_media.index"))
