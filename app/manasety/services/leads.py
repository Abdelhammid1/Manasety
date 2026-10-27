"""Lead intake. The DB row is written first (source of truth); forwarding to Marsoud CRM,
web3forms (email backup), SMTP and n8n happens afterwards and never blocks the visitor."""
from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage
from typing import Any

import requests
from flask import Flask, current_app

from ..extensions import db
from ..models import LEAD_STATUSES, Lead

UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
TIMEOUT = 8


def build_lead(form: Any, form_kind: str) -> tuple[Lead | None, list[str]]:
    def val(key: str, limit: int = 255) -> str:
        value = form.get(key)
        return value.strip()[:limit] if isinstance(value, str) else ""

    errors = []
    name, phone = val("name"), val("phone", 60)
    if not name:
        errors.append("الاسم مطلوب.")
    digits = sum(ch.isdigit() for ch in phone)
    if digits < 8:
        errors.append("رقم الهاتف غير صحيح.")
    if errors:
        return None, errors

    lead = Lead(
        form=form_kind if form_kind in ("demo", "contact") else "demo",
        name=name, phone=phone, school=val("school"), company=val("company"), email=val("email"),
        stage=val("stage", 120), business_type=val("business_type", 120), service=val("service", 120),
        message=val("message", 5000), source=val("source", 60) or f"{form_kind}_form",
        referrer=val("referrer", 1000), landing_path=val("landing_path", 500), status="new",
    )
    for key in UTM_KEYS:
        setattr(lead, key, val(key))
    return lead, []


def forward_lead(lead_id: int) -> None:
    app = current_app._get_current_object()  # type: ignore[attr-defined]
    if app.config.get("LEAD_FORWARD_SYNC"):
        _forward(app, lead_id)
    else:
        threading.Thread(target=_forward, args=(app, lead_id), daemon=True).start()


def _forward(app: Flask, lead_id: int) -> None:
    with app.app_context():
        lead = db.session.get(Lead, lead_id)
        if lead is None:
            return
        log: dict[str, str] = {}
        for name, fn in (("marsoud", _to_marsoud), ("web3forms", _to_web3forms),
                         ("email", _to_email), ("n8n", _to_n8n)):
            try:
                log[name] = fn(app, lead)
            except Exception as exc:  # never let one channel break the others
                log[name] = f"error: {exc.__class__.__name__}: {str(exc)[:200]}"
        lead.forward_log = log
        db.session.commit()


def _description(lead: Lead) -> str:
    parts = []
    if lead.school:
        parts.append(f"المدرسة: {lead.school}")
    if lead.stage:
        parts.append(f"المرحلة: {lead.stage}")
    if lead.business_type:
        parts.append(f"نوع النشاط: {lead.business_type}")
    if lead.message:
        parts.append(lead.message)
    return "\n".join(parts)


def _to_marsoud(app: Flask, lead: Lead) -> str:
    token = app.config.get("MARSOUD_CONTACT_TOKEN")
    if not token:
        return "skipped: MARSOUD_CONTACT_TOKEN not set"
    # Same payload contract as the legacy page (MARSOUD-CONTACT-LEAD-01).
    payload = {
        "name": lead.name,
        "phone": lead.phone,
        "company_name": lead.school or lead.company,
        "service_type": lead.service or ("عرض توضيحي منصتي-سكول" if lead.form == "demo" else "استشارة"),
        "package": "",
        "description": _description(lead),
        "ad_variant": lead.utm_content or "",
        "source": "landing_form",  # marsoud only accepts landing_form / contact_page / website
    }
    r = requests.post(app.config["MARSOUD_LEAD_URL"], json=payload, timeout=TIMEOUT,
                      headers={"X-Contact-Form-Token": token})
    return f"{r.status_code}"


def _to_web3forms(app: Flask, lead: Lead) -> str:
    key = app.config.get("WEB3FORMS_ACCESS_KEY")
    if not key:
        return "skipped: WEB3FORMS_ACCESS_KEY not set"
    data = {
        "access_key": key,
        "subject": "طلب جديد من موقع منصتي",
        "name": lead.name, "phone": lead.phone, "company": lead.school or lead.company,
        "service": lead.service, "message": _description(lead), "email": lead.email,
        "source": lead.source,
    }
    r = requests.post("https://api.web3forms.com/submit", data=data, timeout=TIMEOUT)
    return f"{r.status_code}"


def _to_email(app: Flask, lead: Lead) -> str:
    user, pwd, to = app.config.get("SMTP_USER"), app.config.get("SMTP_PASSWORD"), app.config.get("LEAD_NOTIFY_TO")
    if not (user and pwd and to):
        return "skipped: SMTP not configured"
    msg = EmailMessage()
    msg["Subject"] = f"طلب جديد ({lead.form}) — {lead.name}"
    msg["From"] = app.config.get("SMTP_FROM") or user
    msg["To"] = to
    lines = [f"{k}: {v}" for k, v in (
        ("الاسم", lead.name), ("الهاتف", lead.phone), ("البريد", lead.email), ("المدرسة", lead.school),
        ("الشركة", lead.company), ("المرحلة", lead.stage), ("نوع النشاط", lead.business_type),
        ("الخدمة", lead.service), ("الرسالة", lead.message), ("المصدر", lead.source),
        ("UTM", " / ".join(filter(None, (lead.utm_source, lead.utm_medium, lead.utm_campaign)))),
        ("الحالة", LEAD_STATUSES.get(lead.status, lead.status)),
    ) if v]
    lines.append(f"\n{app.config['SITE_URL']}/admin/leads/{lead.id}")
    msg.set_content("\n".join(lines))
    with smtplib.SMTP(app.config["SMTP_HOST"], app.config["SMTP_PORT"], timeout=TIMEOUT) as smtp:
        smtp.starttls()
        smtp.login(user, pwd)
        smtp.send_message(msg)
    return "sent"


def _to_n8n(app: Flask, lead: Lead) -> str:
    url = app.config.get("N8N_LEAD_WEBHOOK_URL")
    if not url:
        return "skipped: N8N_LEAD_WEBHOOK_URL not set"
    payload = {c.name: getattr(lead, c.key) for c in Lead.__table__.columns if c.name != "forward_log"}
    payload["created_at"] = lead.created_at.isoformat() if lead.created_at else None
    r = requests.post(url, json=payload, timeout=TIMEOUT)
    return f"{r.status_code}"
