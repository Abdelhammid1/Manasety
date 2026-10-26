"""HTML sanitising, permission checks, audit logging and revision helpers."""
from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable, Optional

import nh3
from flask import abort, request
from flask_login import current_user

from .extensions import db
from .models import AuditLog, Revision

# Rich-text editor output (articles, FAQ answers, section rich text).
_RICH_TAGS = {
    "p", "br", "strong", "b", "em", "i", "u", "s", "h2", "h3", "h4", "ul", "ol", "li", "a",
    "blockquote", "code", "pre", "hr", "img", "figure", "figcaption", "table", "thead", "tbody",
    "tr", "th", "td", "span", "iframe", "bdi", "sup", "sub", "dl", "dt", "dd",
}
_RICH_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height", "loading"},
    "iframe": {"src", "width", "height", "title", "allowfullscreen", "loading"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "h2": {"id"}, "h3": {"id"}, "h4": {"id"},
    "span": {"dir", "lang"}, "p": {"dir"}, "bdi": set(),
}

# Legal pages keep their original bilingual markup (classes, ids, the language toggle button).
_LEGAL_TAGS = _RICH_TAGS | {"header", "footer", "main", "aside", "nav", "article", "section", "div", "button", "h1"}
_LEGAL_ATTRS: dict[str, set[str]] = {tag: {"class", "id", "aria-label", "aria-current", "dir", "lang", "role"} for tag in _LEGAL_TAGS}
for _tag, _attrs in _RICH_ATTRS.items():
    _LEGAL_ATTRS[_tag] = _LEGAL_ATTRS.get(_tag, set()) | _attrs
_LEGAL_ATTRS["button"] |= {"type"}

# Only video embeds are allowed inside iframes (YouTube for the Shalaby channel).
_IFRAME_HOSTS = ("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/")


def _filter_attr(tag: str, attr: str, value: str) -> Optional[str]:
    if tag == "iframe" and attr == "src" and not value.startswith(_IFRAME_HOSTS):
        return None
    return value


def clean_rich(html: str) -> str:
    return nh3.clean(
        html or "", tags=_RICH_TAGS, attributes=_RICH_ATTRS, attribute_filter=_filter_attr,
        url_schemes={"http", "https", "mailto", "tel"}, link_rel="noopener",
    )


def clean_legal(html: str) -> str:
    return nh3.clean(
        html or "", tags=_LEGAL_TAGS, attributes=_LEGAL_ATTRS, attribute_filter=_filter_attr,
        url_schemes={"http", "https", "mailto", "tel"}, link_rel=None,
    )


_TAG_RE = re.compile(r"<[^>]*>")


def clean_text(text: str) -> str:
    """Plain text fields: strip every tag. No entity-escaping here — Jinja autoescapes on output."""
    return _TAG_RE.sub("", text or "").strip()


def permission_required(permission: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.can(permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def admin_required(view: Callable) -> Callable:
    return permission_required("__admin_only__")(view)


def _client_ip() -> str:
    return (request.remote_addr or "")[:64]  # real client IP via ProxyFix


def audit(action: str, entity_type: str, entity_id: Any = None, before: Any = None, after: Any = None,
          summary: str = "") -> None:
    user = current_user if current_user and current_user.is_authenticated else None
    db.session.add(AuditLog(
        user_id=user.id if user else None,
        user_label=user.email if user else "system",
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary[:500],
        before=_jsonable(before),
        after=_jsonable(after),
        ip=_client_ip() if request else None,
    ))


def snapshot_model(obj: Any, exclude: tuple[str, ...] = ("password_hash", "totp_secret", "backup_codes")) -> dict:
    data = {}
    for col in obj.__table__.columns:
        if col.key in exclude or col.name in exclude:
            continue
        data[col.name] = getattr(obj, col.key)
    return _jsonable(data)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def add_revision(entity_type: str, entity_id: int, snapshot: Any, note: str = "") -> Revision:
    rev = Revision(
        entity_type=entity_type, entity_id=entity_id, snapshot=_jsonable(snapshot), note=note,
        created_by_id=current_user.id if current_user and current_user.is_authenticated else None,
    )
    db.session.add(rev)
    return rev
