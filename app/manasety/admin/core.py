"""Dashboard home, site settings (nav, footer, contacts, locked legal fields), users, audit log, backups."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..extensions import db
from ..models import (ROLES, Article, AuditLog, Author, Client, Fact, Feature, Lead, Page, User, utcnow)
from ..security import admin_required, audit, clean_text, snapshot_model
from ..settings_store import DEFAULTS, LOCKED_KEYS, all_settings, set_setting

bp = Blueprint("admin_core", __name__, url_prefix="/admin")

# Without these, leads still save to the DB but stop reaching Marsoud CRM / the web3forms email backup.
REQUIRED_LEAD_ENV = ("MARSOUD_CONTACT_TOKEN", "WEB3FORMS_ACCESS_KEY")


@bp.route("/")
def dashboard():
    page = db.session.query(Page).filter_by(slug="home").first()
    stats = {
        "new_leads": db.session.query(Lead).filter_by(status="new").count(),
        "leads_total": db.session.query(Lead).count(),
        "articles_live": db.session.query(Article).filter_by(status="published").count(),
        "articles_draft": db.session.query(Article).filter(Article.status.in_(["draft", "review"])).count(),
        "clients_waiting_consent": len([c for c in db.session.query(Client).all() if not c.is_publishable]),
        "facts_unverified": len([f for f in db.session.query(Fact).all() if not f.is_publishable]),
        "features_soon": db.session.query(Feature).filter_by(status="soon").count(),
    }
    draft_differs = bool(page and page.published_snapshot != [s.to_snapshot() for s in page.sections])
    recent = db.session.query(AuditLog).order_by(AuditLog.id.desc()).limit(8).all() if current_user.can("__admin_only__") else []
    latest_leads = db.session.query(Lead).order_by(Lead.id.desc()).limit(5).all() if current_user.can("leads") else []
    missing_env = [k for k in REQUIRED_LEAD_ENV if not current_app.config.get(k)]
    return render_template("admin/dashboard.html", stats=stats, page=page, draft_differs=draft_differs,
                           recent=recent, latest_leads=latest_leads, missing_env=missing_env)


# ───────── settings ─────────

SETTINGS_FORM = [
    ("الهوية والتذييل", [
        ("brand_name_ar", "اسم العلامة (عربي)", "text"), ("brand_name_en", "اسم العلامة (إنجليزي)", "text"),
        ("footer_brand", "اسم التذييل", "text"), ("footer_about", "نبذة التذييل", "textarea"),
        ("footer_about_biz", "نبذة التذييل (صفحة الأعمال)", "textarea"),
        ("footer_tagline_biz", "السطر الأخير (صفحة الأعمال)", "text"),
        ("footer_note", "سطر الخدمة عن بُعد", "text"), ("footer_social_text", "نص الحسابات", "text"),
        ("social_handle", "اسم الحساب", "text"), ("footer_tagline", "السطر الأخير", "text"),
    ]),
    ("البيانات القانونية (Admin فقط — يجب أن تطابق السجل التجاري)", [
        ("legal_name_ar", "الاسم القانوني (عربي)", "text"), ("legal_name_en", "الاسم القانوني (إنجليزي)", "text"),
        ("commercial_registration", "رقم السجل التجاري", "text"),
        ("address_ar", "العنوان (عربي)", "textarea"), ("address_en", "العنوان (إنجليزي)", "textarea"),
    ]),
    ("التواصل", [
        ("email", "البريد", "text"),
        ("whatsapp_eg", "واتساب مصر (أرقام فقط)", "text"), ("whatsapp_eg_display", "واتساب مصر (للعرض)", "text"),
        ("whatsapp_sa", "واتساب السعودية (أرقام فقط)", "text"), ("whatsapp_sa_display", "واتساب السعودية (للعرض)", "text"),
        ("whatsapp_bubble", "نص فقاعة واتساب (فارغ = بدون فقاعة)", "text"),
        ("whatsapp_prefill", "رسالة واتساب الجاهزة", "text"),
        ("whatsapp_prefill_biz", "رسالة واتساب الجاهزة (صفحة الأعمال)", "text"),
        ("show_whatsapp_sa", "إظهار واتساب السعودية في التذييل", "bool"),
        ("show_whatsapp_eg", "إظهار واتساب مصر في التذييل", "bool"),
        ("show_phone_line", "إظهار سطر الاتصال في التذييل", "bool"),
        ("show_footer_social", "إظهار عمود التواصل الرقمي في التذييل", "bool"),
        ("show_footer_note", "إظهار سطر الخدمة عن بُعد", "bool"),
        ("show_footer_copyright", "إظهار سطر حقوق النشر", "bool"),
        ("show_social_float", "إظهار أزرار التواصل العائمة", "bool"),
        ("show_domain_switch", "إظهار مبدل المجالين وبطاقة الدعوة", "bool"),
    ]),
    ("القائمة والروابط", [
        ("nav", "عناصر شريط التنقل", "links"), ("nav_cta_label", "زر الشريط", "text"), ("nav_cta_href", "رابط زر الشريط", "text"),
        ("nav_biz", "عناصر قائمة صفحة الأعمال", "links"),
        ("nav_cta_label_biz", "زر القائمة (الأعمال)", "text"), ("nav_cta_href_biz", "رابط زر القائمة (الأعمال)", "text"),
        ("footer_links", "روابط الوثائق القانونية في التذييل", "links"), ("social", "حسابات التواصل", "social"),
    ]),
    ("صفحة الشكر والكوكيز", [
        ("thank_you_title", "عنوان صفحة الشكر", "text"), ("thank_you_text", "نص صفحة الشكر", "textarea"),
        ("cookie_banner_text", "نص شريط الكوكيز", "text"),
    ]),
    ("المدونة والـ SEO", [
        ("blog_title", "عنوان المدونة", "text"), ("blog_description", "وصف المدونة", "textarea"),
        ("blog_title_biz", "عنوان مدونة الأعمال", "text"),
        ("blog_description_biz", "وصف مدونة الأعمال", "textarea"),
        ("default_og_image_biz", "صورة المشاركة للأعمال (مسار)", "text"),
        ("product_page_url_biz", "رابط صفحة المنتج للأعمال", "text"),
        ("default_og_image", "صورة المشاركة الافتراضية (مسار)", "text"),
        ("product_page_url", "رابط صفحة المنتج (للروابط الداخلية)", "text"),
        ("internal_links_min_related", "أقل عدد روابط لمقالات ذات صلة", "int"),
        ("robots_extra", "أسطر إضافية في robots.txt", "textarea"),
        ("english_enabled", "تفعيل النسخة الإنجليزية (/en/)", "bool"),
    ]),
]


def _parse_rows(prefix: str, keys: tuple[str, str]) -> list[dict]:
    rows = []
    for i in range(60):
        a = clean_text(request.form.get(f"{prefix}__{i}__{keys[0]}", ""))
        b = clean_text(request.form.get(f"{prefix}__{i}__{keys[1]}", ""))
        if a or b:
            rows.append({keys[0]: a, keys[1]: b})
    return rows


@bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    current = all_settings()
    if request.method == "POST":
        before = {}
        after = {}
        for _group, fields in SETTINGS_FORM:
            for key, _label, kind in fields:
                if kind == "links":
                    value = _parse_rows(key, ("label", "href"))
                elif kind == "social":
                    value = _parse_rows(key, ("name", "url"))
                elif kind == "bool":
                    value = request.form.get(key) == "on"
                elif kind == "int":
                    try:
                        value = int(request.form.get(key) or DEFAULTS.get(key, 0))
                    except ValueError:
                        value = DEFAULTS.get(key, 0)
                else:
                    value = clean_text(request.form.get(key, ""))
                if value != current.get(key):
                    before[key], after[key] = current.get(key), value
                    set_setting(key, value)
        if after:
            locked_changed = sorted(set(after) & LOCKED_KEYS)
            audit("update", "settings", None, before=before, after=after,
                  summary=("تعديل بيانات قانونية: " + ", ".join(locked_changed)) if locked_changed else "تعديل الإعدادات")
            db.session.commit()
            flash("تم حفظ الإعدادات.", "ok")
        return redirect(url_for("admin_core.settings"))
    return render_template("admin/settings.html", form=SETTINGS_FORM, values=current, locked=LOCKED_KEYS)


# ───────── users ─────────

@bp.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        role = request.form.get("role")
        if not email or role not in ROLES:
            flash("أدخل بريدًا ودورًا صحيحين.", "error")
        elif db.session.query(User).filter_by(email=email).first():
            flash("هذا البريد مسجّل بالفعل.", "error")
        else:
            temp = secrets.token_urlsafe(12)
            user = User(email=email, name=clean_text(request.form.get("name") or email), role=role,
                        author_id=_author_choice())
            user.set_password(temp)
            db.session.add(user)
            db.session.flush()
            audit("create", "user", user.id, after=snapshot_model(user))
            db.session.commit()
            flash(f"تم إنشاء الحساب. كلمة المرور المؤقتة (تظهر مرة واحدة): {temp}", "ok")
        return redirect(url_for("admin_core.users"))
    return render_template("admin/users.html", users=db.session.query(User).order_by(User.id).all(), roles=ROLES,
                           authors=db.session.query(Author).order_by(Author.name).all())


def _author_choice() -> int | None:
    """The «linked author» select: an existing author id, or None for «no author»."""
    raw = request.form.get("author_id", "")
    return int(raw) if raw.isdigit() and db.session.get(Author, int(raw)) is not None else None


@bp.route("/users/<int:uid>", methods=["POST"])
@admin_required
def user_update(uid: int):
    user = db.session.get(User, uid) or abort(404)
    before = snapshot_model(user)
    action = request.form.get("action")
    if user.id == current_user.id and action in ("deactivate", "role"):
        flash("لا يمكنك تعطيل حسابك أو تغيير دورك بنفسك.", "error")
        return redirect(url_for("admin_core.users"))
    if action == "role" and request.form.get("role") in ROLES:
        user.role = request.form["role"]
    elif action == "author":
        user.author_id = _author_choice()
    elif action == "deactivate":
        user.is_active_flag = not user.is_active_flag
        user.session_version += 1
    elif action == "reset_2fa":
        user.totp_enabled, user.totp_secret, user.backup_codes = False, None, []
        user.session_version += 1
    elif action == "reset_password":
        temp = secrets.token_urlsafe(12)
        user.set_password(temp)
        user.session_version += 1
        flash(f"كلمة المرور المؤقتة (تظهر مرة واحدة): {temp}", "ok")
    audit(action or "update", "user", user.id, before=before, after=snapshot_model(user))
    db.session.commit()
    return redirect(url_for("admin_core.users"))


# ───────── audit log ─────────

@bp.route("/audit")
@admin_required
def audit_log():
    q = db.session.query(AuditLog).order_by(AuditLog.id.desc())
    if request.args.get("entity"):
        q = q.filter(AuditLog.entity_type == request.args["entity"])
    page_no = max(request.args.get("page", 1, type=int) or 1, 1)
    rows = q.offset((page_no - 1) * 50).limit(50).all()
    return render_template("admin/audit.html", rows=rows, page_no=page_no)


@bp.route("/audit/<int:log_id>")
@admin_required
def audit_detail(log_id: int):
    row = db.session.get(AuditLog, log_id) or abort(404)
    return render_template("admin/audit_detail.html", row=row,
                           before=json.dumps(row.before, ensure_ascii=False, indent=2),
                           after=json.dumps(row.after, ensure_ascii=False, indent=2))


# ───────── backups ─────────

@bp.route("/backups", methods=["GET", "POST"])
@admin_required
def backups():
    status_file = Path(current_app.config["BACKUP_STATUS_FILE"])
    if request.method == "POST":
        # The app container can't run Docker; the host cron picks this trigger up within a minute.
        (status_file.parent / "backup-requested").write_text(utcnow().isoformat(), encoding="utf-8")
        audit("backup_requested", "backup", None)
        db.session.commit()
        flash("طُلبت نسخة احتياطية؛ تبدأ خلال دقيقة. حدّث الصفحة بعد دقائق لرؤية النتيجة.", "ok")
        return redirect(url_for("admin_core.backups"))
    status = {}
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except ValueError:
            status = {"error": "ملف الحالة غير مقروء"}
    return render_template("admin/backups.html", status=status, now=utcnow())
