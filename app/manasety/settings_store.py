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
    "address_ar": "11 شارع مسجد الرضوان - قويسنا - المنوفية",
    "address_en": "11 Radwan Mosque Street - Quesna - Monufia",
    "footer_brand": "منصتي - نظام إدارة المدارس",
    "footer_about": "نظام سحابي ذكي وشامل لإدارة العمليات التعليمية والإدارية والمالية بدقة وأمان.",
    "footer_note": "",
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
    "schema_same_as": "https://www.linkedin.com/company/manasetyai/\nhttps://www.facebook.com/manasetyai\nhttps://www.instagram.com/manasetyai\nhttps://www.tiktok.com/@manasetyai\nhttps://www.snapchat.com/@manasetyai\nhttps://x.com/manasetyai\nhttps://www.youtube.com/@manasetyai\nhttps://www.crunchbase.com/organization/manasety-%D9%85%D9%86%D8%B5%D8%AA%D9%8A\nhttps://maps.app.goo.gl/AMxjeWMMwRQCFrr57",
    "schema_phone": "+201044203322",
    "schema_contact_type": "customer service",
    "schema_logo": "/static/img/logo.svg",
    "org_description_ar": "شركة برمجيات وحلول ذكاء اصطناعي، متخصصة في أنظمة إدارة المدارس والمنصات التعليمية، بالإضافة إلى بناء أنظمة مخصصة للشركات وأتمتة العمليات.",
    "org_description_en": "Manasety is a software and AI solutions company specializing in school management systems and e-learning platforms, plus custom business systems and process automation.",
    "english_enabled": False,
    "show_whatsapp_sa": True,
    "show_whatsapp_eg": True,
    "show_phone_line": True,
    "show_footer_social": False,
    "show_footer_note": False,
    "show_footer_copyright": False,
    "show_social_float": True,
    "show_domain_switch": False,
    "blog_title_biz": "مقالات منصتي للأعمال",
    "blog_description_biz": "مقالات عملية عن الأنظمة الإدارية المخصصة وأتمتة العمليات وإدارة الفروع والتقارير.",
    "default_og_image_biz": "/media/og-business.jpg",
    "product_page_url_biz": "/business",
    "whatsapp_prefill_biz": "السلام عليكم 👋 جاي من موقع منصتي، عايز أعرف أكتر عن الأنظمة الإدارية المخصصة لشركتي",
    "nav_biz": [
        {"label": "خدماتنا", "href": "#services"},
        {"label": "من الفكرة إلى الإطلاق", "href": "#process"},
        {"label": "أنظمتنا", "href": "#portfolio"},
        {"label": "المقالات", "href": "/blog"},
    ],
    "nav_cta_label_biz": "احجز استشارة",
    "whatsapp_prefill_institutes": "السلام عليكم 👋 جاي من موقع منصتي، عايز أعرف أكتر عن منصة إدارة المعاهد ومراكز التدريب وأطلب عرضًا تجريبيًا",
    "nav_institutes": [
        {"label": "ما يغطيه النظام", "href": "#features"},
        {"label": "الذكاء الاصطناعي", "href": "#ai"},
        {"label": "دراسة حالة", "href": "#case"},
        {"label": "كيف نبدأ", "href": "#process"},
        {"label": "الأسئلة الشائعة", "href": "#faq"},
        {"label": "المقالات", "href": "/blog"},
    ],
    "nav_cta_label_institutes": "اطلب عرضًا",
    "nav_cta_href_institutes": "#contact",
    "business_pages": "marsoud\nelmouhamy\nactivefit",
    "nav_biz_pages": [
        {"label": "خدماتنا", "href": "/business#services"},
        {"label": "من الفكرة إلى الإطلاق", "href": "/business#process"},
        {"label": "أنظمتنا", "href": "/business#portfolio"},
        {"label": "المقالات", "href": "/business/blog"},
    ],
    "page_layout": {},
    "extra_pages": [
        {"label": "للمعاهد والمراكز", "href": "/training-institutes"},
    ],
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
    # English version: read instead of the Arabic setting of the same name on /en/ pages (see i18n.py).
    "footer_brand_en": "Manasety - School Management System",
    "footer_about_en": "A smart, comprehensive cloud system for managing educational, administrative and financial operations with accuracy and security.",
    "footer_note_en": "",
    "footer_social_text_en": "Follow the latest in education technology and AI on our accounts:",
    "footer_tagline_en": "The integrated Manasety system for school education and AI solutions",
    "whatsapp_prefill_en": "Hello 👋 I came from the Manasety website and would like a free consultation",
    "nav_en": [
        {"label": "School solution", "href": "/#solution"},
        {"label": "Features", "href": "/#features"},
        {"label": "AI", "href": "/#ai"},
        {"label": "Success stories", "href": "/#success"},
        {"label": "Our other systems", "href": "/#portfolio"},
    ],
    "nav_cta_label_en": "Book a demo",
    "footer_links_en": [
        {"label": "Privacy Policy", "href": "/privacy.html"},
        {"label": "Terms and Conditions", "href": "/terms.html"},
        {"label": "Refund Policy", "href": "/refund.html"},
    ],
    "thank_you_title_en": "Your request was received successfully!",
    "thank_you_text_en": "Thank you for your interest. The Manasety team will contact you by WhatsApp or phone to schedule the demo.",
    "blog_title_en": "Manasety articles",
    "blog_description_en": "Practical articles on school management, assessment, e-learning and AI in education.",
    "blog_title_biz_en": "Manasety Business articles",
    "blog_description_biz_en": "Practical articles on custom management systems, process automation, branch management and reporting.",
    "whatsapp_prefill_biz_en": "Hello 👋 I came from the Manasety website and would like to know more about custom management systems for my company",
    "nav_biz_en": [
        {"label": "Our services", "href": "#services"},
        {"label": "From idea to launch", "href": "#process"},
        {"label": "Our systems", "href": "#portfolio"},
    ],
    "nav_cta_label_biz_en": "Book a consultation",
    "footer_about_biz_en": "Custom operating systems and platforms for companies: management, tracking, reports and permissions, built around your business.",
    "footer_tagline_biz_en": "Manasety: software solutions and custom management systems for companies.",
    "whatsapp_bubble_en": "Hello! Would you like to know more about our plans and pricing?",
    "cookie_banner_text_en": "We use cookies to analyze traffic and improve the site.",
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
