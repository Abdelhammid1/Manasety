"""Database schema.

Principle from the spec: every visitor-facing string is a DB field, and every number or
client name carries a source / verification date / consent before it can be published.
The `is_publishable` properties are the single place those rules live; public queries go
through `manasety.publishing` which only ever uses them.
"""
from __future__ import annotations

import re
import secrets
from datetime import date, datetime, timezone
from typing import Any, Optional

from flask_login import UserMixin
from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Table, Column, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import Model, db


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ───────────────────────── Users, roles, audit ─────────────────────────

ROLES = {
    "admin": "مدير النظام (Admin)",
    "editor": "محرر (Editor)",
    "marketer": "تسويق (Marketer)",
    "sales": "مبيعات (Sales)",
}

# What each role may touch. Admin implicitly has everything.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "editor": {"content", "features", "clients", "facts", "case_studies", "media", "faq", "files", "legal"},
    "marketer": {"articles", "seo", "backlinks", "analytics", "media"},
    "sales": {"leads"},
}

ROLES_REQUIRING_2FA = {"admin", "editor"}


class User(UserMixin, Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="editor")
    totp_secret: Mapped[Optional[str]] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    backup_codes: Mapped[list] = mapped_column(JSON, default=list)  # hashed
    is_active_flag: Mapped[bool] = mapped_column("is_active", Boolean, default=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # The byline this person writes under: new articles they create start with this author selected.
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("authors.id", ondelete="SET NULL"))

    author = relationship("Author")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self.is_active_flag

    def get_id(self) -> str:
        # Bumping session_version logs the user out everywhere (password change, 2FA reset).
        return f"{self.id}:{self.session_version}"

    @property
    def requires_2fa(self) -> bool:
        return self.role in ROLES_REQUIRING_2FA

    def can(self, permission: str) -> bool:
        if self.role == "admin":
            return True
        return permission in ROLE_PERMISSIONS.get(self.role, set())

    def generate_backup_codes(self) -> list[str]:
        codes = [secrets.token_hex(4) for _ in range(8)]
        self.backup_codes = [generate_password_hash(c) for c in codes]
        return codes

    def use_backup_code(self, code: str) -> bool:
        code = code.strip().lower()
        for h in list(self.backup_codes or []):
            if check_password_hash(h, code):
                self.backup_codes = [x for x in self.backup_codes if x != h]
                return True
        return False


class AuditLog(Model):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    user_label: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[Optional[str]] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(String(500), default="")
    before: Mapped[Optional[Any]] = mapped_column(JSON)
    after: Mapped[Optional[Any]] = mapped_column(JSON)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user = relationship("User")


class Revision(Model):
    """Snapshot history for pages, legal pages and articles (restore = load snapshot)."""
    __tablename__ = "revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    snapshot: Mapped[Any] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    created_by = relationship("User")


# ───────────────────────── Media ─────────────────────────

class Media(Model):
    __tablename__ = "media"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))  # image | pdf | video
    size: Mapped[int] = mapped_column(Integer)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    alt: Mapped[str] = mapped_column(String(500), default="")
    alt_en: Mapped[str] = mapped_column(String(500), default="")
    is_demo_data_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def url(self) -> str:
        return f"/media/{self.filename}"


# ───────────────────────── Page builder ─────────────────────────

class Page(Model):
    """A page is an ordered list of Sections (the draft). Publishing freezes the draft into
    `published_snapshot`, which is the only thing the public site reads."""
    __tablename__ = "pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)  # "home"
    title: Mapped[str] = mapped_column(String(255))
    seo: Mapped[dict] = mapped_column(JSON, default=dict)  # draft SEO {lang: {...}}
    published_seo: Mapped[dict] = mapped_column(JSON, default=dict)
    published_snapshot: Mapped[Optional[Any]] = mapped_column(JSON)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    scheduled_snapshot: Mapped[Optional[Any]] = mapped_column(JSON)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    preview_token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(24))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    sections = relationship(
        "Section", back_populates="page", order_by="Section.position", cascade="all, delete-orphan"
    )


