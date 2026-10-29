"""Block type registry.

Each page section is an instance of one block type. A block type declares its fields; the
dashboard builds its editing form from this schema, and `templates/public/blocks/<type>.html`
renders it. Adding a *new block type* is the only change that needs a developer (spec).

Field spec: (key, kind, label, extra)
  kind: text | textarea | rich | url | bool | select | media | list
  list fields carry their sub-fields in extra["fields"].
"""
from __future__ import annotations

from typing import Any

from .icons import ICONS
from .models import FAQ_CATEGORIES, FEATURE_MODULES
from .security import clean_rich, clean_text

F = dict  # readability alias

ICON_CHOICES = list(ICONS)
_ICON = F(key="icon", kind="select", label="الأيقونة", choices={i: i for i in ICON_CHOICES})

_HEAD = [
    F(key="eyebrow", kind="text", label="سطر علوي صغير"),
    F(key="title", kind="textarea", label="العنوان"),
    F(key="subtitle", kind="textarea", label="نص تحت العنوان"),
]
_CTA = [
    F(key="cta_label", kind="text", label="نص الزر"),
    F(key="cta_href", kind="url", label="رابط الزر"),
]

BLOCK_TYPES: dict[str, dict[str, Any]] = {
    "hero": {
        "label": "Hero (العنوان الرئيسي)",
        "fields": [
            F(key="badge", kind="text", label="الشارة فوق العنوان"),
            F(key="title", kind="textarea", label="العنوان (H1) — السطر الأول"),
            F(key="title_highlight", kind="textarea", label="العنوان — الجزء الملوّن"),
            F(key="subtitle", kind="textarea", label="النص التعريفي"),
            F(key="cta_primary_label", kind="text", label="الزر الأساسي"),
            F(key="cta_primary_href", kind="url", label="رابط الزر الأساسي"),
            F(key="cta_secondary_label", kind="text", label="الزر الثانوي"),
            F(key="cta_secondary_href", kind="url", label="رابط الزر الثانوي"),
            F(key="proof_line", kind="text", label="سطر الإثبات تحت الأزرار"),
            F(key="no_mock", kind="bool", label="بدون مثال توضيحي (للصفحات غير المدرسية)"),
            F(key="image", kind="media", label="صورة الـ Hero (بيانات تجريبية فقط)"),
            F(key="show_files", kind="bool", label="إظهار الملفات المخصصة للـ Hero"),
        ],
    },
    "cards": {
        "label": "بطاقات (المشكلة / الحل)",
        "fields": [
            *_HEAD,
            F(key="variant", kind="select", label="الشكل", choices={"chain": "سلسلة (انفوجرافيك)", "tiles": "بلاطات (انفوجرافيك)", "story": "قصة واحدة: فوضى ← منظومة", "chaos": "فوضى ← نظام (انفوجرافيك)", "problem": "مشكلة (أحمر)", "solution": "حل (أزرق)"}),
            F(key="items", kind="list", label="البطاقات", fields=[
                _ICON, F(key="title", kind="text", label="العنوان"), F(key="text", kind="textarea", label="النص")]),
            F(key="modules", kind="list", label="موديولات الحل", fields=[
                _ICON, F(key="title", kind="text", label="العنوان"), F(key="text", kind="textarea", label="النص")]),
        ],
    },
    "feature_tabs": {
        "label": "المميزات بالتفصيل (تبويبات من مكتبة المميزات)",
        "fields": [
            F(key="eyebrow", kind="text", label="سطر علوي"),
            F(key="title", kind="textarea", label="العنوان"),
            F(key="tabs", kind="list", label="التبويبات (الترتيب = ترتيب العرض)", fields=[
                F(key="module", kind="select", label="الموديول", choices=FEATURE_MODULES),
                F(key="label", kind="text", label="اسم التبويب"),
                F(key="intro", kind="textarea", label="جملة تعريفية"),
            ]),
            F(key="soon_module", kind="select", label="موديول بطاقة «قريبًا»", choices={"": "بدون", **FEATURE_MODULES}),
        ],
    },
    "customize": {
        "label": "على مقاس مدرستك (المنصة الأم والموديولات)",
        "fields": [
            F(key="eyebrow", kind="text", label="سطر علوي"),
            F(key="title", kind="textarea", label="العنوان"),
            F(key="core_label", kind="text", label="اسم المنصة الأم في الرسم"),
            F(key="ring", kind="list", label="الموديولات حول المنصة", fields=[
                F(key="label", kind="text", label="الاسم"), F(key="on", kind="bool", label="مُضاء في الرسم")]),
            F(key="points", kind="list", label="النقاط", fields=[
                _ICON, F(key="title", kind="text", label="العنوان"), F(key="text", kind="textarea", label="النص")]),
        ],
    },
    "ai": {
        "label": "الذكاء الاصطناعي",
        "fields": [
            *_HEAD,
            F(key="variant", kind="select", label="الشكل", choices={"": "كروت (الحالي)", "flow": "مسار بقرار بشري (انفوجرافيك)"}),
            F(key="tools_title", kind="text", label="الطبقة 1: العنوان"),
            F(key="tools_subtitle", kind="text", label="الطبقة 1: سطر تحت العنوان"),
            F(key="tools", kind="list", label="الطبقة 1: الأدوات", fields=[_ICON, F(key="text", kind="text", label="الأداة")]),
            F(key="rows_title", kind="text", label="الطبقة 2: العنوان"),
            F(key="rows_subtitle", kind="text", label="الطبقة 2: سطر تحت العنوان"),
            F(key="rows", kind="list", label="الطبقة 2: النقاط", fields=[
                _ICON, F(key="title", kind="text", label="العنوان"), F(key="text", kind="text", label="الوصف")]),
            F(key="cost_title", kind="text", label="شريط التحكم: العنوان"),
            F(key="cost_text", kind="textarea", label="شريط التحكم: النص"),
            F(key="cost_badge", kind="text", label="شريط التحكم: الشارة"),
            F(key="transparency", kind="textarea", label="سطر الشفافية (فارغ = مخفي)"),
        ],
    },
    "split": {
        "label": "نص ونقاط (خبرة الاختبارات / عام)",
        "fields": [
            F(key="eyebrow", kind="text", label="سطر علوي"),
            F(key="title", kind="textarea", label="العنوان"),
            F(key="variant", kind="select", label="الشكل", choices={"": "عادي (الحالي)", "timeline": "خط زمني (انفوجرافيك)"}),
            F(key="body", kind="textarea", label="النص"),
            F(key="points", kind="list", label="النقاط", fields=[
                F(key="title", kind="text", label="العنوان"), F(key="text", kind="textarea", label="النص")]),
        ],
    },
    "case_studies": {
        "label": "دراسات الحالة (من جدول دراسات الحالة)",
        "fields": [
            F(key="eyebrow", kind="text", label="سطر علوي"),
            F(key="title", kind="textarea", label="العنوان"),
            F(key="label_challenge", kind="text", label="عنوان «التحدي»"),
            F(key="label_built", kind="text", label="عنوان «ما بنيناه»"),
            F(key="label_now", kind="text", label="عنوان «ما يعمل الآن»"),
            F(key="case_ids", kind="textarea", label="أرقام دراسات حالة محددة (رقم لكل سطر) — فارغ = كل الدراسات"),
            F(key="show_files", kind="bool", label="إظهار الملفات المخصصة لهذا القسم"),
        ],
    },
    "logos": {
        "label": "شركاء النجاح (من جدول العملاء، بالموافقة فقط)",
        "fields": [
            F(key="title", kind="textarea", label="العنوان"),
            F(key="partner_label", kind="text", label="وسم الشريك"),
        ],
    },
    "systems": {
        "label": "أنظمتنا الأخرى / خبرتنا في الإدارة",
        "fields": [
            *_HEAD,
            F(key="variant", kind="select", label="الشكل", choices={"": "كروت (الحالي)", "gallery": "معرض أنظمة (انفوجرافيك)", "roundcards": "بطاقات بشعار دائري", "classic": "كلاسيك (صفوف)", "windows": "نوافذ أنظمة (انفوجرافيك)", "panels": "لوحات جانبية (انفوجرافيك)", "showcase": "عرض مميز (انفوجرافيك)"}),
            F(key="items", kind="list", label="الأنظمة", fields=[
                _ICON, F(key="logo", kind="media", label="الشعار (يحل محل الأيقونة)"), F(key="name", kind="text", label="الاسم"), F(key="text", kind="textarea", label="الوصف"),
                F(key="tag", kind="text", label="الوسم السفلي"),
                F(key="url", kind="url", label="الرابط (اتركه فارغًا إن لم يُتحقق منه)")]),
        ],
    },
    "services": {
        "label": "عندك نشاط آخر؟ (الخدمات المخصصة)",
        "fields": [
            *_HEAD,
            F(key="items", kind="list", label="الخدمات", fields=[_ICON, F(key="title", kind="text", label="الخدمة")]),
            F(key="side_title", kind="text", label="البطاقة الجانبية: العنوان"),
            F(key="side_text", kind="textarea", label="البطاقة الجانبية: النص"),
            *_CTA,
        ],
    },
    "faq": {
        "label": "الأسئلة الشائعة (من مدير الأسئلة)",
        "fields": [
            *_HEAD,
            F(key="category", kind="select", label="تصنيف محدد (اختياري)", choices={"": "كل أسئلة الرئيسية", **FAQ_CATEGORIES}),
            F(key="more_label", kind="text", label="نص رابط كل الأسئلة (فارغ = مخفي)"),
        ],
    },
    "cta_form": {
        "label": "نموذج حجز العرض التوضيحي",
        "fields": [
            *_HEAD,
            F(key="stage_label", kind="text", label="عنوان حقل المرحلة/العدد (فارغ = الافتراضي)"),
            F(key="school_label", kind="text", label="عنوان حقل المدرسة/المؤسسة (فارغ = الافتراضي)"),
            F(key="stage_ph", kind="text", label="نص أول خيار في قائمة المرحلة/العدد"),
            F(key="stages", kind="textarea", label="خيارات المرحلة (سطر لكل خيار)"),
            F(key="business_types", kind="textarea", label="خيارات نوع النشاط (سطر لكل خيار)"),
            F(key="name_placeholder", kind="text", label="مثال حقل الاسم"),
            F(key="school_placeholder", kind="text", label="مثال حقل المدرسة"),
            F(key="phone_placeholder", kind="text", label="مثال حقل الهاتف"),
            F(key="notes_placeholder", kind="text", label="مثال حقل الملاحظات"),
            F(key="submit_label", kind="text", label="نص زر الإرسال"),
            F(key="note", kind="text", label="ملاحظة تحت الزر"),
        ],
    },
    "featured_article": {
        "label": "مقال مميز / أحدث المقالات",
        "fields": [
            F(key="eyebrow", kind="text", label="سطر علوي"),
            F(key="title", kind="textarea", label="العنوان"),
            F(key="article_slugs", kind="textarea", label="روابط مقالات محددة (slug لكل سطر) — فارغ = الأحدث"),
            F(key="count", kind="select", label="العدد", choices={"3": "3", "2": "2", "1": "1", "4": "4", "6": "6"}),
            F(key="more_label", kind="text", label="نص رابط المدونة"),
        ],
    },
    "stats": {
        "label": "أرقام (من جدول الأرقام الموثقة فقط)",
        "fields": [
            F(key="title", kind="textarea", label="العنوان"),
            F(key="fact_keys", kind="textarea", label="مفاتيح الأرقام (مفتاح لكل سطر)"),
        ],
    },
    "rich_text": {
        "label": "نص حر",
        "fields": [
            F(key="title", kind="textarea", label="العنوان"),
            F(key="body", kind="rich", label="النص"),
        ],
    },
}


