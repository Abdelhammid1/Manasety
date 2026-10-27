"""Key/value site settings with defaults. Locked keys are editable by Admin only."""
from __future__ import annotations

from typing import Any

from flask import g

from .extensions import db
from .models import Setting

# Values a non-Admin may never change: they must match what was filed with
# Apple, Google, D&B and PayTabs.
LOCKED_KEYS = {"legal_name_ar", "legal_name_en", "commercial_registration", "address_ar", "address_en"}

DEFAULTS: dict[str, Any] = {
    "brand_name_ar": "منصتي",
    "brand_name_en": "Manasety",
    "legal_name_ar": "شلبي إنتليجنس للبرمجيات وحلول الذكاء الاصطناعي (ذ.م.م)",
    "legal_name_en": "Shalaby Intelligence Software and AI Solutions LLC",
    "commercial_registration": "105300600301610",
    "address_ar": "11 شارع مسجد الرضوان، مدينة قويسنا، محافظة المنوفية، جمهورية مصر العربية",
    "address_en": "11 Masjid Al-Radwan St., Quweisna City, Monufia Governorate, Arab Republic of Egypt",
    "footer_brand": "منصتي - سكول",
    "footer_about": "نظام سحابي ذكي وشامل لإدارة العمليات التعليمية والإدارية والمالية بدقة وأمان.",
    "footer_note": "نخدم مؤسسات تعليمية سعودية ومصرية عن بُعد",
    "footer_social_text": "تابع أحدث تحديثات التكنولوجيا التعليمية والذكاء الاصطناعي عبر حساباتنا:",
    "social_handle": "@manasetyai",
    "footer_tagline": "منظومة منصتي المتكاملة لحلول التعليم المدرسي والذكاء الاصطناعي",
    "email": "hello@manasety.ai",
    "whatsapp_eg": "201044203322",
    "whatsapp_eg_display": "+20 10 44 20 33 22",
    "whatsapp_sa": "966561197859",
    "whatsapp_sa_display": "+966 56 11 978 59",
    "whatsapp_prefill": "السلام عليكم 👋 جاي من موقع منصتي، محتاج استشارة مجانية",
    "social": [
        {"name": "Instagram", "url": "https://instagram.com/manasetyai"},
        {"name": "TikTok", "url": "https://tiktok.com/@manasetyai"},
        {"name": "Facebook", "url": "https://facebook.com/manasetyai"},
    ],
    "nav": [
        {"label": "حل المدارس", "href": "/#solution"},
        {"label": "المميزات", "href": "/#features"},
        {"label": "الذكاء الاصطناعي", "href": "/#ai"},
        {"label": "قصص النجاح", "href": "/#success"},
        {"label": "أنظمتنا الأخرى", "href": "/#portfolio"},
        {"label": "المقالات", "href": "/blog"},
    ],
    "nav_cta_label": "احجز عرضًا",
    "nav_cta_href": "/#contact",
    "footer_links": [
        {"label": "سياسة الخصوصية", "href": "/privacy.html"},
        {"label": "الشروط والأحكام", "href": "/terms.html"},
        {"label": "سياسة الاسترجاع", "href": "/refund.html"},
    ],
    "thank_you_title": "تم استلام طلبكم بنجاح!",
    "thank_you_text": "شكرًا لاهتمامكم. سيتواصل معكم فريق منصتي عبر الواتساب أو الهاتف لتحديد موعد العرض التوضيحي.",
    "robots_extra": "",
    "english_enabled": False,
    "show_whatsapp_sa": True,
    "show_whatsapp_eg": True,
    "show_phone_line": True,
    "show_footer_social": False,
    "show_footer_note": False,
    "show_footer_copyright": False,
    "show_social_float": True,
    "show_domain_switch": False,
    "whatsapp_prefill_biz": "السلام عليكم 👋 جاي من موقع منصتي، عايز أعرف أكتر عن الأنظمة الإدارية المخصصة لشركتي",
    "nav_biz": [
        {"label": "خدماتنا", "href": "#services"},
        {"label": "من الفكرة إلى الإطلاق", "href": "#process"},
        {"label": "أنظمتنا", "href": "#portfolio"},
        {"label": "المقالات", "href": "/blog"},
    ],
    "nav_cta_label_biz": "احجز استشارة",
    "nav_cta_href_biz": "#contact",
    "footer_about_biz": "أنظمة ومنصات تشغيل مخصصة للشركات: إدارة ومتابعة وتقارير وصلاحيات، مبنية حسب نشاطك.",
    "footer_tagline_biz": "منصتي: حلول برمجية وأنظمة إدارية مخصصة للشركات.",
    "whatsapp_bubble": "مرحباً.. هل تريد معرفة المزيد عن الباقات والأسعار؟",
    "cookie_banner_text": "نستخدم ملفات تعريف الارتباط لتحليل الزيارات وتحسين الموقع.",
    "default_og_image": "/static/img/og-image.png",
    "blog_title": "مقالات منصتي",
    "blog_description": "مقالات عملية عن إدارة المدارس والتقييم والتعلم الإلكتروني والذكاء الاصطناعي في التعليم.",
    "product_page_url": "/",
    "internal_links_min_related": 2,
}


def get_setting(key: str, default: Any = None) -> Any:
    cache = g.setdefault("_settings_cache", {})
    if key not in cache:
        row = db.session.get(Setting, key)
        cache[key] = row.value if row is not None else DEFAULTS.get(key, default)
    return cache[key]


def set_setting(key: str, value: Any) -> None:
    row = db.session.get(Setting, key)
    if row is None:
        db.session.add(Setting(key=key, value=value))
    else:
        row.value = value
    g.setdefault("_settings_cache", {})[key] = value


def all_settings() -> dict[str, Any]:
    data = dict(DEFAULTS)
    for row in db.session.query(Setting).all():
        data[row.key] = row.value
    return data
