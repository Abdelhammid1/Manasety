"""Runtime configuration. Every secret comes from the environment, never from code or the DB."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SITE_URL = os.environ.get("SITE_URL", "https://manasety.ai").rstrip("/")
    MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", BASE_DIR / "media"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "40")) * 1024 * 1024
    MAX_IMAGE_MB = int(os.environ.get("MAX_IMAGE_MB", "8"))

    # Staging: whole site noindex + basic-auth gate (spec: deploy step 2)
    STAGING = _bool("STAGING")
    STAGING_USER = os.environ.get("STAGING_USER", "")
    STAGING_PASSWORD = os.environ.get("STAGING_PASSWORD", "")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 6

    TRUST_PROXY = _bool("TRUST_PROXY", True)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Lead forwarding (the current site's integrations, moved server-side)
    MARSOUD_LEAD_URL = os.environ.get(
        "MARSOUD_LEAD_URL", "https://marsoud.com/api/v1/public/contact-lead"
    )
    MARSOUD_CONTACT_TOKEN = os.environ.get("MARSOUD_CONTACT_TOKEN", "")
    WEB3FORMS_ACCESS_KEY = os.environ.get("WEB3FORMS_ACCESS_KEY", "")
    N8N_LEAD_WEBHOOK_URL = os.environ.get("N8N_LEAD_WEBHOOK_URL", "")
    LEAD_FORWARD_SYNC = _bool("LEAD_FORWARD_SYNC")  # tests run forwarding inline

    # Email notifications (Microsoft 365 SMTP)
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.office365.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)
    LEAD_NOTIFY_TO = os.environ.get("LEAD_NOTIFY_TO", "hello@manasety.ai")

    # Search Console API (phase 3 dashboard). Path to a service-account JSON file.
    GSC_CREDENTIALS_FILE = os.environ.get("GSC_CREDENTIALS_FILE", "")
    GSC_PROPERTY = os.environ.get("GSC_PROPERTY", "sc-domain:manasety.ai")

    # Directory holding the old static site (served for LEGACY_FILES only)
    LEGACY_DIR = Path(os.environ.get("LEGACY_DIR", BASE_DIR.parent))

    BACKUP_STATUS_FILE = os.environ.get("BACKUP_STATUS_FILE", str(BASE_DIR / "instance" / "backup-status.json"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    LEAD_FORWARD_SYNC = True
    SECRET_KEY = "test"


# Old static files that still answer 200 on manasety.ai and must keep working byte-for-byte
# after the switch (inventory taken 2026-10-26). index.html is handled by a 301 to "/".
LEGACY_FILES = {
    "contact.html", "saas.html", "lexoffice.html", "gym-system.html", "syrian-house-proposal.html",
    "manasety-landing-v2.html", "logo-animated-preview.html", "logo-animated.svg",
    "favicon.ico", "favicon.svg", "favicon-96x96.png", "apple-touch-icon.png", "site.webmanifest",
    "web-app-manifest-192x192.png", "web-app-manifest-512x512.png", "og-image.png",
    "legal.css", "legal.js", "indexold23-09-2026.html",
}
# Old static sub-sites served as whole folders (unknown sub-paths fall back to the folder's index.html,
# because they use path-based URLs, e.g. /sara/<name>).
LEGACY_DIRS = {"sara"}