def field_specs(block_type: str) -> list[dict]:
    return BLOCK_TYPES[block_type]["fields"]


def parse_block_form(block_type: str, form: Any, lang: str) -> dict:
    """Rebuild a block's content dict for one language from flat form names:
    `<lang>__<key>` and, for lists, `<lang>__<key>__<index>__<sub>`."""
    out: dict[str, Any] = {}
    for spec in field_specs(block_type):
        name = f"{lang}__{spec['key']}"
        if spec["kind"] == "list":
            rows: dict[int, dict] = {}
            prefix = name + "__"
            for k in form.keys():
                if not k.startswith(prefix):
                    continue
                parts = k[len(prefix):].split("__", 1)
                if len(parts) != 2 or not parts[0].isdigit():
                    continue
                rows.setdefault(int(parts[0]), {})
            items = []
            for idx in sorted(rows):
                row = {sub["key"]: _clean_value(sub, form, f"{prefix}{idx}__{sub['key']}") for sub in spec["fields"]}
                if any(v not in ("", False, None) for v in row.values()):
                    items.append(row)
            out[spec["key"]] = items
        else:
            out[spec["key"]] = _clean_value(spec, form, name)
    return out


def _clean_value(spec: dict, form: Any, name: str) -> Any:
    kind = spec["kind"]
    if kind == "bool":
        return form.get(name) in ("on", "1", "true", "y")
    raw = form.get(name, "") or ""
    if kind == "rich":
        return clean_rich(raw)
    if kind == "media":
        return int(raw) if str(raw).isdigit() else None
    if kind == "select":
        choices = spec.get("choices") or {}
        return raw if raw in choices else ""
    if kind == "url":
        raw = clean_text(raw)
        if raw and not raw.startswith(("/", "#", "https://", "http://", "mailto:", "tel:")):
            return ""
        return raw
    return clean_text(raw)