class Section(Model):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    block_type: Mapped[str] = mapped_column(String(40))
    admin_label: Mapped[str] = mapped_column(String(120), default="")
    anchor: Mapped[str] = mapped_column(String(60), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # {"ar": {...}, "en": {...}}
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    page = relationship("Page", back_populates="sections")

    def to_snapshot(self) -> dict:
        return {
            "id": self.id,
            "block_type": self.block_type,
            "admin_label": self.admin_label,
            "anchor": self.anchor,
            "position": self.position,
            "is_visible": self.is_visible,
            "content": self.content,
        }


# ───────────────────────── Features library ─────────────────────────

FEATURE_MODULES = {
    "academic": "الأكاديمي والطلاب والحضور",
    "assessment": "التقييم والروبريك",
    "elearning": "التعلم الإلكتروني وبنك الأسئلة",
    "exams": "الاختبارات",
    "finance": "المالية والمحاسبة",
    "hr": "الموارد البشرية وبوابة أولياء الأمور",
    "pickup": "نداء استلام الطالب",
    "security": "الأمان والنسخ الاحتياطي",
    "ai": "الذكاء الاصطناعي",
    "nafes": "نافس ونواتج التعلم",
    "apps": "تطبيقات الجوال",
}

FEATURE_STATUSES = {"ready": "جاهزة", "soon": "قريبًا", "hidden": "مخفية"}

# Anything that looks like a date or a delivery promise inside free text.
_DATE_LIKE = re.compile(
    r"(20\d\d|\d{1,2}[/\-.]\d{1,2}|يناير|فبراير|مارس|أبريل|ابريل|مايو|يونيو|يوليو|أغسطس|اغسطس|سبتمبر|أكتوبر|اكتوبر|نوفمبر|ديسمبر|"
    r"الربع|Q[1-4]|january|february|march|april|may|june|july|august|september|october|november|december)",
    re.IGNORECASE,
)


def contains_date_like(text: str) -> bool:
    return bool(_DATE_LIKE.search(text or ""))


class Feature(Model):
    __tablename__ = "features"
    id: Mapped[int] = mapped_column(primary_key=True)
    module: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(60), default="check")
    status: Mapped[str] = mapped_column(String(10), default="ready")
    release_date: Mapped[Optional[date]] = mapped_column(Date)
    release_date_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    claim_note: Mapped[str] = mapped_column(String(500), default="")  # where the claim comes from (UAT, code…)
    position: Mapped[int] = mapped_column(Integer, default=0)

    def validation_errors(self) -> list[str]:
        errors = []
        if self.status not in FEATURE_STATUSES:
            errors.append("حالة غير معروفة.")
        if self.module not in FEATURE_MODULES:
            errors.append("موديول غير معروف.")
        if self.release_date and not self.release_date_confirmed:
            errors.append("لا يُحفظ تاريخ إطلاق إلا إذا كان مؤكدًا (فعّل خانة \"تاريخ مؤكد\").")
        if self.status == "soon":
            for label, text in (("الاسم", self.name), ("الوصف", self.description),
                                ("الاسم EN", self.name_en), ("الوصف EN", self.description_en)):
                if contains_date_like(text):
                    errors.append(f"{label}: لا تكتب تاريخًا داخل نص ميزة \"قريبًا\"؛ استخدم حقل التاريخ المؤكد.")
        return errors

    @property
    def public_release_date(self) -> Optional[date]:
        return self.release_date if (self.release_date and self.release_date_confirmed) else None


# ───────────────────────── Clients, facts, case studies ─────────────────────────

class Client(Model):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255), default="")
    kind: Mapped[str] = mapped_column(String(10), default="client")  # client | partner
    sector: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    logo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[Optional[date]] = mapped_column(Date)
    consent_proof_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    consent_notes: Mapped[str] = mapped_column(String(500), default="")
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    show_name: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    logo = relationship("Media", foreign_keys=[logo_id])
    consent_proof = relationship("Media", foreign_keys=[consent_proof_id])

    @property
    def is_publishable(self) -> bool:
        """Name or logo may appear publicly only with recorded written consent."""
        return bool(self.is_visible and self.consent and self.consent_date and self.consent_proof_id)


class Fact(Model):
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True)
    label: Mapped[str] = mapped_column(String(255))
    value: Mapped[str] = mapped_column(String(60))
    meaning: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(500), default="")
    verified_at: Mapped[Optional[date]] = mapped_column(Date)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def is_publishable(self) -> bool:
        return bool(self.is_visible and (self.source or "").strip() and self.verified_at)


class CaseStudy(Model):
    __tablename__ = "case_studies"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clients.id"))
    anonymous_label: Mapped[str] = mapped_column(String(255), default="")  # shown until client consents
    anonymous_label_en: Mapped[str] = mapped_column(String(255), default="")
    challenge: Mapped[str] = mapped_column(Text, default="")
    built: Mapped[str] = mapped_column(Text, default="")
    working_now: Mapped[str] = mapped_column(Text, default="")
    challenge_en: Mapped[str] = mapped_column(Text, default="")
    built_en: Mapped[str] = mapped_column(Text, default="")
    working_now_en: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    media_ids: Mapped[list] = mapped_column(JSON, default=list)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    client = relationship("Client")

    def display_name(self, lang: str = "ar") -> str:
        if self.client and self.client.is_publishable:
            return (self.client.name_en if lang == "en" and self.client.name_en else self.client.name)
        return (self.anonymous_label_en if lang == "en" and self.anonymous_label_en else self.anonymous_label)

    def display_url(self) -> str:
        # The URL identifies the client, so it follows the same consent rule as the name.
        return self.url if (self.client and self.client.is_publishable) else ""


