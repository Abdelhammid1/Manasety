"""Slugs, TOC, JSON-LD schema, sitemap entries and the article quality / internal-link checks."""
from __future__ import annotations

import html as htmllib
import json
import re
from typing import Any, Iterable, Optional

from markupsafe import Markup

_AR_MAP = {
    "ا": "a", "أ": "a", "إ": "e", "آ": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "g", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z",
    "ع": "a", "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "a",
    "و": "w", "ؤ": "o", "ي": "y", "ى": "a", "ئ": "e", "ء": "", "ـ": "",
}
_STOP = {"al", "fy", "mn", "aly", "an", "w", "the", "a", "of", "and", "to", "in"}


def slugify(text: str, max_words: int = 6) -> str:
    """Short Latin slug (Arabic URLs show up percent-encoded when shared on WhatsApp)."""
    text = (text or "").strip().lower()
    text = "".join(_AR_MAP.get(ch, ch) for ch in text)
    text = re.sub(r"[ًٌٍَُِّْ]", "", text)  # harakat
    words = [w for w in re.split(r"[^a-z0-9]+", text) if w]
    words = [w[2:] if w.startswith("al") and len(w) > 4 else w for w in words]  # drop definite article
    words = [w for w in words if w not in _STOP] or words
    return "-".join(words[:max_words])[:80].strip("-") or "article"


_HEADING_RE = re.compile(r"<(h[23])([^>]*)>(.*?)</\1>", re.S | re.I)
_TAGS_RE = re.compile(r"<[^>]+>")


def strip_tags(value: str) -> str:
    return htmllib.unescape(_TAGS_RE.sub(" ", value or "")).replace("\xa0", " ")


def add_heading_ids(content: str) -> tuple[str, list[dict]]:
    """Give every h2/h3 a stable id and return the TOC entries."""
    toc: list[dict] = []
    used: set[str] = set()

    def repl(m: re.Match) -> str:
        tag, attrs, inner = m.group(1).lower(), m.group(2), m.group(3)
        text = strip_tags(inner).strip()
        existing = re.search(r'id="([^"]+)"', attrs)
        hid = existing.group(1) if existing else (slugify(text, 8) or f"s-{len(toc) + 1}")
        base, n = hid, 2
        while hid in used:
            hid, n = f"{base}-{n}", n + 1
        used.add(hid)
        toc.append({"level": int(tag[1]), "id": hid, "text": text})
        attrs = re.sub(r'\s*id="[^"]*"', "", attrs)
        return f'<{tag}{attrs} id="{hid}">{inner}</{tag}>'

    return _HEADING_RE.sub(repl, content or ""), toc


def word_count(content: str) -> int:
    return len(strip_tags(content).split())


_TABLE_TAG_RE = re.compile(r"<table\b|</table>", re.I)
_WRAP_OPEN = '<div class="table-wrap">'


def wrap_tables(content: str) -> str:
    """Give each table a horizontal scroller for phones. Returns plain str on purpose: this is a text
    edit (a "<table" inside an attribute value would be hit too), so the result must still go through
    the sanitiser (`|tables|rich` in templates), which keeps only <div class="table-wrap">.
    Tables already wrapped (written that way in the HTML view) are left alone."""
    content = str(content or "")
    out, pos, stack = [], 0, []
    for m in _TABLE_TAG_RE.finditer(content):
        out.append(content[pos:m.start()])
        if m.group(0).lower() == "</table>":
            out.append(m.group(0))
            if stack and stack.pop():
                out.append("</div>")
        else:
            wrapped = content[:m.start()].rstrip().endswith(_WRAP_OPEN)
            stack.append(not wrapped)
            out.append(m.group(0) if wrapped else _WRAP_OPEN + m.group(0))
        pos = m.end()
    out.append(content[pos:])
    return "".join(out)


# A paragraph that is nothing but bold text: usually a heading pasted from Word/Docs as <b>.
# Same rule as isBoldLine() in editor.js: every visible character sits inside <strong>/<b>.
_PARA_RE = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)
_BOLD_RUN_RE = re.compile(r"<(strong|b)\b[^>]*>.*?</\1>", re.I | re.S)


def bold_line_count(content: str) -> int:
    count = 0
    for inner in _PARA_RE.findall(content or ""):
        text = strip_tags(inner).strip()
        if not 2 <= len(text) <= 150 or not _BOLD_RUN_RE.search(inner):
            continue
        if not strip_tags(_BOLD_RUN_RE.sub("", inner)).strip():
            count += 1
    return count


def jsonld(data: Any) -> Markup:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    raw = raw.replace("</", "<\\/")  # no premature </script>
    return Markup(f'<script type="application/ld+json">{raw}</script>')


def organization_schema(s: dict, site_url: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": f"{site_url}/#organization",
        "name": s["brand_name_ar"],
        "alternateName": [s["brand_name_en"], s["legal_name_en"]],
        "legalName": s["legal_name_en"],
        "url": site_url + "/",
        "logo": f"{site_url}/static/img/logo.svg",
        "email": s["email"],
        "address": {"@type": "PostalAddress", "streetAddress": s["address_ar"],
                    "addressLocality": "قويسنا", "addressRegion": "المنوفية", "addressCountry": "EG"},
        "sameAs": [x["url"] for x in s.get("social", []) if x.get("url")],
    }


