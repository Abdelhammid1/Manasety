"""Declarative CRUD for the simple libraries. Each resource lists its fields once; list, form,
validation and audit logging come from here. Domain rules (consent, source, "soon" dates,
no secrets in the integrations registry) are enforced in each resource's `validate`."""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Optional

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from flask_login import current_user

from ..extensions import db
from ..icons import ICONS
from ..models import (BACKLINK_CHANNELS, BACKLINK_STATUSES, FAQ_CATEGORIES, FEATURE_MODULES, FEATURE_STATUSES,
                      INTEGRATION_KINDS, INTEGRATION_PLACEMENTS, Article, Author, Backlink, CaseStudy, Category,
                      Client, Fact, FaqItem, Feature, Integration, Media, Redirect, Tag)
from ..security import audit, clean_rich, clean_text, snapshot_model
from ..services.seo import slugify

bp = Blueprint("admin_crud", __name__, url_prefix="/admin/lib")


def F(key: str, label: str, kind: str = "text", **extra: Any) -> dict:
    return {"key": key, "label": label, "kind": kind, **extra}


ICON_CHOICES = {k: k for k in ICONS}

# ───────── validators ─────────

_SECRET_RE = re.compile(
    r"(sk_live|sk_test|secret|api[_-]?key|access[_-]?token|bearer\s+[a-z0-9]|password|passwd|private[_-]?key|"
    r"X-Contact-Form-Token|[a-f0-9]{48,})", re.I)


def _features(obj: Feature) -> list[str]:
    return obj.validation_errors()


def _faq(obj: FaqItem) -> list[str]:
    return obj.validation_errors()


def _facts(obj: Fact) -> list[str]:
    errs = []
    if not re.fullmatch(r"[a-z0-9_\-]{2,60}", obj.key or ""):
        errs.append("المفتاح حروف لاتينية صغيرة وأرقام و _ فقط.")
    if obj.is_visible and not ((obj.source or "").strip() and obj.verified_at):
        errs.append("لا يمكن إظهار رقم بدون «المصدر» و«تاريخ التحقق».")
    return errs


def _clients(obj: Client) -> list[str]:
    if obj.consent and not (obj.consent_date and obj.consent_proof_id):
        return ["الموافقة تحتاج «تاريخ الموافقة» و«ملف الإثبات» (صورة رسالة واتساب مثلًا)."]
    return []


def _redirects(obj: Redirect) -> list[str]:
    errs = []
    if not obj.from_path.startswith("/") or obj.from_path.startswith(
            ("/admin", "/static", "/media", "/api", "/preview", "/blog", "/authors", "/en/")):
        errs.append("المسار القديم يبدأ بـ / ولا يكون من مسارات الموقع نفسه (/admin، /api، /blog…).")
    if obj.code not in (301, 302):
        errs.append("الكود 301 أو 302 فقط.")
    if not (obj.to_path.startswith("/") and not obj.to_path.startswith("//")) and not obj.to_path.startswith("https://"):
        errs.append("الرابط الجديد مسار داخلي (/…) أو رابط https.")
    if obj.from_path in ("/privacy.html", "/terms.html", "/refund.html", "/manasety-profile.pdf"):
        errs.append("هذا الرابط مرتبط بتسجيلات الشركة (PayTabs / Sector Bot) ولا يُحوَّل.")
    if obj.from_path == obj.to_path:
        errs.append("التحويل يشير لنفسه.")
    target = db.session.query(Redirect).filter_by(from_path=obj.to_path).first()
    if target is not None and target.id != obj.id:
        errs.append("الرابط الجديد نفسه محوَّل مرة أخرى (سلسلة تحويلات).")
    return errs


def _integrations(obj: Integration) -> list[str]:
    errs = []
    if obj.code and _SECRET_RE.search(obj.code):
        errs.append("يبدو أن الكود يحتوي مفتاحًا أو توكنًا سريًا. المفاتيح تُحفظ في متغيرات البيئة على السيرفر، "
                    "والسجل يحمل الاسم والحالة والمعرّف العام فقط.")
    if obj.code and obj.placement == "none":
        errs.append("كود بمكان «لا يُحقن» لن يظهر أبدًا؛ اختر head أو نهاية body.")
    return errs


def _slugged(obj: Any) -> list[str]:
    """Slug from the name, made unique (Arabic-only names all fall back to the same Latin slug)."""
    base = slugify(obj.slug or obj.name)
    slug, n = base, 2
    model = type(obj)
    while db.session.query(model).filter(model.slug == slug, model.id != (obj.id or 0)).first():
        slug, n = f"{base}-{n}", n + 1
    obj.slug = slug
    return []


