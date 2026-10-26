"""Claim-registry rules: consent before names/logos, source before numbers, feature status."""
from datetime import date

from manasety.extensions import db
from manasety.models import Client, Fact, FaqItem, Feature, Media, Page
from manasety.publishing import publish_page, render_rich, resolve_facts


def _home_html(client) -> str:
    return client.get("/").data.decode()


def test_client_without_consent_never_appears(client):
    html = _home_html(client)
    for c in db.session.query(Client).all():
        assert c.name not in html  # ticket 3: automated check, name AND logo absent


def test_client_appears_only_with_full_consent(client, app):
    proof = Media(filename="p.webp", original_name="p", mime="image/webp", kind="image", size=1, alt="proof")
    logo = Media(filename="logo-x.webp", original_name="l", mime="image/webp", kind="image", size=1, alt="شعار")
    db.session.add_all([proof, logo])
    db.session.flush()
    c = db.session.query(Client).filter_by(kind="partner").limit(1).one()
    c.logo_id = logo.id
    c.consent = True
    db.session.commit()
    assert c.name not in _home_html(client)          # consent alone is not enough
    c.consent_date = date(2026, 10, 20)
    db.session.commit()
    assert c.name not in _home_html(client)          # still needs the proof file
    c.consent_proof_id = proof.id
    db.session.commit()
    html = _home_html(client)
    assert c.name in html and "logo-x.webp" in html
    assert "p.webp" not in html                       # the proof itself is never public


def test_unverified_fact_is_not_published(client):
    assert resolve_facts("x [[fact:qdrat_students]] y") == "x  y"
    assert resolve_facts("a[[if:qdrat_students]] — 2000 طالب[[/if]]b") == "ab"


def test_fact_needs_source_and_date(client):
    f = db.session.query(Fact).filter_by(key="qdrat_students").one()
    f.is_visible = True
    db.session.commit()
    assert resolve_facts("[[fact:qdrat_students]]") == ""
    f.source, f.verified_at = "خطاب المعهد", date(2026, 10, 25)
    db.session.commit()
    from flask import g
    g.pop("_facts", None)
    assert resolve_facts("[[fact:qdrat_students]] طالب") == "2000 طالب"


def test_fact_value_is_escaped_inside_rich_text(client):
    f = db.session.query(Fact).filter_by(key="marsoud_clients").one()
    f.value, f.source, f.verified_at, f.is_visible = "<img src=x onerror=alert(1)>", "s", date(2026, 1, 1), True
    db.session.commit()
    out = str(render_rich("<p>[[fact:marsoud_clients]]</p>"))
    assert "<img" not in out and "&lt;img" in out


def test_if_segment_removal_cannot_splice_markup(client):
    out = str(render_rich('<p><a href="https://x[[if:qdrat_students]]">[[/if]]" onclick="alert(1)">t</a></p>'))
    assert "onclick" not in out


def test_soon_feature_rejects_dates_without_confirmed_field():
    f = Feature(module="apps", name="تطبيق الجوال", description="يصدر في يناير 2027", status="soon")
    assert f.validation_errors()
    f2 = Feature(module="apps", name="تطبيق الجوال", description="قريبًا", status="soon", release_date=date(2027, 1, 1))
    assert any("مؤكد" in e for e in f2.validation_errors())
    f2.release_date_confirmed = True
    assert not f2.validation_errors()


def test_soon_badge_and_hidden_feature(client):
    assert "قريبًا" in _home_html(client)
    feat = db.session.query(Feature).filter_by(name="الجدول الذكي").one()
    assert feat.name in _home_html(client)
    feat.status = "hidden"
    db.session.commit()
    assert feat.name not in _home_html(client)


def test_faq_answer_with_number_requires_source():
    item = FaqItem(question="q", answer_html="<p>أكثر من 400 عميل</p>")
    assert item.validation_errors()
    item.source = "تقرير مرصود"
    assert not item.validation_errors()


def test_hidden_faq_not_in_html_or_schema(client):
    item = db.session.query(FaqItem).filter_by(show_on_home=True).limit(1).one()
    html = _home_html(client)
    assert html.count(item.question) == 2  # visible list + FAQPage schema
    item.is_visible = False
    db.session.commit()
    assert item.question not in _home_html(client)


def test_hidden_section_removed_after_publish(client):
    page = db.session.query(Page).filter_by(slug="home").one()
    ai = next(s for s in page.sections if s.block_type == "ai")
    ai.is_visible = False
    db.session.commit()
    assert 'id="ai"' in _home_html(client)   # draft change: public page unchanged
    publish_page(page)
    db.session.commit()
    assert 'id="ai"' not in _home_html(client)
