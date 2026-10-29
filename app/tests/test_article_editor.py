"""Article editor ticket: tables, headings, lists, sanitiser whitelist, autosave, display-time cleaning."""
from manasety.extensions import db
from manasety.models import Article, Revision
from manasety.security import clean_rich
from manasety.services.seo import article_checks, bold_line_count
from tests.test_public import _publish_article

TABLE = ("<table><thead><tr><th scope=\"col\">المرحلة</th><th>عدد الطلاب</th></tr></thead>"
         "<tbody><tr><td colspan=\"2\">الابتدائي</td></tr></tbody></table>")


def test_tables_headings_and_nested_lists_survive_cleaning():
    html = f"<h2>أ</h2><h3>ب</h3><h4>ج</h4>{TABLE}<ul><li>واحد<ul><li>فرعي</li></ul></li></ul>"
    assert clean_rich(html) == html.replace("<a ", "<a ")


def test_unsafe_markup_is_stripped():
    dirty = ('<p style="color:red" onclick="x()">نص</p><script>alert(1)</script><img src="x" onerror="alert(1)">'
             '<a href="javascript:alert(1)">رابط</a><table onmouseover="x()" style="width:9px"><tr><td style="color:red">1</td></tr></table>'
             '<span class="MsoNormal" style="font-family:Arial">كلمة</span><!--[if gte mso 9]><xml></xml><![endif]-->')
    out = clean_rich(dirty)
    for bad in ("<script", "onclick", "onerror", "onmouseover", "javascript:", "style=", "Mso", "<!--", "alert(1)</"):
        assert bad not in out, bad
    assert "<table><tbody><tr><td>1</td></tr></tbody></table>" in out


def test_only_the_checklist_class_is_allowed():
    assert clean_rich('<ul class="checklist evil"><li>☐ مهمة</li></ul>') == '<ul class="checklist"><li>☐ مهمة</li></ul>'
    assert clean_rich('<ul class="evil"><li>x</li></ul>') == "<ul><li>x</li></ul>"
    assert clean_rich('<ol class="checklist"><li>x</li></ol>') == "<ol><li>x</li></ol>"


def test_typed_bullets_inside_list_items_are_removed():
    assert clean_rich("<ul><li>• أولًا</li><li>- ثانيًا</li><li>-5 درجات</li></ul>") == \
        "<ul><li>أولًا</li><li>ثانيًا</li><li>-5 درجات</li></ul>"


def test_bold_lines_are_flagged_and_h2_is_recognised():
    art = Article(title="t", content_html="<p><strong>مقدمة المقال</strong></p><p>نص <b>غامق</b> عادي</p>")
    assert bold_line_count(art.content_html) == 1
    labels = {c["label"]: c["ok"] for c in article_checks(art)}
    assert labels["يحتوي عناوين H2"] is False
    assert any("سطر غامق" in label and not ok for label, ok in labels.items())
    art.content_html = "<h2>مقدمة المقال</h2><p>نص</p>"
    labels = {c["label"]: c["ok"] for c in article_checks(art)}
    assert labels["يحتوي عناوين H2"] and labels["لا توجد سطور غامقة مكان العناوين"]


def test_article_page_wraps_tables_and_recleans_on_display(client):
    art = _publish_article("tables-article")
    # simulate content stored before this change / written straight to the DB
    art.content_html = f"<h2>مقدمة</h2>{TABLE}<p onclick=\"x()\">نص</p><script>alert(1)</script>"
    db.session.commit()
    html = client.get("/blog/tables-article").data.decode()
    assert '<div class="table-wrap"><table>' in html and "</table></div>" in html
    assert "onclick" not in html and "<script>alert(1)" not in html


def test_old_article_renders_unchanged(client):
    old = '<h2>مقدمة</h2><p>فقرة <strong>مهمة</strong> و<a href="/blog/x">رابط</a>.</p><ul><li>بند</li></ul><blockquote>اقتباس</blockquote>'
    art = _publish_article("old-article")
    art.content_html = old
    db.session.commit()
    html = client.get("/blog/old-article").data.decode()
    assert '<p>فقرة <strong>مهمة</strong> و<a href="/blog/x" rel="noopener">رابط</a>.</p><ul><li>بند</li></ul><blockquote>اقتباس</blockquote>' in html