# ───────────────────────── FAQ ─────────────────────────

FAQ_CATEGORIES = {
    "schools": "المدارس",
    "pricing": "الاشتراك والتسعير",
    "ai": "الذكاء الاصطناعي",
    "tech": "التقنية",
    "general": "عام",
}


class FaqItem(Model):
    __tablename__ = "faq_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(String(500))
    answer_html: Mapped[str] = mapped_column(Text)
    question_en: Mapped[str] = mapped_column(String(500), default="")
    answer_html_en: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(20), default="general")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    show_on_home: Mapped[bool] = mapped_column(Boolean, default=True)
    show_on_faq_page: Mapped[bool] = mapped_column(Boolean, default=True)
    article_ids: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(500), default="")

    def validation_errors(self) -> list[str]:
        if re.search(r"[0-9٠-٩]", f"{self.answer_html or ''}{self.answer_html_en or ''}") and not (self.source or "").strip():
            return ["الإجابة تحتوي رقمًا: اكتب مصدر الرقم في حقل \"المصدر\"."]
        return []


# ───────────────────────── Leads ─────────────────────────

LEAD_STATUSES = {"new": "جديد", "contacted": "تم التواصل", "demo": "ديمو", "lost": "خسارة"}


class Lead(Model):
    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    form: Mapped[str] = mapped_column(String(20), default="demo")  # demo | contact
    name: Mapped[str] = mapped_column(String(255))
    school: Mapped[str] = mapped_column(String(255), default="")
    company: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(60))
    email: Mapped[str] = mapped_column(String(255), default="")
    stage: Mapped[str] = mapped_column(String(120), default="")
    business_type: Mapped[str] = mapped_column(String(120), default="")
    service: Mapped[str] = mapped_column(String(120), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(60), default="")
    utm_source: Mapped[str] = mapped_column(String(255), default="")
    utm_medium: Mapped[str] = mapped_column(String(255), default="")
    utm_campaign: Mapped[str] = mapped_column(String(255), default="")
    utm_term: Mapped[str] = mapped_column(String(255), default="")
    utm_content: Mapped[str] = mapped_column(String(255), default="")
    referrer: Mapped[str] = mapped_column(String(1000), default="")
    landing_path: Mapped[str] = mapped_column(String(500), default="")
    forward_log: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ───────────────────────── Articles ─────────────────────────

article_tags = Table(
    "article_tags",
    db.metadata,
    Column("article_id", ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Model):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    landing_url: Mapped[str] = mapped_column(String(255), default="/")  # the product page this cluster feeds


class Tag(Model):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)


class Author(Model):
    __tablename__ = "authors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    job_title: Mapped[str] = mapped_column(String(255), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    photo_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    same_as: Mapped[list] = mapped_column(JSON, default=list)  # profile URLs

    photo = relationship("Media")


ARTICLE_STATUSES = {
    "draft": "مسودة",
    "review": "مراجعة",
    "scheduled": "مجدول",
    "published": "منشور",
    "archived": "مؤرشف",
}


