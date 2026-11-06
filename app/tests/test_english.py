"""English version: same templates, English text, Arabic untouched, and hidden until switched on."""
import re
from pathlib import Path

import pytest

from manasety import seed as seed_module
from manasety.extensions import db
from manasety.i18n import AR_RE, t, t_or_empty, translate_text
from manasety.i18n_catalog import CONTENT, UI
from manasety.models import Feature, Lead, Page, Section
from manasety.services.translations import fill_english, import_translations
from manasety.settings_store import get_setting, set_setting
from tests.conftest import login, make_user
from tests.test_public import _publish_article


def _enable():
    set_setting("english_enabled", True)
    db.session.commit()


def _visible_text(html: str) -> str:
    html = html[html.index("<body"):]
    html = re.sub(r"<(script|style|svg|template)\b.*?</\1>", "", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


def _strings(value):
    if isinstance(value, str):
        if AR_RE.search(value):
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


def test_all_seeded_copy_has_a_translation():
    table = {**UI, **CONTENT}
    sources = [s["content"]["ar"] for s in seed_module.HOME_SECTIONS + seed_module.ABOUT_SECTIONS + seed_module.CONTACT_SECTIONS] + [
        [seo for *_x, seo in seed_module.EXTRA_PAGES],
        [(n, d) for _m, _i, n, d, _s in seed_module.FEATURES],
        [(q, a) for q, _c, a in seed_module.FAQ_HOME], seed_module.FAQ_LEGACY, seed_module.CLIENTS,
        [n for n, _s in seed_module.CATEGORIES]]
    missing = sorted({s for src in sources for s in _strings(src) if translate_text(s, table) is None})
    assert not missing, missing


def test_every_template_label_is_in_the_dictionary():
    root = Path(__file__).parents[1] / "manasety" / "templates" / "public"
    found = {m for f in root.rglob("*.html") for m in re.findall(r"(?<![\w.])t\('([^'\n]*)'\)", f.read_text(encoding="utf-8"))}
    assert found and not sorted(x for x in found if x not in UI)


def test_translations_never_add_numbers():
    """The rule for the whole site: English may not state a figure the Arabic does not."""
    western = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    for ar, en in {**UI, **CONTENT}.items():
        assert set(re.findall(r"\d+", en)) <= set(re.findall(r"\d+", ar.translate(western))), ar


def test_english_is_hidden_until_switched_on(client):
    for path in ("/en/", "/en/faq", "/en/blog", "/en/thank-you", "/en/business"):
        assert client.get(path).status_code == 404, path
    assert b"lang-switch" not in client.get("/").data


def test_staff_can_review_english_before_it_is_live(client):
    user, secret = make_user("marketer")
    login(client, user, secret)
    html = client.get("/en/").data.decode()
    assert 'name="robots" content="noindex' in html and "Unpublished English version" in html


def test_home_in_english_has_no_arabic_left(client):
    _enable()
    r = client.get("/en/")
    assert r.status_code == 200
    html = r.data.decode()
    assert '<html lang="en" dir="ltr">' in html and "One system for your whole school." in html
    # the only Arabic allowed: the button that switches to Arabic
    text = _visible_text(html).replace("العربية", "")
    assert not AR_RE.search(text), re.findall(r"\S*[؀-ۿ]+\S*", text)[:30]


def test_arabic_home_is_unchanged_apart_from_the_button(client):
    before = client.get("/").data.decode()
    _enable()
    after = client.get("/").data.decode()
    assert '<html lang="ar" dir="rtl">' in after and "نظام واحد لمدرستك كلها." in after
    assert 'href="/en/"' in after and 'href="/en/"' not in before
    assert 'hreflang="en" href="https://manasety.ai/en/"' in after


def test_language_button_goes_to_the_same_page_both_ways(client):
    _enable()
    assert re.search(r'class="lang-switch" href="/en/"', client.get("/").data.decode())
    assert re.search(r'class="lang-switch" href="/"', client.get("/en/").data.decode())


def test_analytics_and_pixel_also_on_english_pages(client):
    _enable()
    html = client.get("/en/").data.decode()
    assert "G-RB896Z7ZBD" in html and "1365676268753546" in html


def test_links_stay_in_english_and_legal_pages_keep_their_address(client):
    _enable()
    html = client.get("/en/").data.decode()
    assert 'href="/en/#solution"' in html and 'href="/privacy.html"' in html


def _page(slug: str, *sections: dict) -> None:
    db.session.add(Page(slug=slug, title=slug, published_snapshot=[
        {"id": i, "block_type": "rich_text", "anchor": "", "is_visible": True, "position": i, "admin_label": "x", "content": c}
        for i, c in enumerate(sections)]))
    db.session.commit()


def test_page_without_english_is_404_and_has_no_button(client):
    _enable()
    _page("marsoud", {"ar": {"title": "نص لم يترجم", "body": "<p>نص</p>"}, "en": {}})
    assert client.get("/en/marsoud").status_code == 404
    assert b"lang-switch" not in client.get("/marsoud").data


def test_translated_extra_page_hides_untranslated_section(client):
    _enable()
    _page("marsoud", {"ar": {"title": "عنوان", "body": "<p>نص</p>"}, "en": {"title": "A title", "body": "<p>Body</p>"}},
          {"ar": {"title": "لم يترجم", "body": "<p>نص</p>"}, "en": {}})
    html = client.get("/en/marsoud").data.decode()
    assert "A title" in html and "لم يترجم" not in html
    assert 'class="lang-switch" href="/en/marsoud"' in client.get("/marsoud").data.decode()


def test_article_button_only_with_a_translation(client):
    _enable()
    ar = _publish_article("arabic-only")
    assert b"lang-switch" not in client.get("/blog/arabic-only").data
    en = _publish_article("in-english", lang="en", translation_of_id=ar.id)
    assert en.path == "/en/blog/in-english"
    assert 'class="lang-switch" href="/en/blog/in-english"' in client.get("/blog/arabic-only").data.decode()
    assert 'class="lang-switch" href="/blog/arabic-only"' in client.get("/en/blog/in-english").data.decode()


def test_english_lead_is_saved_with_english_errors(client):
    _enable()
    r = client.post("/api/leads", data={"name": "", "phone": "1", "lang": "en"}, headers={"Accept": "application/json"})
    assert r.status_code == 400 and "Name is required." in r.get_json()["errors"]
    r = client.post("/api/leads", data={"name": "Sam", "phone": "+966500000000", "school": "x", "lang": "en"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/en/thank-you")
    assert db.session.query(Lead).count() == 1
    assert "received successfully" in client.get("/en/thank-you").data.decode()


def test_form_on_english_page_posts_language_and_thanks_url(client):
    _enable()
    html = client.get("/en/").data.decode()
    assert 'name="lang" value="en"' in html and 'data-thanks="/en/thank-you"' in html


def test_fill_only_touches_empty_english_fields(client):
    section = db.session.query(Section).order_by(Section.position).limit(1).one()
    arabic = dict(section.content["ar"])
    section.content = {"ar": arabic, "en": {"title": "Edited by hand"}}
    feature = db.session.query(Feature).limit(1).one()
    feature.name_en = "Edited name"
    db.session.commit()
    fill_english()
    assert section.content["en"] == {"title": "Edited by hand"} and section.content["ar"] == arabic
    assert feature.name_en == "Edited name"


def test_section_with_untranslated_text_is_reported_then_filled_from_a_file(client):
    section = db.session.query(Section).order_by(Section.position).limit(1).one()
    section.content = {"ar": {"title": "نص جديد لم يترجم بعد", "cta_primary_href": "#contact"}, "en": {}}
    db.session.commit()
    result = fill_english()
    assert "نص جديد لم يترجم بعد" in result["missing"] and section.content["en"] == {}
    import_translations({"نص جديد لم يترجم بعد": "New text"})
    assert "نص جديد لم يترجم بعد" not in fill_english()["missing"]
    assert section.content["en"] == {"title": "New text", "cta_primary_href": "#contact"}


@pytest.mark.parametrize("path", ["/en/faq", "/en/files", "/en/blog", "/en/thank-you"])
def test_english_pages_render(client, path):
    _enable()
    assert client.get(path).status_code == 200


def test_faq_page_in_english(client):
    _enable()
    assert "What is the difference between Manasety School" in client.get("/en/faq").data.decode()


def test_hidden_english_404_does_not_show_the_english_site(client):
    r = client.get("/en/nope")
    html = r.data.decode()
    assert r.status_code == 404 and '<html lang="ar"' in html and "Unpublished English version" not in html


def test_header_button_stays_on_the_english_form(client):
    _enable()
    assert re.search(r'class="btn btn-primary btn-sm" href="/en/#contact"', client.get("/en/").data.decode())


def test_links_keep_their_query_and_section(client):
    _enable()
    with client.application.test_request_context("/en/"):
        from manasety.i18n import lhref
        assert lhref("/?utm_source=x#contact") == "/en/?utm_source=x#contact"
        assert lhref("/no-english?utm_source=x") == "/no-english?utm_source=x"


def test_business_blog_in_english(client):
    _enable()
    ar = _publish_article("biz-ar", audience="business")
    _publish_article("biz-en", lang="en", translation_of_id=ar.id, audience="business")
    assert 'class="lang-switch" href="/en/business/blog"' in client.get("/business/blog").data.decode()
    html = client.get("/en/business/blog").data.decode()
    assert "/en/blog/biz-en" in html and 'class="lang-switch" href="/business/blog"' in html


def test_sitemap_lists_only_english_pages_that_open(client):
    _enable()
    _page("marsoud", {"ar": {"title": "لم يترجم"}, "en": {}})
    _page("qdrat", {"ar": {"title": "عنوان"}, "en": {"title": "A title"}})
    xml = client.get("/sitemap.xml").data.decode()
    assert "/en/qdrat" in xml and "/en/marsoud" not in xml and "https://manasety.ai/en/<" in xml
    set_setting("english_enabled", False)
    db.session.commit()
    assert "/en/" not in client.get("/sitemap.xml").data.decode()


def test_export_changes_nothing(client):
    section = db.session.query(Section).order_by(Section.position).limit(1).one()
    section.content = {"ar": section.content["ar"], "en": {}}
    db.session.commit()
    assert fill_english(dry_run=True)["filled"] > 0
    db.session.refresh(section)
    assert section.content["en"] == {}


def test_filled_counts_published_snapshots(client):
    db.session.add(Page(slug="snap", title="snap", published_snapshot=[{
        "id": 1, "block_type": "rich_text", "anchor": "", "is_visible": True, "position": 0, "admin_label": "x",
        "content": {"ar": {"title": "لم يترجم"}, "en": {}}}]))
    db.session.commit()
    import_translations({"لم يترجم": "Translated"})
    assert fill_english()["filled"] == 1


def test_reseeding_does_not_bring_back_removed_english(client):
    section = db.session.query(Section).order_by(Section.position).limit(1).one()
    section.content = {"ar": section.content["ar"], "en": {}}
    db.session.commit()
    seed_module.seed_all()
    db.session.refresh(section)
    assert section.content["en"] == {}


def test_imported_translation_corrects_a_built_in_label(client):
    _enable()
    import_translations({"الرئيسية": "Main page"})
    with client.application.test_request_context("/en/"):
        assert t("الرئيسية") == "Main page"


def test_untranslated_description_stays_hidden_in_english(client):
    _enable()
    with client.application.test_request_context("/en/"):
        assert t_or_empty("وصف لم يترجم") == ""
    with client.application.test_request_context("/"):
        assert t_or_empty("وصف لم يترجم") == "وصف لم يترجم"


@pytest.mark.parametrize("path, arabic, english", [
    ("about", "من نحن", "About us"), ("contact", "تواصل معنا", "Contact us")])
def test_about_and_contact_in_both_languages(client, path, arabic, english):
    _enable()
    ar = client.get(f"/{path}").data.decode()
    en = client.get(f"/en/{path}").data.decode()
    assert '<html lang="ar"' in ar and f"<title>{arabic} | منصتي" in ar and f'class="lang-switch" href="/en/{path}"' in ar
    assert '<html lang="en"' in en and f"<title>{english} | منصتي - Manasety" in en and f'class="lang-switch" href="/{path}"' in en
    assert not AR_RE.search(_visible_text(en).replace("العربية", ""))
    assert en.count("<h1") == 1 and ar.count("<h1") == 1
    assert f'href="/{path}"' in client.get("/").data.decode() and f'href="/en/{path}"' in client.get("/en/").data.decode()


def test_about_and_contact_stay_arabic_only_until_english_is_on(client):
    assert client.get("/about").status_code == 200 and client.get("/contact").status_code == 200
    assert client.get("/en/about").status_code == 404 and client.get("/en/contact").status_code == 404


def test_contact_page_shows_current_settings_and_saves_a_contact_lead(client):
    _enable()
    set_setting("email", "new@manasety.ai")
    db.session.commit()
    en = client.get("/en/contact").data.decode()
    assert "new@manasety.ai" in en and 'name="form" value="contact"' in en and 'data-thanks="/en/thank-you"' in en
    r = client.post("/api/leads", data={"form": "contact", "name": "Sam", "phone": "+966500000000", "message": "Hi",
                                        "lang": "en", "source": "contact_page"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/en/thank-you")
    lead = db.session.query(Lead).one()
    assert lead.form == "contact" and lead.source == "contact_page"


def test_seed_keeps_an_edited_about_page_and_does_not_repeat_footer_links(client):
    page = db.session.query(Page).filter_by(slug="about").one()
    page.title = "Edited"
    db.session.commit()
    seed_module.seed_all()
    assert db.session.query(Page).filter_by(slug="about").one().title == "Edited"
    assert sum(item["href"] == "/about" for item in get_setting("extra_pages")) == 1


def test_root_files_are_not_swallowed_by_the_page_route(client):
    assert client.get("/indexold23-09-2026.html").status_code == 200
    assert client.get("/no-such-page").status_code == 404
