"""Broken-link scan of published content and live check of recorded backlinks."""
from __future__ import annotations

import ipaddress
import re
import socket
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import requests

from ..extensions import db
from ..models import Article, Backlink, utcnow

UA = {"User-Agent": "ManasetyLinkCheck/1.0 (+https://manasety.ai)"}
TIMEOUT = 10
MAX_REDIRECTS = 5


class UnsafeURL(ValueError):
    pass


def assert_public_url(url: str) -> None:
    """URLs come from editors, so never let the checker reach the server's own network
    (loopback, RFC1918, link-local/metadata, reserved). Every resolved address is checked."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("scheme")
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURL("dns") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL("private address")


def _assert_public_peer(r: requests.Response) -> None:
    """Check the address the socket actually connected to. Closes the DNS-rebinding gap between
    assert_public_url()'s lookup and the connect (the body is not read until this passes)."""
    conn = getattr(r.raw, "_connection", None) or getattr(r.raw, "connection", None)
    sock = getattr(conn, "sock", None)
    if sock is None:
        r.close()
        raise UnsafeURL("peer unknown")
    ip = ipaddress.ip_address(sock.getpeername()[0])
    if not ip.is_global or ip.is_multicast:
        r.close()
        raise UnsafeURL("private address (rebinding)")


def safe_request(method: str, url: str, **kwargs) -> requests.Response:
    """requests with redirects followed by hand so every hop is re-validated, before and after connect."""
    kwargs.pop("stream", None)
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_url(url)
        with requests.Session() as session:
            session.trust_env = False  # no proxy env vars: we must see the real peer
            r = session.request(method, url, allow_redirects=False, timeout=TIMEOUT, headers=UA, stream=True, **kwargs)
        _assert_public_peer(r)
        if r.is_redirect and r.headers.get("Location"):
            r.close()
            url = urljoin(url, r.headers["Location"])
            continue
        return r
    raise UnsafeURL("too many redirects")


def _status(url: str) -> int:
    try:
        r = safe_request("HEAD", url)
        if r.status_code in (405, 403):  # some hosts refuse HEAD
            r = safe_request("GET", url, stream=True)
        return r.status_code
    except (requests.RequestException, UnsafeURL):
        return 0


def scan_broken_links(site_url: str, extra_urls: Iterable[str] = ()) -> list[dict]:
    """Check every link inside live articles plus the given URLs. Returns only failures."""
    found: dict[str, set[str]] = {}
    for art in db.session.query(Article).filter(Article.status == "published").all():
        for href in re.findall(r'href="([^"#]+)', art.content_html or ""):
            if href.startswith(("mailto:", "tel:")):
                continue
            url = site_url + href if href.startswith("/") else href
            found.setdefault(url, set()).add(art.path)
    for url in extra_urls:
        found.setdefault(url, set()).add("(صفحة)")
    broken = []
    for url, pages in sorted(found.items()):
        code = _status(url)
        if code == 0 or code >= 400:
            broken.append({"url": url, "status": code, "pages": sorted(pages)})
    return broken


def check_backlink(link: Backlink, site_host: str = "manasety.ai") -> None:
    """Fetch the source page and confirm it still links to us (and with which rel)."""
    try:
        r = safe_request("GET", link.source_url)
        html = r.text if r.ok else ""
    except (requests.RequestException, UnsafeURL) as exc:
        html, r = "", None
        link.last_check_result = f"تعذر الوصول: {exc.__class__.__name__}"
    if r is not None:
        # Parse each <a> once (pairing two separate regex lists misaligns on <a> without href),
        # and match our host exactly or as a subdomain (not "manasety.ai.evil.com").
        hit = None
        for tag in re.findall(r"<a\b[^>]*>", html, re.I):
            href = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", tag, re.I)
            host = (urlsplit(href.group(1)).hostname or "").lower() if href else ""
            if host == site_host or host.endswith("." + site_host):
                hit = tag
                break
        if hit:
            rel = "nofollow" if re.search(r"rel=[\"'][^\"']*(nofollow|sponsored|ugc)", hit, re.I) else "dofollow"
            link.last_check_result = f"موجود ({rel})"
            link.rel = rel
            if link.status == "lost":
                link.status = "published"
        else:
            link.last_check_result = f"الرابط غير موجود (HTTP {r.status_code})"
            if link.status == "published":
                link.status = "lost"
    link.last_checked_at = utcnow()
