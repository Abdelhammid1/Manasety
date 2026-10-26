"""Leads: list/filter, status pipeline, notes, CSV export, resend to integrations."""
from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import LEAD_STATUSES, Lead
from ..security import audit, clean_text, permission_required
from ..services.leads import forward_lead

bp = Blueprint("admin_leads", __name__, url_prefix="/admin/leads")

EXPORT_COLUMNS = ["id", "created_at", "status", "form", "name", "school", "company", "phone", "email", "stage",
                  "business_type", "service", "message", "source", "utm_source", "utm_medium", "utm_campaign",
                  "utm_term", "utm_content", "referrer", "landing_path", "notes"]


def _filtered():
    q = db.session.query(Lead)
    if request.args.get("status") in LEAD_STATUSES:
        q = q.filter_by(status=request.args["status"])
    if request.args.get("utm_source"):
        q = q.filter(Lead.utm_source == request.args["utm_source"])
    term = (request.args.get("q") or "").strip()
    if term:
        like = f"%{term}%"
        q = q.filter(Lead.name.ilike(like) | Lead.phone.ilike(like) | Lead.school.ilike(like) | Lead.company.ilike(like))
    return q.order_by(Lead.id.desc())


@bp.route("/")
@permission_required("leads")
def index():
    rows = _filtered().limit(500).all()
    sources = [r[0] for r in db.session.query(Lead.utm_source).distinct() if r[0]]
    return render_template("admin/leads.html", rows=rows, statuses=LEAD_STATUSES, sources=sources)


@bp.route("/<int:lid>", methods=["GET", "POST"])
@permission_required("leads")
def detail(lid: int):
    lead = db.session.get(Lead, lid) or abort(404)
    if request.method == "POST":
        before = {"status": lead.status, "notes": lead.notes}
        if request.form.get("status") in LEAD_STATUSES:
            lead.status = request.form["status"]
        lead.notes = clean_text(request.form.get("notes", ""))[:5000]
        audit("update", "lead", lead.id, before=before, after={"status": lead.status, "notes": lead.notes})
        db.session.commit()
        flash("تم الحفظ.", "ok")
        return redirect(url_for("admin_leads.detail", lid=lid))
    return render_template("admin/lead_detail.html", lead=lead, statuses=LEAD_STATUSES)


@bp.route("/<int:lid>/resend", methods=["POST"])
@permission_required("leads")
def resend(lid: int):
    lead = db.session.get(Lead, lid) or abort(404)
    forward_lead(lead.id)
    audit("resend", "lead", lead.id)
    db.session.commit()
    flash("أُعيد إرسال الطلب للتكاملات. حدّث الصفحة لرؤية النتيجة.", "ok")
    return redirect(url_for("admin_leads.detail", lid=lid))


def _csv_safe(value: object) -> str:
    """Neutralise spreadsheet formulas (CSV injection) — leads are visitor-typed text."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.route("/export.csv")
@permission_required("leads")
def export():
    buf = io.StringIO()
    buf.write("﻿")  # Excel opens UTF-8 Arabic correctly with a BOM
    writer = csv.writer(buf)
    writer.writerow(EXPORT_COLUMNS)
    for lead in _filtered().all():
        writer.writerow([_csv_safe(getattr(lead, c)) for c in EXPORT_COLUMNS])
    audit("export", "lead", None, summary="تصدير CSV")
    db.session.commit()
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=manasety-leads.csv"})
