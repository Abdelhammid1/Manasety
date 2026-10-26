"""Legal pages (privacy/terms/refund). Same URLs that were filed with PayTabs; full history + restore."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import LegalPage, Revision
from ..security import add_revision, audit, clean_legal, clean_text, permission_required

bp = Blueprint("admin_legal", __name__, url_prefix="/admin/legal")


def _snap(p: LegalPage) -> dict:
    return {"title": p.title, "meta_description": p.meta_description, "body_html": p.body_html,
            "last_updated": p.last_updated.isoformat() if p.last_updated else None}


@bp.route("/")
@permission_required("legal")
def index():
    return render_template("admin/legal_list.html", pages=db.session.query(LegalPage).order_by(LegalPage.id).all())


@bp.route("/<slug>", methods=["GET", "POST"])
@permission_required("legal")
def edit(slug: str):
    page = db.session.query(LegalPage).filter_by(slug=slug).first() or abort(404)
    if request.method == "POST":
        if request.form.get("ack_paytabs") != "on":
            flash("أكّد أنك راجعت تنبيه PayTabs قبل الحفظ.", "error")
            return redirect(request.url)
        before = _snap(page)
        add_revision("legal", page.id, before, note="قبل التعديل")
        page.title = clean_text(request.form.get("title", page.title))
        page.meta_description = clean_text(request.form.get("meta_description", ""))
        page.body_html = clean_legal(request.form.get("body_html", ""))
        try:
            page.last_updated = date.fromisoformat(request.form.get("last_updated") or "")
        except ValueError:
            pass
        audit("update", "legal_page", page.id, before=before, after=_snap(page), summary=f"تعديل {slug}.html")
        db.session.commit()
        flash("تم الحفظ والنشر. النسخة السابقة محفوظة في السجل.", "ok")
        return redirect(url_for("admin_legal.edit", slug=slug))
    revs = (db.session.query(Revision).filter_by(entity_type="legal", entity_id=page.id)
            .order_by(Revision.id.desc()).limit(50).all())
    return render_template("admin/legal_form.html", page=page, revisions=revs)


@bp.route("/<slug>/restore/<int:rid>", methods=["POST"])
@permission_required("legal")
def restore(slug: str, rid: int):
    page = db.session.query(LegalPage).filter_by(slug=slug).first() or abort(404)
    rev = db.session.get(Revision, rid)
    if rev is None or rev.entity_type != "legal" or rev.entity_id != page.id:
        abort(404)
    before = _snap(page)
    add_revision("legal", page.id, before, note="قبل الاسترجاع")
    page.title = rev.snapshot["title"]
    page.meta_description = rev.snapshot["meta_description"]
    page.body_html = rev.snapshot["body_html"]
    if rev.snapshot.get("last_updated"):
        page.last_updated = date.fromisoformat(rev.snapshot["last_updated"])
    audit("restore", "legal_page", page.id, before=before, after=_snap(page))
    db.session.commit()
    flash("تم استرجاع النسخة.", "ok")
    return redirect(url_for("admin_legal.edit", slug=slug))
