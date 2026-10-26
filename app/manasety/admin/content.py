"""Page builder: sections (blocks), order, visibility, draft → publish, schedule, preview, revisions, page SEO."""
from __future__ import annotations

import secrets
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

from ..blocks import BLOCK_TYPES, field_specs, parse_block_form
from ..extensions import db
from ..models import Page, Revision, Section
from ..publishing import draft_snapshot, publish_page, schedule_page
from ..security import audit, clean_text, permission_required

bp = Blueprint("admin_content", __name__, url_prefix="/admin/pages")

LANGS = {"ar": "العربية", "en": "English"}


def _page(slug: str = "home") -> Page:
    return db.session.query(Page).filter_by(slug=slug).first() or abort(404)


def _section(page: Page, sid: int) -> Section:
    sec = db.session.get(Section, sid)
    if sec is None or sec.page_id != page.id:
        abort(404)
    return sec


def _renumber(page: Page) -> None:
    for i, s in enumerate(sorted(page.sections, key=lambda x: x.position)):
        s.position = i


@bp.route("/")
@bp.route("/<slug>")
@permission_required("content")
def page_builder(slug: str = "home"):
    page = _page(slug)
    sections = sorted(page.sections, key=lambda s: s.position)
    sid = request.args.get("s", type=int)
    selected = next((s for s in sections if s.id == sid), sections[0] if sections else None)
    lang = request.args.get("lang", "ar") if request.args.get("lang") in LANGS else "ar"
    draft_differs = page.published_snapshot != draft_snapshot(page)
    return render_template(
        "admin/page_builder.html", page=page, sections=sections, selected=selected, lang=lang, langs=LANGS,
        block_types=BLOCK_TYPES, specs=field_specs(selected.block_type) if selected else [],
        content=(selected.content or {}).get(lang, {}) if selected else {}, draft_differs=draft_differs,
    )