# ───────── resources ─────────

def _client_choices() -> dict:
    return {"": "— بدون —", **{str(c.id): c.name for c in db.session.query(Client).order_by(Client.name).all()}}


def _article_choices() -> dict:
    return {str(a.id): a.title for a in db.session.query(Article).order_by(Article.title).all()}


def _publish_state(c: Client) -> str:
    return "ظاهر للزوار" if c.is_publishable else "مخفي (بلا موافقة مكتملة)"


RESOURCES: dict[str, dict[str, Any]] = {
    "features": {
        "model": Feature, "perm": "features", "label": "مكتبة المميزات", "singular": "ميزة",
        "order": (Feature.module, Feature.position, Feature.id), "filters": {"module": FEATURE_MODULES, "status": FEATURE_STATUSES},
        "columns": [("name", "الاسم"), ("module", "الموديول", lambda o: FEATURE_MODULES.get(o.module, o.module)),
                    ("status", "الحالة", lambda o: FEATURE_STATUSES.get(o.status, o.status))],
        "fields": [
            F("module", "الموديول", "select", choices=FEATURE_MODULES, required=True),
            F("name", "الاسم", required=True), F("description", "الوصف", "textarea"),
            F("icon", "الأيقونة", "select", choices=ICON_CHOICES),
            F("status", "الحالة", "select", choices=FEATURE_STATUSES,
              help="«قريبًا» تعرض الشارة تلقائيًا. «مخفية» لا تظهر في أي مكان."),
            F("release_date", "تاريخ الإطلاق", "date", help="لا يظهر إلا مع تفعيل «تاريخ مؤكد»."),
            F("release_date_confirmed", "تاريخ مؤكد كتابيًا", "bool"),
            F("claim_note", "مصدر الادعاء (UAT / الكود / غيره)", help="داخلي فقط، لا يظهر للزوار."),
            F("position", "الترتيب", "int"),
            F("name_en", "الاسم EN"), F("description_en", "الوصف EN", "textarea"),
        ],
        "validate": _features,
    },
    "clients": {
        "model": Client, "perm": "clients", "label": "العملاء وشركاء النجاح", "singular": "جهة",
        "order": (Client.position, Client.id), "filters": {"kind": {"client": "عميل", "partner": "شريك"}},
        "columns": [("name", "الاسم"), ("kind", "النوع", lambda o: "شريك" if o.kind == "partner" else "عميل"),
                    ("consent", "الحالة العامة", _publish_state)],
        "fields": [
            F("name", "الاسم", required=True), F("kind", "النوع", "select", choices={"client": "عميل", "partner": "شريك"}),
            F("sector", "القطاع"), F("description", "الوصف", "textarea"), F("url", "الرابط", "url"),
            F("logo_id", "الشعار", "media", media_kind="image"),
            F("consent", "موافقة كتابية على الظهور", "bool",
              help="بدون موافقة + تاريخ + ملف إثبات لا يظهر الاسم ولا الشعار في أي صفحة."),
            F("consent_date", "تاريخ الموافقة", "date"),
            F("consent_proof_id", "ملف إثبات الموافقة", "media", media_kind="any", private_hint=True),
            F("consent_notes", "ملاحظات الموافقة"),
            F("is_visible", "ظاهر", "bool"), F("position", "الترتيب", "int"),
            F("name_en", "الاسم EN"), F("description_en", "الوصف EN", "textarea"),
            F("show_name", "\u0625\u0638\u0647\u0627\u0631 \u0627\u0644\u0627\u0633\u0645 \u062a\u062d\u062a \u0627\u0644\u0644\u0648\u062c\u0648", "bool"),
        ],
        "validate": _clients,
    },
    "case_studies": {
        "model": CaseStudy, "perm": "case_studies", "label": "دراسات الحالة", "singular": "دراسة حالة",
        "order": (CaseStudy.position, CaseStudy.id),
        "columns": [("anonymous_label", "الاسم المعروض", lambda o: o.display_name()),
                    ("client_id", "العميل", lambda o: o.client.name if o.client else "—")],
        "fields": [
            F("client_id", "العميل (اسمه يظهر فقط بعد موافقته)", "select", choices=_client_choices, coerce="int"),
            F("anonymous_label", "الاسم قبل الموافقة", required=True, help="مثل: «مدرسة حقيقية للتعليم القرآني»."),
            F("challenge", "التحدي", "textarea"), F("built", "ما بنيناه", "textarea"), F("working_now", "ما يعمل الآن", "textarea",
              help="لأي رقم استخدم [[fact:key]] أو [[if:key]]…[[/if]] من جدول الأرقام."),
            F("url", "رابط المنصة (يظهر بعد الموافقة فقط)", "url"),
            F("is_visible", "ظاهر", "bool"), F("position", "الترتيب", "int"),
            F("anonymous_label_en", "الاسم قبل الموافقة EN"), F("challenge_en", "التحدي EN", "textarea"),
            F("built_en", "ما بنيناه EN", "textarea"), F("working_now_en", "ما يعمل الآن EN", "textarea"),
        ],
    },
    "facts": {
        "model": Fact, "perm": "facts", "label": "الأرقام والإحصاءات", "singular": "رقم",
        "order": (Fact.key,),
        "columns": [("key", "المفتاح"), ("value", "القيمة"),
                    ("source", "الحالة العامة", lambda o: "منشور" if o.is_publishable else "غير منشور")],
        "fields": [
            F("key", "المفتاح (يُستخدم كـ [[fact:key]])", required=True), F("label", "التسمية", required=True),
            F("value", "القيمة", required=True, help="مثل 2000+"), F("meaning", "ماذا يعدّ الرقم بالضبط", "textarea"),
            F("source", "المصدر", "textarea"), F("verified_at", "تاريخ التحقق", "date"),
            F("is_visible", "ظاهر", "bool", help="لا يُنشر رقم بدون مصدر وتاريخ تحقق."),
        ],
        "validate": _facts,
    },
    "faq": {
        "model": FaqItem, "perm": "faq", "label": "الأسئلة الشائعة", "singular": "سؤال",
        "order": (FaqItem.position, FaqItem.id), "filters": {"category": FAQ_CATEGORIES}, "sortable": True,
        "columns": [("question", "السؤال"), ("category", "التصنيف", lambda o: FAQ_CATEGORIES.get(o.category, o.category)),
                    ("is_visible", "ظاهر", lambda o: "نعم" if o.is_visible else "لا")],
        "fields": [
            F("question", "السؤال", required=True), F("answer_html", "الإجابة", "rich", required=True),
            F("category", "التصنيف", "select", choices=FAQ_CATEGORIES),
            F("source", "المصدر (مطلوب إن كانت الإجابة تحتوي رقمًا)"),
            F("is_visible", "ظاهر", "bool"), F("show_on_home", "في الصفحة الرئيسية", "bool"),
            F("show_on_faq_page", "في صفحة الأسئلة /faq", "bool"),
            F("article_ids", "داخل مقالات", "multiselect", choices=_article_choices),
            F("position", "الترتيب", "int"),
            F("question_en", "السؤال EN"), F("answer_html_en", "الإجابة EN", "rich"),
        ],
        "validate": _faq,
    },
    "categories": {
        "model": Category, "perm": "articles", "label": "تصنيفات المقالات (العناقيد)", "singular": "تصنيف",
        "order": (Category.name,), "columns": [("name", "الاسم"), ("slug", "الرابط"), ("landing_url", "صفحة الهبوط")],
        "fields": [F("name", "الاسم", required=True), F("slug", "الرابط (يُولَّد تلقائيًا)"),
                   F("description", "الوصف", "textarea"), F("landing_url", "صفحة الهبوط لهذا العنقود")],
        "validate": _slugged,
    },
    "tags": {
        "model": Tag, "perm": "articles", "label": "الوسوم", "singular": "وسم", "order": (Tag.name,),
        "columns": [("name", "الاسم"), ("slug", "الرابط")],
        "fields": [F("name", "الاسم", required=True), F("slug", "الرابط (يُولَّد تلقائيًا)")],
        "validate": _slugged,
    },
    "authors": {
        "model": Author, "perm": "articles", "label": "الكُتّاب", "singular": "كاتب", "order": (Author.name,),
        "columns": [("name", "الاسم"), ("job_title", "الصفة")],
        "fields": [F("name", "الاسم", required=True), F("slug", "الرابط (يُولَّد تلقائيًا)"), F("job_title", "الصفة"),
                   F("bio", "نبذة", "rich"), F("photo_id", "الصورة", "media", media_kind="image"),
                   F("same_as", "روابط الحسابات (سطر لكل رابط)", "lines")],
        "validate": _slugged,
    },
    "redirects": {
        "model": Redirect, "perm": "seo", "label": "التحويلات 301", "singular": "تحويل", "order": (Redirect.from_path,),
        "columns": [("from_path", "من"), ("to_path", "إلى"), ("code", "الكود"), ("hits", "مرات الاستخدام")],
        "fields": [F("from_path", "المسار القديم", required=True, ltr=True), F("to_path", "الرابط الجديد", required=True, ltr=True),
                   F("code", "الكود", "select", choices={"301": "301 دائم", "302": "302 مؤقت"}, coerce="int"),
                   F("note", "ملاحظة")],
        "validate": _redirects,
    },
    "backlinks": {
        "model": Backlink, "perm": "backlinks", "label": "متتبع الباك لينكس", "singular": "رابط",
        "order": (Backlink.id.desc(),), "filters": {"channel": BACKLINK_CHANNELS, "status": BACKLINK_STATUSES},
        "columns": [("source_url", "الصفحة المصدر"), ("target_url", "الهدف عندنا"),
                    ("channel", "القناة", lambda o: BACKLINK_CHANNELS.get(o.channel, o.channel)),
                    ("status", "الحالة", lambda o: BACKLINK_STATUSES.get(o.status, o.status)),
                    ("last_check_result", "آخر فحص")],
        "fields": [
            F("source_url", "الصفحة المصدر", "url", required=True, ltr=True), F("target_url", "الصفحة الهدف عندنا", "url", required=True, ltr=True),
            F("anchor_text", "نص الرابط (Anchor)", help="الأفضل اسم العلامة أو الرابط نفسه، لا كلمات مفتاحية مكررة."),
            F("rel", "النوع", "select", choices={"dofollow": "dofollow", "nofollow": "nofollow"}),
            F("channel", "القناة", "select", choices=BACKLINK_CHANNELS), F("status", "الحالة", "select", choices=BACKLINK_STATUSES),
            F("acquired_at", "تاريخ الحصول", "date"), F("owner", "المسؤول"),
            F("written_request_kept", "الطلب المكتوب محفوظ", "bool"), F("notes", "ملاحظات", "textarea"),
        ],
        "row_actions": [("admin_seo.check_backlink", "فحص الآن")],
    },
    "integrations": {
        "model": Integration, "perm": "analytics", "label": "سجل التكاملات والسكربتات", "singular": "تكامل",
        "order": (Integration.position, Integration.id), "delete_perm": "__admin_only__", "delete_type_name": True,
        "columns": [("name", "الاسم"), ("kind", "النوع", lambda o: INTEGRATION_KINDS.get(o.kind, o.kind)),
                    ("placement", "المكان", lambda o: INTEGRATION_PLACEMENTS.get(o.placement, o.placement)),
                    ("is_active", "الحالة", lambda o: "مفعّل" if o.is_active else "متوقف"),
                    ("last_verified_at", "آخر تحقق")],
        "fields": [
            F("name", "الاسم", required=True), F("kind", "النوع", "select", choices=INTEGRATION_KINDS),
            F("placement", "المكان", "select", choices=INTEGRATION_PLACEMENTS),
            F("page_scope", "الصفحات (* = كل الصفحات، أو مسارات مفصولة بفاصلة)", ltr=True),
            F("identifier", "المعرّف العام (مثل G-… أو رقم الـ Pixel)", ltr=True),
            F("code", "الكود (يُحقن كما هو — بدون مفاتيح سرية)", "code", admin_only=True,
              help="يعدّله Admin فقط: الكود يعمل في كل الصفحات بصلاحيات الموقع."),
            F("is_active", "مفعّل", "bool"),
            F("requires_consent", "لا يعمل إلا بعد موافقة الكوكيز", "bool",
              help="تفعيلها على Analytics/Pixel يقلل البيانات المسجلة؛ القرار تسويقي/قانوني."),
            F("position", "ترتيب الحقن", "int"), F("owner", "المسؤول"), F("last_verified_at", "تاريخ آخر تحقق", "date"),
            F("notes", "ملاحظات (ما يعتمد عليه: إعلانات، تقارير…)", "textarea"),
        ],
        "validate": _integrations,
    },
}


