"""Dashboard (/admin). Arabic RTL. Every page requires login; Admin/Editor also require TOTP 2FA."""
from __future__ import annotations

from flask import Flask, redirect, request, session, url_for
from flask_login import current_user

# (group label, [(endpoint, label, permission)])
NAV = [
    ("المحتوى", [
        ("admin_content.page_builder", "منشئ الصفحة", "content"),
        ("admin_crud.index:features", "مكتبة المميزات", "features"),
        ("admin_crud.index:clients", "العملاء والشركاء", "clients"),
        ("admin_crud.index:case_studies", "دراسات الحالة", "case_studies"),
        ("admin_crud.index:facts", "الأرقام والإحصاءات", "facts"),
        ("admin_crud.index:faq", "الأسئلة الشائعة", "faq"),
        ("admin_files.index", "الملفات المعروضة", "files"),
        ("admin_legal.index", "الصفحات القانونية", "legal"),
        ("admin_media.index", "مكتبة الوسائط", "media"),
    ]),
    ("النمو", [
        ("admin_articles.index", "المقالات", "articles"),
        ("admin_crud.index:categories", "التصنيفات", "articles"),
        ("admin_crud.index:tags", "الوسوم", "articles"),
        ("admin_crud.index:side_cards", "الإعلانات الجانبية", "articles"),
        ("admin_crud.index:authors", "الكُتّاب", "articles"),
        ("admin_seo.index", "الـ SEO والروابط", "seo"),
        ("admin_crud.index:redirects", "التحويلات 301", "seo"),
        ("admin_crud.index:backlinks", "الباك لينكس", "backlinks"),
        ("admin_crud.index:integrations", "التكاملات والسكربتات", "analytics"),
        ("admin_seo.search_console", "أرقام Search Console", "seo"),
    ]),
    ("المبيعات", [
        ("admin_leads.index", "الطلبات", "leads"),
    ]),
    ("الإدارة", [
        ("admin_core.settings", "الإعدادات", "__admin_only__"),
        ("admin_core.users", "المستخدمون", "__admin_only__"),
        ("admin_core.audit_log", "سجل النشاط", "__admin_only__"),
        ("admin_core.backups", "النسخ الاحتياطي", "__admin_only__"),
    ]),
]

OPEN_ENDPOINTS = {"admin_auth.login", "admin_auth.verify", "admin_auth.logout"}
SETUP_ENDPOINTS = OPEN_ENDPOINTS | {"admin_auth.setup_2fa"}


def register_admin(app: Flask) -> None:
    from . import articles, auth, content, core, crud, files, leads, legal, media, seo

    for mod in (auth, core, content, crud, media, files, legal, articles, leads, seo):
        app.register_blueprint(mod.bp)

    @app.before_request
    def admin_gate():
        if not request.path.startswith("/admin") or request.endpoint in OPEN_ENDPOINTS:
            return None
        if not current_user.is_authenticated:
            return redirect(url_for("admin_auth.login", next=request.full_path))
        # Admin/Editor without 2FA can reach nothing but the 2FA setup page.
        if current_user.requires_2fa and not current_user.totp_enabled:
            if request.endpoint not in SETUP_ENDPOINTS:
                return redirect(url_for("admin_auth.setup_2fa"))
            return None
        if current_user.totp_enabled and not session.get("2fa_ok"):
            return redirect(url_for("admin_auth.verify"))
        return None

    @app.context_processor
    def admin_nav():
        if not request.path.startswith("/admin") or not current_user.is_authenticated:
            return {}
        groups = []
        for label, items in NAV:
            visible = []
            for endpoint, item_label, perm in items:
                if not current_user.can(perm):
                    continue
                if ":" in endpoint:
                    ep, resource = endpoint.split(":")
                    href = url_for(ep, resource=resource)
                else:
                    href = url_for(endpoint)
                visible.append({"href": href, "label": item_label, "active": request.path.startswith(href) and href != "/admin/"})
            if visible:
                groups.append({"label": label, "items": visible})
        return {"admin_nav": groups}