def test_autosave_keeps_live_article_untouched_and_offers_restore(admin_client):
    art = _publish_article("autosave-article")
    live = art.content_html
    r = admin_client.post(f"/admin/articles/{art.id}/autosave", data={
        "title": art.title, "content_html": "<h2>جديد</h2><p>مسودة</p><script>alert(1)</script>", "focus_keyword": ""})
    assert r.status_code == 200 and "checks" in r.get_json()
    db.session.expire_all()
    assert db.session.query(Article).filter_by(id=art.id).one().content_html == live
    slot = db.session.query(Revision).filter_by(entity_type="article_autosave", entity_id=art.id).one()
    assert "<script" not in slot.snapshot["content_html"]
    page = admin_client.get(f"/admin/articles/{art.id}").data.decode()
    assert 'id="autosave-draft"' in page
    # the normal revisions list never shows the autosave slot
    assert db.session.query(Revision).filter_by(entity_type="article", entity_id=art.id).count() == 0


def test_autosave_matching_saved_content_clears_the_slot(admin_client):
    art = _publish_article("autosave-same")
    admin_client.post(f"/admin/articles/{art.id}/autosave", data={"title": art.title, "content_html": "<p>تغيير</p>"})
    admin_client.post(f"/admin/articles/{art.id}/autosave", data={"title": art.title, "content_html": art.content_html})
    assert db.session.query(Revision).filter_by(entity_type="article_autosave").count() == 0


def test_autosave_requires_login(client):
    art = _publish_article("autosave-anon")
    assert client.post(f"/admin/articles/{art.id}/autosave", data={"content_html": "<p>x</p>"}).status_code in (302, 401)


def test_table_wrap_cannot_break_out_of_an_attribute(client):
    """A "<table" inside an attribute value must not become a real tag after the display-time wrap."""
    art = _publish_article("attr-breakout")
    art.content_html = clean_rich('<p><a href="/x" title="<table onmouseover=alert(1) x">رابط</a></p>')
    db.session.commit()
    html = client.get("/blog/attr-breakout").data.decode()
    assert "onmouseover" not in html


def test_rich_text_keeps_only_whitelisted_classes_and_legal_pages_keep_theirs():
    from manasety.security import clean_legal
    assert clean_rich('<div class="table-wrap x"><table><tr><td>1</td></tr></table></div><div class="hero">y</div>') == \
        '<div class="table-wrap"><table><tbody><tr><td>1</td></tr></tbody></table></div><div>y</div>'
    assert clean_legal('<ul class="legal-list"><li>x</li></ul>') == '<ul class="legal-list"><li>x</li></ul>'


def test_wrap_tables_does_not_double_wrap_and_handles_nesting():
    from manasety.services.seo import wrap_tables
    once = wrap_tables("<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>")
    assert once.count('<div class="table-wrap">') == 2 and once.count("</div>") == 2
    assert wrap_tables('<div class="table-wrap"><table></table></div>') == '<div class="table-wrap"><table></table></div>'


def test_bold_line_rule_matches_the_editor():
    assert bold_line_count("<p><strong>عنوان </strong><strong>جزء</strong></p>") == 1
    assert bold_line_count("<p><strong>عنوان <em>مائل</em></strong></p>") == 1
    assert bold_line_count("<p><strong>غامق</strong> ثم نص عادي</p>") == 0


def test_stale_autosave_is_refused_and_delete_drops_the_draft(admin_client):
    art = _publish_article("stale-autosave")
    r = admin_client.post(f"/admin/articles/{art.id}/autosave",
                          data={"title": art.title, "content_html": "<p>قديم</p>", "base": "2000-01-01T00:00:00"})
    assert r.status_code == 409
    assert db.session.query(Revision).filter_by(entity_type="article_autosave").count() == 0
    base = art.updated_at.isoformat()
    r = admin_client.post(f"/admin/articles/{art.id}/autosave", data={"title": art.title, "content_html": "<p>جديد</p>", "base": base})
    assert r.get_json()["saved_at"]
    art.status = "draft"
    db.session.commit()
    admin_client.post(f"/admin/articles/{art.id}/delete")
    assert db.session.query(Revision).filter_by(entity_type="article_autosave").count() == 0


def test_autosave_without_changes_reports_no_draft(admin_client):
    art = _publish_article("no-changes")
    r = admin_client.post(f"/admin/articles/{art.id}/autosave", data={"title": art.title, "content_html": art.content_html})
    assert r.get_json()["saved_at"] is None