def _resource(name: str) -> dict:
    res = RESOURCES.get(name) or abort(404)
    if not current_user.can(res["perm"]):
        abort(403)
    return res


def _choices(field: dict) -> dict:
    ch: Any = field.get("choices") or {}
    if callable(ch):
        ch = ch()
    return dict(ch)


def _parse(field: dict, form: Any) -> Any:
    key, kind = field["key"], field["kind"]
    raw = form.get(key, "")
    if kind == "bool":
        return form.get(key) == "on"
    if kind == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
    if kind == "date":
        try:
            return date.fromisoformat(raw) if raw else None
        except ValueError:
            return None
    if kind == "media":
        return int(raw) if str(raw).isdigit() else None
    if kind == "rich":
        return clean_rich(raw)
    if kind == "code":
        return (raw or "").strip()  # injected verbatim by design; editors are trusted, secrets are blocked
    if kind == "lines":
        return [clean_text(x) for x in (raw or "").splitlines() if clean_text(x)]
    if kind == "multiselect":
        return [int(x) for x in form.getlist(key) if str(x).isdigit()]
    if kind == "select":
        if field.get("coerce") == "int":
            return int(raw) if str(raw).isdigit() and str(raw) in _choices(field) else None
        return raw if raw in _choices(field) else (next(iter(_choices(field)), "") if field.get("required") else "")
    value = clean_text(raw)
    if kind == "url" and value and not value.startswith(("https://", "http://", "/")):
        return ""
    return value


