"""Roles, 2FA, audit log, page builder, display files, integrations registry, slugs."""
import io

from manasety.extensions import db
from manasety.models import AuditLog, DisplayFile, Integration, Lead, Page, Section
from manasety.services.seo import slugify
from tests.conftest import login, make_user


def test_admin_requires_login(client):
    r = client.get("/admin/")
    assert r.status_code == 302 and "/admin/login" in r.headers["Location"]


def test_admin_without_2fa_cannot_enter(client):
    user, _ = make_user("admin", with_2fa=False)
    login(client, user, None)
    r = client.get("/admin/settings")
    assert r.status_code == 302 and "/admin/2fa/setup" in r.headers["Location"]


def test_sales_sees_leads_but_not_settings(client):
    user, _ = make_user("sales", with_2fa=False)  # 2FA optional for Sales
    login(client, user, None)
    assert client.get("/admin/leads/").status_code == 200
    assert client.get("/admin/settings").status_code == 403
    assert client.get("/admin/pages/").status_code == 403


def test_marketer_cannot_edit_settings_or_delete_integrations(client):
    user, _ = make_user("marketer", with_2fa=False)
    login(client, user, None)
    assert client.get("/admin/settings").status_code == 403
    integ = db.session.query(Integration).filter_by(name="Meta Pixel").one()
    r = client.post(f"/admin/lib/integrations/{integ.id}/delete", data={"confirm_name": "Meta Pixel"})
    assert r.status_code == 403


def test_integration_delete_requires_typed_name_and_is_logged(admin_client):
    integ = db.session.query(Integration).filter_by(name="Meta Pixel").one()
    admin_client.post(f"/admin/lib/integrations/{integ.id}/delete", data={"confirm_name": "wrong"})
    assert db.session.get(Integration, integ.id) is not None
    admin_client.post(f"/admin/lib/integrations/{integ.id}/delete", data={"confirm_name": "Meta Pixel"})
    assert db.session.get(Integration, integ.id) is None
    assert db.session.query(AuditLog).filter_by(action="delete", entity_type="integrations").count() == 1


def test_marketer_cannot_change_injected_code(client):
    user, _ = make_user("marketer", with_2fa=False)
    login(client, user, None)
    integ = db.session.query(Integration).filter_by(name="Google Analytics 4").one()
    original = integ.code
    client.post(f"/admin/lib/integrations/{integ.id}", data={
        "name": integ.name, "kind": "script", "placement": "head", "page_scope": "*", "is_active": "on",
        "code": "<script>steal()</script>", "notes": "checked"})
    db.session.expire_all()
    integ = db.session.query(Integration).filter_by(id=integ.id).one()
    assert integ.code == original and integ.notes == "checked"


def test_integration_rejects_secrets(admin_client):
    r = admin_client.post("/admin/lib/integrations/new", data={
        "name": "bad", "kind": "script", "placement": "head", "page_scope": "*",
        "code": "<script>var api_key='abc123'</script>", "is_active": "on"})
    assert r.status_code == 200 and "مفتاح" in r.data.decode()
    assert db.session.query(Integration).filter_by(name="bad").count() == 0


def test_edit_section_publish_changes_public_page_and_logs_before_after(admin_client, client):
    page = db.session.query(Page).filter_by(slug="home").one()
    hero = next(s for s in page.sections if s.block_type == "hero")
    form = {f"ar__{k}": v for k, v in hero.content["ar"].items() if isinstance(v, str)}
    form.update({"lang": "ar", "admin_label": "Hero", "anchor": "top", "ar__title": "عنوان جديد للتجربة"})
    admin_client.post(f"/admin/pages/home/sections/{hero.id}", data=form)
    assert "عنوان جديد للتجربة" not in admin_client.get("/").data.decode()   # draft only
    admin_client.post("/admin/pages/home/publish")
    assert "عنوان جديد للتجربة" in admin_client.get("/").data.decode()
    log = db.session.query(AuditLog).filter_by(entity_type="section", action="update").limit(1).one()
    assert log.before and log.after and log.before != log.after


def test_section_xss_is_stripped(admin_client):
    page = db.session.query(Page).filter_by(slug="home").one()
    hero = next(s for s in page.sections if s.block_type == "hero")
    admin_client.post(f"/admin/pages/home/sections/{hero.id}", data={
        "lang": "ar", "ar__title": "<script>alert(1)</script>عنوان", "ar__subtitle": '<img src=x onerror=alert(1)>'})
    admin_client.post("/admin/pages/home/publish")
    html = admin_client.get("/").data.decode()
    assert "<script>alert(1)" not in html and "onerror=alert" not in html