@bp.route("/<slug>/sections/<int:sid>", methods=["POST"])
@permission_required("content")
def save_section(slug: str, sid: int):
    page = _page(slug)
    sec = _section(page, sid)
    lang = request.form.get("lang", "ar") if request.form.get("lang") in LANGS else "ar"
    before = sec.to_snapshot()
    content = dict(sec.content or {})
    content[lang] = parse_block_form(sec.block_type, request.form, lang)
    sec.content = content
    sec.admin_label = clean_text(request.form.get("admin_label") or sec.admin_label)[:120]
    anchor = clean_text(request.form.get("anchor") or "").strip("#")[:60]
    if anchor and not all(ch.isalnum() or ch in "-_" for ch in anchor):
        flash("الـ anchor حروف لاتينية وأرقام و - فقط.", "error")
    else:
        sec.anchor = anchor
    audit("update", "section", sec.id, before=before, after=sec.to_snapshot(), summary=f"تعديل مسودة: {sec.admin_label}")
    db.session.commit()
    flash("تم حفظ المسودة. اضغط «نشر التغييرات» لتظهر للزوار.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug, s=sid, lang=lang))


@bp.route("/<slug>/sections/<int:sid>/toggle", methods=["POST"])
@permission_required("content")
def toggle_section(slug: str, sid: int):
    page = _page(slug)
    sec = _section(page, sid)
    sec.is_visible = not sec.is_visible
    audit("toggle", "section", sec.id, after={"is_visible": sec.is_visible}, summary=sec.admin_label)
    db.session.commit()
    return redirect(url_for("admin_content.page_builder", slug=slug, s=sid))


@bp.route("/<slug>/reorder", methods=["POST"])
@permission_required("content")
def reorder(slug: str):
    page = _page(slug)
    ids = [int(x) for x in (request.get_json(silent=True) or {}).get("order", []) if str(x).isdigit()]
    by_id = {s.id: s for s in page.sections}
    if sorted(ids) != sorted(by_id):
        return jsonify(ok=False, error="قائمة الأقسام غير مكتملة"), 400
    before = [s.id for s in sorted(page.sections, key=lambda x: x.position)]
    for pos, sid in enumerate(ids):
        by_id[sid].position = pos
    audit("reorder", "page", page.id, before=before, after=ids)
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/<slug>/sections", methods=["POST"])
@permission_required("content")
def add_section(slug: str):
    page = _page(slug)
    block_type = request.form.get("block_type")
    if block_type not in BLOCK_TYPES:
        abort(400)
    sec = Section(page_id=page.id, block_type=block_type, admin_label=BLOCK_TYPES[block_type]["label"],
                  position=len(page.sections), is_visible=False, content={"ar": {}, "en": {}})
    db.session.add(sec)
    db.session.flush()
    audit("create", "section", sec.id, after=sec.to_snapshot())
    db.session.commit()
    flash("أُضيف القسم مخفيًا. املأ حقوله ثم أظهره.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug, s=sec.id))


@bp.route("/<slug>/sections/<int:sid>/delete", methods=["POST"])
@permission_required("content")
def delete_section(slug: str, sid: int):
    page = _page(slug)
    sec = _section(page, sid)
    audit("delete", "section", sec.id, before=sec.to_snapshot())
    db.session.delete(sec)
    db.session.flush()
    _renumber(page)
    db.session.commit()
    flash("حُذف القسم من المسودة (النسخة المنشورة لا تتغير قبل النشر).", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug))


@bp.route("/<slug>/publish", methods=["POST"])
@permission_required("content")
def publish(slug: str):
    page = _page(slug)
    publish_page(page, note=clean_text(request.form.get("note") or "نشر")[:255])
    db.session.commit()
    flash("تم النشر. الصفحة العامة محدّثة الآن.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug))


@bp.route("/<slug>/schedule", methods=["POST"])
@permission_required("content")
def schedule(slug: str):
    page = _page(slug)
    if request.form.get("cancel"):
        page.scheduled_at, page.scheduled_snapshot = None, None
        audit("unschedule", "page", page.id)
        db.session.commit()
        flash("أُلغيت الجدولة.", "ok")
        return redirect(url_for("admin_content.page_builder", slug=slug))
    try:
        # The form sends Cairo local time; store UTC (Egypt is UTC+2 / +3 in summer — the field carries the offset).
        when = datetime.fromisoformat(request.form["when"])
    except (KeyError, ValueError):
        flash("صيغة التاريخ غير صحيحة.", "error")
        return redirect(url_for("admin_content.page_builder", slug=slug))
    if when.tzinfo is not None:
        from datetime import timezone
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
    schedule_page(page, when)
    db.session.commit()
    flash("تمت جدولة المسودة الحالية للنشر.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug))


@bp.route("/<slug>/preview-token", methods=["POST"])
@permission_required("content")
def rotate_preview(slug: str):
    page = _page(slug)
    page.preview_token = secrets.token_urlsafe(24)
    audit("rotate_preview", "page", page.id)
    db.session.commit()
    flash("تم تغيير رابط المعاينة؛ الرابط القديم لم يعد يعمل.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug))


@bp.route("/<slug>/revisions")
@permission_required("content")
def revisions(slug: str):
    page = _page(slug)
    revs = (db.session.query(Revision).filter_by(entity_type="page", entity_id=page.id)
            .order_by(Revision.id.desc()).limit(100).all())
    return render_template("admin/revisions.html", page=page, revisions=revs)


@bp.route("/<slug>/revisions/<int:rid>/restore", methods=["POST"])
@permission_required("content")
def restore(slug: str, rid: int):
    """Load a published version back into the draft. Nothing goes live until Publish."""
    page = _page(slug)
    rev = db.session.get(Revision, rid)
    if rev is None or rev.entity_type != "page" or rev.entity_id != page.id:
        abort(404)
    before = draft_snapshot(page)
    for sec in list(page.sections):
        db.session.delete(sec)
    db.session.flush()
    for pos, snap in enumerate(rev.snapshot.get("sections", [])):
        db.session.add(Section(page_id=page.id, block_type=snap["block_type"], admin_label=snap.get("admin_label", ""),
                               anchor=snap.get("anchor", ""), position=pos, is_visible=snap.get("is_visible", True),
                               content=snap.get("content", {})))
    if rev.snapshot.get("seo") is not None:
        page.seo = rev.snapshot["seo"]
    audit("restore", "page", page.id, before=before, after={"revision": rid})
    db.session.commit()
    flash("تم استرجاع النسخة إلى المسودة. راجعها ثم انشر.", "ok")
    return redirect(url_for("admin_content.page_builder", slug=slug))


@bp.route("/<slug>/seo", methods=["GET", "POST"])
@permission_required("content")
def page_seo(slug: str):
    page = _page(slug)
    if request.method == "POST":
        before = page.seo
        seo = dict(page.seo or {})
        for lang in LANGS:
            seo[lang] = {k: clean_text(request.form.get(f"{lang}__{k}", ""))
                         for k in ("title", "description", "og_image", "software_name")}
        page.seo = seo
        audit("update", "page_seo", page.id, before=before, after=seo)
        db.session.commit()
        flash("تم حفظ الـ SEO في المسودة؛ يظهر بعد النشر.", "ok")
        return redirect(url_for("admin_content.page_seo", slug=slug))
    return render_template("admin/page_seo.html", page=page, langs=LANGS)