@bp.app_template_filter("display_cell")
def display_cell(obj: Any, column: tuple[Any, ...]) -> Any:
    attr, *rest = column
    render = rest[1] if len(rest) > 1 else None
    return render(obj) if callable(render) else getattr(obj, attr)


@bp.route("/<resource>")
def index(resource: str):
    res = _resource(resource)
    model = res["model"]
    q = db.session.query(model)
    active_filters = {}
    for key, choices in (res.get("filters") or {}).items():
        val = request.args.get(key)
        if val in choices:
            q = q.filter(getattr(model, key) == val)
            active_filters[key] = val
    rows = q.order_by(*res["order"]).all()
    return render_template("admin/crud_list.html", res=res, resource=resource, rows=rows, active_filters=active_filters)


@bp.route("/<resource>/new", methods=["GET", "POST"])
@bp.route("/<resource>/<int:oid>", methods=["GET", "POST"])
def edit(resource: str, oid: Optional[int] = None):
    res = _resource(resource)
    model = res["model"]
    obj = db.session.get(model, oid) if oid else model()
    if obj is None:
        abort(404)
    errors: list[str] = []
    if request.method == "POST":
        with db.session.no_autoflush:  # validators query the DB; never flush half-edited rows
            before = snapshot_model(obj) if oid else None
            for field in res["fields"]:
                if field.get("admin_only") and not current_user.can("__admin_only__"):
                    continue  # injected code runs with the site's privileges: Admin only
                setattr(obj, field["key"], _parse(field, request.form))
            for field in res["fields"]:
                if field.get("required") and getattr(obj, field["key"]) in (None, "", []):
                    errors.append(f"«{field['label']}» مطلوب.")
            validate: Optional[Callable] = res.get("validate")
            if validate:
                errors += validate(obj)
        if not errors:
            if not oid:
                db.session.add(obj)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                errors.append("قيمة مكررة: يوجد عنصر آخر بنفس الاسم أو الرابط أو المفتاح.")
                media = db.session.query(Media).order_by(Media.id.desc()).limit(300).all()
                return render_template("admin/crud_form.html", res=res, resource=resource, obj=obj, oid=oid,
                                       errors=errors, media=media, choices=_choices)
            audit("update" if oid else "create", resource, obj.id, before=before, after=snapshot_model(obj))
            db.session.commit()
            flash("تم الحفظ.", "ok")
            return redirect(url_for("admin_crud.index", resource=resource))
        # On errors the typed values stay on screen; the request-scoped session is rolled back at teardown.
    media = db.session.query(Media).order_by(Media.id.desc()).limit(300).all()
    return render_template("admin/crud_form.html", res=res, resource=resource, obj=obj, oid=oid, errors=errors,
                           media=media, choices=_choices)