def test_revision_restore_brings_back_old_version(admin_client):
    page = db.session.query(Page).filter_by(slug="home").one()
    first_rev = page.id
    from manasety.models import Revision
    rev = db.session.query(Revision).filter_by(entity_type="page").order_by(Revision.id).limit(1).one()
    sec = page.sections[0]
    db.session.delete(sec)
    db.session.commit()
    admin_client.post(f"/admin/pages/home/revisions/{rev.id}/restore")
    db.session.expire_all()
    assert len(db.session.query(Page).filter_by(id=first_rev).one().sections) == 13


def test_display_file_hide_keeps_direct_link(admin_client, app):
    pdf = b"%PDF-1.4 test"
    r = admin_client.post("/admin/files/new", data={
        "display_name": "الملف التعريفي", "public_path": "manasety-profile.pdf", "placements": ["footer"],
        "is_visible": "on", "direct_link_enabled": "on", "file": (io.BytesIO(pdf), "p.pdf")},
        content_type="multipart/form-data")
    assert r.status_code == 302
    f = db.session.query(DisplayFile).one()
    assert "الملف التعريفي" in admin_client.get("/").data.decode()
    admin_client.post(f"/admin/files/{f.id}", data={"display_name": "معرض أعمالنا", "placements": ["footer"],
                                                     "direct_link_enabled": "on"})  # hidden + renamed, no re-upload
    html = admin_client.get("/").data.decode()
    assert "معرض أعمالنا" not in html and "الملف التعريفي" not in html
    assert admin_client.get("/manasety-profile.pdf").data == pdf          # direct link still works
    admin_client.post(f"/admin/files/{f.id}", data={"display_name": "x", "direct_link_enabled": "on",
                                                     "file": (io.BytesIO(b"%PDF-1.4 v2"), "p.pdf")},
                      content_type="multipart/form-data")
    assert admin_client.get("/manasety-profile.pdf").data == b"%PDF-1.4 v2"  # replaced, same URL


def test_lead_export_csv_neutralises_formulas(admin_client):
    db.session.add(Lead(name="=HYPERLINK(\"x\")", phone="0100", status="new"))
    db.session.commit()
    body = admin_client.get("/admin/leads/export.csv").data.decode("utf-8-sig")
    assert "'=HYPERLINK" in body


def test_media_upload_requires_alt_and_converts_to_webp(admin_client):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, "PNG")
    png = buf.getvalue()
    admin_client.post("/admin/media/", data={"file": (io.BytesIO(png), "a.png"), "alt": "", "demo_checked": "on"},
                      content_type="multipart/form-data")
    from manasety.models import Media
    assert db.session.query(Media).count() == 0
    admin_client.post("/admin/media/", data={"file": (io.BytesIO(png), "a.png"), "alt": "لقطة", "demo_checked": "on"},
                      content_type="multipart/form-data")
    m = db.session.query(Media).one()
    assert m.mime == "image/webp" and m.filename.endswith(".webp")


def test_slugify_arabic_to_short_latin():
    s = slugify("كيف تختار نظام إدارة مدرسة؟")
    assert s.isascii() and 0 < len(s) <= 80 and " " not in s


def test_all_admin_pages_render(admin_client):
    for path in ("/admin/", "/admin/pages/", "/admin/pages/home/seo", "/admin/pages/home/revisions", "/admin/settings",
                 "/admin/users", "/admin/audit", "/admin/backups", "/admin/media/", "/admin/files/", "/admin/files/new",
                 "/admin/legal/", "/admin/articles/", "/admin/articles/new", "/admin/leads/", "/admin/seo/",
                 "/admin/seo/search-console", "/admin/account"):
        assert admin_client.get(path).status_code == 200, path
    from manasety.admin.crud import RESOURCES
    for name in RESOURCES:
        assert admin_client.get(f"/admin/lib/{name}").status_code == 200, name
        assert admin_client.get(f"/admin/lib/{name}/new").status_code == 200, name
    for sec in db.session.query(Section).all():
        assert admin_client.get(f"/admin/pages/home?s={sec.id}").status_code == 200, sec.block_type
