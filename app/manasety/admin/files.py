"""Displayed files (company profile, portfolio): rename without re-upload, hide from pages while
the direct link keeps working (Sector Bot sends it), replace in place so the URL never changes."""
from __future__ import annotations

import re
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import FILE_PLACEMENTS, DisplayFile, Media
from ..security import audit, clean_text, permission_required, snapshot_model
from ..services.media import PRIVATE_DIR, media_dir, sniff

bp = Blueprint("admin_files", __name__, url_prefix="/admin/files")

_PATH_RE = re.compile(r"[a-z0-9][a-z0-9\-_.]{1,120}\.pdf")


@bp.route("/")
@permission_required("files")
def index():
    files = db.session.query(DisplayFile).order_by(DisplayFile.position, DisplayFile.id).all()
    return render_template("admin/files.html", files=files, placements=FILE_PLACEMENTS)


@bp.route("/new", methods=["GET", "POST"])
@bp.route("/<int:fid>", methods=["GET", "POST"])
@permission_required("files")
def edit(fid: int | None = None):
    f = db.session.get(DisplayFile, fid) if fid else DisplayFile(placements=[], is_visible=True, direct_link_enabled=True)
    if f is None:
        abort(404)
    if request.method == "POST":
        before = snapshot_model(f) if fid else None
        f.display_name = clean_text(request.form.get("display_name", ""))
        f.display_name_en = clean_text(request.form.get("display_name_en", ""))
        f.description = clean_text(request.form.get("description", ""))
        f.placements = [p for p in request.form.getlist("placements") if p in FILE_PLACEMENTS]
        f.is_visible = request.form.get("is_visible") == "on"
        f.show_counter = request.form.get("show_counter") == "on"
        f.position = request.form.get("position", 0, type=int) or 0
        cover = request.form.get("cover_id", "")
        f.cover_id = int(cover) if cover.isdigit() else None
        f.external_url = clean_text(request.form.get("external_url", ""))
        if f.external_url and not f.external_url.startswith("https://"):
            flash("الرابط الخارجي يبدأ بـ https://", "error")
            return redirect(request.url)
        new_direct = request.form.get("direct_link_enabled") == "on"
        if fid and f.direct_link_enabled and not new_direct and request.form.get("confirm_disable") != "on":
            flash("إيقاف الرابط المباشر يكسر الرابط المرسل في رسائل Sector Bot. أكّد الخيار صراحةً.", "error")
            return redirect(request.url)
        f.direct_link_enabled = new_direct
        if not fid:
            path = (request.form.get("public_path") or "").strip().lower()
            if not _PATH_RE.fullmatch(path) or db.session.query(DisplayFile).filter_by(public_path=path).first():
                flash("اسم الرابط غير صالح أو مستخدم (مثل company-portfolio.pdf).", "error")
                return redirect(request.url)
            f.public_path = path
        upload = request.files.get("file")
        data = upload.read() if upload and upload.filename else b""
        if data and sniff(data) != "pdf":
            flash("الملف يجب أن يكون PDF.", "error")
            return redirect(request.url)
        if not f.display_name or not (f.stored_filename or data or f.external_url):
            flash("اسم العرض والملف (أو رابط خارجي) مطلوبان.", "error")
            return redirect(request.url)
        # Everything validated: only now touch the disk (a rejected save never changes the live PDF).
        if data:
            if not f.stored_filename:
                f.stored_filename = f"{PRIVATE_DIR}/file-{secrets.token_hex(8)}.pdf"
            target = media_dir() / f.stored_filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)  # same public URL, new content
        if not fid:
            db.session.add(f)
        db.session.flush()
        audit("update" if fid else "create", "display_file", f.id, before=before, after=snapshot_model(f))
        db.session.commit()
        flash("تم الحفظ.", "ok")
        return redirect(url_for("admin_files.index"))
    images = db.session.query(Media).filter_by(kind="image").order_by(Media.id.desc()).limit(200).all()
    return render_template("admin/file_form.html", f=f, fid=fid, placements=FILE_PLACEMENTS, images=images)