def website_schema(s: dict, site_url: str) -> dict:
    return {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{site_url}/#website",
            "url": site_url + "/", "name": s["brand_name_ar"], "inLanguage": "ar",
            "publisher": {"@id": f"{site_url}/#organization"}}


def software_schema(site_url: str, name: str, description: str) -> dict:
    # No offers/price (no prices on the site during the PayTabs review), no ratings (none verified).
    return {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": name,
            "applicationCategory": "EducationalApplication", "operatingSystem": "Web",
            "description": description, "url": site_url + "/", "inLanguage": "ar",
            "publisher": {"@id": f"{site_url}/#organization"}}


def breadcrumb_schema(items: Iterable[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": url} for i, (name, url) in enumerate(items)]}


def faq_schema(pairs: list[tuple[str, str]]) -> Optional[dict]:
    if not pairs:
        return None
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": strip_tags(a).strip()}}
        for q, a in pairs]}


def article_schema(article: Any, site_url: str, image_url: str = "") -> dict:
    data: dict[str, Any] = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": article.h1 or article.title,
        "description": article.meta_description or article.excerpt,
        "inLanguage": article.lang,
        "mainEntityOfPage": site_url + article.path,
        "datePublished": article.published_at.isoformat() if article.published_at else None,
        "dateModified": (article.content_updated_at or article.published_at).isoformat() if article.published_at else None,
        "publisher": {"@id": f"{site_url}/#organization"},
    }
    if image_url:
        data["image"] = image_url
    if article.author:
        data["author"] = person_schema(article.author, site_url)
    if article.focus_keyword:
        data["keywords"] = ", ".join(filter(None, [article.focus_keyword, article.secondary_keywords]))
    return data


def person_schema(author: Any, site_url: str) -> dict:
    data = {"@type": "Person", "name": author.name, "url": f"{site_url}/authors/{author.slug}"}
    if author.job_title:
        data["jobTitle"] = author.job_title
    if author.same_as:
        data["sameAs"] = author.same_as
    return data


# ───────── article quality ─────────

def article_checks(article: Any, product_url: str = "/", min_related: int = 2) -> list[dict]:
    """Return [{ok, label}] shown beside the editor. Advisory except where noted at publish time."""
    content = article.content_html or ""
    text = strip_tags(content)
    kw = (article.focus_keyword or "").strip()
    first_para = text.strip()[:400]
    meta_t = article.meta_title or article.title or ""
    title = article.h1 or article.title or ""
    links = re.findall(r'href="([^"]+)"', content)
    internal = [h for h in links if h.startswith("/") or "manasety.ai" in h]
    to_product = any(h.split("#")[0].rstrip("/") in ("", product_url.rstrip("/"), "https://manasety.ai") for h in internal)
    to_articles = {h for h in internal if "/blog/" in h}
    bold_lines = bold_line_count(content)
    imgs_without_alt = re.findall(r"<img(?![^>]*\balt=\"[^\"]+\")[^>]*>", article.content_html or "")
    checks = [
        (bool(kw), "تحديد كلمة مفتاحية أساسية"),
        (bool(kw) and kw in title, "الكلمة المفتاحية في العنوان/H1"),
        (bool(kw) and kw in first_para, "الكلمة المفتاحية في أول فقرة"),
        (bool(kw) and kw in (article.meta_description or ""), "الكلمة المفتاحية في الـ Meta Description"),
        (30 <= len(meta_t) <= 65, f"طول الـ Meta Title مناسب (30–65 حرفًا، الحالي {len(meta_t)})"),
        (70 <= len(article.meta_description or "") <= 160,
         f"طول الـ Meta Description مناسب (70–160، الحالي {len(article.meta_description or '')})"),
        (word_count(content) >= 600, f"طول المقال 600 كلمة فأكثر (الحالي {word_count(content)})"),
        ("<h2" in content, "يحتوي عناوين H2"),
        (bold_lines == 0, "لا توجد سطور غامقة مكان العناوين" if bold_lines == 0 else
         f"{bold_lines} سطر غامق يبدو كعنوان: حوّله بزر «تحويل لعنوان»"),
        (to_product, "رابط داخلي لصفحة المنتج"),
        (len(to_articles) >= min_related, f"روابط لمقالين ذوي صلة على الأقل (الحالي {len(to_articles)})"),
        (not imgs_without_alt, "كل الصور داخل المقال لها alt"),
        (bool(article.cover_id), "صورة رئيسية"),
        (bool(article.author_id), "كاتب حقيقي محدد"),
        (bool(article.human_reviewed), "مراجعة بشرية قبل النشر"),
    ]
    return [{"ok": ok, "label": label} for ok, label in checks]


def suggest_internal_links(article: Any, candidates: list[Any], limit: int = 6) -> list[Any]:
    """Rank other live articles by shared category / keyword overlap."""
    words = set(re.findall(r"\w{4,}", f"{article.title} {article.focus_keyword} {article.secondary_keywords}"))
    scored = []
    for other in candidates:
        if other.id == article.id:
            continue
        other_words = set(re.findall(r"\w{4,}", f"{other.title} {other.focus_keyword} {other.secondary_keywords}"))
        score = len(words & other_words) + (3 if other.category_id and other.category_id == article.category_id else 0)
        if score:
            scored.append((score, other))
    scored.sort(key=lambda x: -x[0])
    return [o for _, o in scored[:limit]]