@bp.route("/<resource>/<int:oid>/delete", methods=["POST"])
def delete(resource: str, oid: int):
    res = _resource(resource)
    if res.get("delete_perm") and not current_user.can(res["delete_perm"]):
        abort(403)
    obj = db.session.get(res["model"], oid)
    if obj is None:
        abort(404)
    if res.get("delete_type_name") and (request.form.get("confirm_name") or "").strip() != obj.name:
        flash("للحذف اكتب اسم التكامل كما هو بالضبط.", "error")
        return redirect(url_for("admin_crud.edit", resource=resource, oid=oid))
    audit("delete", resource, oid, before=snapshot_model(obj))
    db.session.delete(obj)
    db.session.commit()
    flash("تم الحذف.", "ok")
    return redirect(url_for("admin_crud.index", resource=resource))


@bp.route("/<resource>/reorder", methods=["POST"])
def reorder(resource: str):
    res = _resource(resource)
    ids = [int(x) for x in (request.get_json(silent=True) or {}).get("order", []) if str(x).isdigit()]
    rows = {o.id: o for o in db.session.query(res["model"]).filter(res["model"].id.in_(ids)).all()}
    for pos, oid in enumerate(ids):
        if oid in rows:
            rows[oid].position = pos
    audit("reorder", resource, None, after=ids)
    db.session.commit()
    return {"ok": True}
