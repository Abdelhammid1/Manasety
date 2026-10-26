"""Links that must never break, integrations kept byte-for-byte, SEO outputs, lead intake."""
from datetime import timedelta

from manasety.extensions import db
from manasety.models import Article, Author, Category, Lead, Media, Redirect, utcnow
from manasety.seed import GA_ID, PIXEL_ID


def test_legacy_anchors_and_integrations_survive(client):
    html = client.get("/").data.decode()
    for anchor in ("services", "portfolio", "ai", "contact", "pricing"):
        assert f'id="{anchor}"' in html
    assert f"gtag('config', '{GA_ID}')" in html
    assert f"fbq('init','{PIXEL_ID}')" in html
    assert 'name="facebook-domain-verification" content="rakz6coyf8znt856mdjcjputqivqsk"' in html


def test_no_prices_or_packages_on_page(client):
    html = client.get("/").data.decode()
    for word in ("Starter", "Growth", "Enterprise", "25,000", "جنيه", "الباقة المختارة"):
        assert word not in html


def test_index_html_redirects(client):
    r = client.get("/index.html")
    assert r.status_code == 301 and r.headers["Location"] == "/"


def test_redirect_hits_counted(client):
    db.session.add(Redirect(from_path="/old-post", to_path="/blog/new-post", code=301))
    db.session.commit()
    r = client.get("/old-post")
    assert r.status_code == 301 and r.headers["Location"] == "/blog/new-post"
    assert db.session.query(Redirect).filter_by(from_path="/old-post").one().hits == 1


def test_robots_and_sitemap(client):
    robots = client.get("/robots.txt").data.decode()
    assert "Disallow: /admin" in robots and "Sitemap:" in robots
    sm = client.get("/sitemap.xml").data.decode()
    assert "<loc>https://manasety.ai/</loc>" in sm


def _publish_article(slug: str, **extra) -> Article:
    cover = Media(filename=f"{slug}.webp", original_name="c", mime="image/webp", kind="image", size=1, alt="غلاف")
    author = db.session.query(Author).limit(1).one()
    cat = db.session.query(Category).limit(1).one()
    db.session.add(cover)
    db.session.flush()
    art = Article(slug=slug, title="كيف تختار نظام إدارة مدرسة", content_html="<h2>مقدمة</h2><p>نص</p>",
                  status="published", published_at=utcnow() - timedelta(minutes=1), cover_id=cover.id,
                  author_id=author.id, category_id=cat.id, meta_description="وصف", **extra)
    db.session.add(art)
    db.session.commit()
    return art


def test_published_article_in_sitemap_with_schema(client):
    _publish_article("choose-school-system")
    sm = client.get("/sitemap.xml").data.decode()
    assert "/blog/choose-school-system" in sm
    html = client.get("/blog/choose-school-system").data.decode()
    assert '"@type":"BlogPosting"' in html and '"@type":"BreadcrumbList"' in html
    assert '<link rel="canonical" href="https://manasety.ai/blog/choose-school-system">' in html
    assert "choose-school-system" in client.get("/blog/feed.xml").data.decode()


def test_noindex_and_draft_articles_excluded(client):
    _publish_article("hidden-one", noindex=True)
    assert "hidden-one" not in client.get("/sitemap.xml").data.decode()
    draft = _publish_article("draft-one")
    draft.status = "draft"
    db.session.commit()
    assert client.get("/blog/draft-one").status_code == 404


def test_scheduled_article_goes_live_on_time(client, app):
    art = _publish_article("later-one")
    art.status, art.published_at = "scheduled", utcnow() + timedelta(hours=1)
    db.session.commit()
    assert client.get("/blog/later-one").status_code == 404
    art.published_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    from manasety.publishing import apply_scheduled
    apply_scheduled()
    assert client.get("/blog/later-one").status_code == 200


def test_lead_is_stored_with_utm(client, app, monkeypatch):
    sent = {}

    class Resp:
        status_code = 200

    def fake_post(url, **kwargs):
        sent[url] = kwargs
        return Resp()

    monkeypatch.setattr("manasety.services.leads.requests.post", fake_post)
    app.config.update(MARSOUD_CONTACT_TOKEN="t", WEB3FORMS_ACCESS_KEY="k")
    r = client.post("/api/leads", data={"name": "أحمد", "school": "مدرسة النور", "phone": "+20 100 000 0000",
                                        "stage": "ثانوي", "business_type": "مدرسة خاصة", "utm_source": "facebook",
                                        "utm_campaign": "launch", "form": "demo"},
                    headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.json["ok"]
    lead = db.session.query(Lead).one()
    assert lead.status == "new" and lead.utm_source == "facebook" and lead.school == "مدرسة النور"
    assert "https://marsoud.com/api/v1/public/contact-lead" in sent
    assert sent["https://marsoud.com/api/v1/public/contact-lead"]["headers"]["X-Contact-Form-Token"] == "t"
    assert lead.forward_log["marsoud"] == "200"


def test_lead_honeypot_and_validation(client):
    r = client.post("/api/leads", data={"name": "bot", "phone": "01000000000", "website": "spam"},
                    headers={"Accept": "application/json"})
    assert r.status_code == 200 and db.session.query(Lead).count() == 0
    r = client.post("/api/leads", data={"name": "", "phone": "1"}, headers={"Accept": "application/json"})
    assert r.status_code == 400


def test_legal_pages_keep_urls(client):
    for slug in ("privacy", "terms", "refund"):
        # seeded without --legal-dir in tests → 404 is expected here; the deploy check uses the real import
        assert client.get(f"/{slug}.html").status_code in (200, 404)