class Article(Model):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    lang: Mapped[str] = mapped_column(String(5), default="ar")
    slug: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str] = mapped_column(String(255))
    h1: Mapped[str] = mapped_column(String(255), default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    meta_title: Mapped[str] = mapped_column(String(255), default="")
    meta_description: Mapped[str] = mapped_column(String(500), default="")
    focus_keyword: Mapped[str] = mapped_column(String(255), default="")
    secondary_keywords: Mapped[str] = mapped_column(String(500), default="")
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"))
    cover_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    og_image_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("authors.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    content_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    canonical_url: Mapped[str] = mapped_column(String(500), default="")
    noindex: Mapped[bool] = mapped_column(Boolean, default=False)
    related_mode: Mapped[str] = mapped_column(String(10), default="auto")
    audience: Mapped[str] = mapped_column(String(10), default="both", server_default="both")
    related_ids: Mapped[list] = mapped_column(JSON, default=list)
    faq: Mapped[list] = mapped_column(JSON, default=list)  # [{"q": .., "a": ..}]
    translation_of_id: Mapped[Optional[int]] = mapped_column(ForeignKey("articles.id"))
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    category = relationship("Category")
    author = relationship("Author")
    cover = relationship("Media", foreign_keys=[cover_id])
    og_image = relationship("Media", foreign_keys=[og_image_id])
    tags = relationship("Tag", secondary=article_tags)
    translation_of = relationship("Article", remote_side=[id])

    __table_args__ = (db.UniqueConstraint("lang", "slug", name="uq_article_lang_slug"),)

    @property
    def is_live(self) -> bool:
        return self.status == "published" and self.published_at is not None and self.published_at <= utcnow()

    @property
    def path(self) -> str:
        return f"/en/blog/{self.slug}" if self.lang == "en" else f"/blog/{self.slug}"

    def to_snapshot(self) -> dict:
        return {c: getattr(self, c) for c in (
            "title", "h1", "excerpt", "content_html", "meta_title", "meta_description", "focus_keyword",
            "secondary_keywords", "canonical_url", "noindex", "faq", "slug",
        )}


# ───────────────────────── SEO, redirects, backlinks ─────────────────────────

class Redirect(Model):
    __tablename__ = "redirects"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_path: Mapped[str] = mapped_column(String(500), unique=True)
    to_path: Mapped[str] = mapped_column(String(1000))
    code: Mapped[int] = mapped_column(Integer, default=301)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


BACKLINK_STATUSES = {"requested": "مطلوب", "contacted": "تم التواصل", "published": "منشور", "lost": "ضاع"}
BACKLINK_CHANNELS = {
    "clients": "عملاؤنا وشركاؤنا",
    "derived": "مواقع المنصات المشتقة",
    "social": "حسابات الشركة والمؤسس",
    "guest": "مقالات ضيف",
    "press": "أخبار وبيانات صحفية",
    "directories": "الأدلة الموثوقة",
    "assets": "أصول قابلة للربط",
    "media": "بودكاست وفيديو",
    "other": "أخرى",
}


class Backlink(Model):
    __tablename__ = "backlinks"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(String(1000))
    target_url: Mapped[str] = mapped_column(String(1000))
    anchor_text: Mapped[str] = mapped_column(String(500), default="")
    rel: Mapped[str] = mapped_column(String(10), default="dofollow")
    channel: Mapped[str] = mapped_column(String(20), default="other", index=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", index=True)
    acquired_at: Mapped[Optional[date]] = mapped_column(Date)
    owner: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    written_request_kept: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_check_result: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ───────────────────────── Integrations registry ─────────────────────────

INTEGRATION_KINDS = {
    "script": "سكربت", "api": "API", "webhook": "Webhook", "embed": "Embed",
    "form": "نموذج", "verification": "تحقق ملكية",
}
INTEGRATION_PLACEMENTS = {
    "head": "head", "body_end": "نهاية body", "page": "صفحة بعينها", "none": "لا يُحقن (خارجي/سيرفر)",
}


class Integration(Model):
    __tablename__ = "integrations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    placement: Mapped[str] = mapped_column(String(20), default="head")
    page_scope: Mapped[str] = mapped_column(String(255), default="*")  # "*" or comma-separated paths
    identifier: Mapped[str] = mapped_column(String(255), default="")  # public ID only (G-…, pixel id)
    code: Mapped[str] = mapped_column(Text, default="")  # snippet injected verbatim; never secrets
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    owner: Mapped[str] = mapped_column(String(120), default="")
    last_verified_at: Mapped[Optional[date]] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    def applies_to(self, path: str) -> bool:
        scope = (self.page_scope or "*").strip()
        if scope == "*":
            return True
        return path in {p.strip() for p in scope.split(",") if p.strip()}


# ───────────────────────── Legal pages, display files ─────────────────────────

class LegalPage(Model):
    __tablename__ = "legal_pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)  # privacy | terms | refund
    title: Mapped[str] = mapped_column(String(255))
    meta_description: Mapped[str] = mapped_column(String(500), default="")
    body_html: Mapped[str] = mapped_column(Text)  # everything inside <body>, bilingual markup preserved
    last_updated: Mapped[Optional[date]] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


FILE_PLACEMENTS = {"hero": "الـ Hero", "footer": "التذييل", "case_studies": "قسم دراسات الحالة", "page": "صفحة الملفات"}


class DisplayFile(Model):
    __tablename__ = "display_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255))
    display_name_en: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    cover_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    public_path: Mapped[str] = mapped_column(String(255), unique=True)  # e.g. "manasety-profile.pdf"
    external_url: Mapped[str] = mapped_column(String(1000), default="")  # when the "file" is a link
    stored_filename: Mapped[str] = mapped_column(String(255), default="")
    mime: Mapped[str] = mapped_column(String(100), default="application/pdf")
    placements: Mapped[list] = mapped_column(JSON, default=list)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    direct_link_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    show_counter: Mapped[bool] = mapped_column(Boolean, default=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    cover = relationship("Media")

    @property
    def href(self) -> str:
        return self.external_url or f"/{self.public_path}"


# ───────────────────────── Settings ─────────────────────────

class Setting(Model):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SideCard(Model):
    __tablename__ = "side_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    image_id: Mapped[Optional[int]] = mapped_column(ForeignKey("media.id"))
    button_label: Mapped[str] = mapped_column(String(60), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    audience: Mapped[str] = mapped_column(String(10), default="both")
    side: Mapped[str] = mapped_column(String(10), default="both")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
