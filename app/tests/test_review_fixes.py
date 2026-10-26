"""Regression tests for the /code-review findings."""
import io
from datetime import date, timedelta
from types import SimpleNamespace

from manasety.extensions import db
from manasety.models import Backlink, Client, DisplayFile, Lead, Media, Page, Tag, utcnow
from manasety.publishing import apply_scheduled, schedule_page
from manasety.services import linkcheck


def _upload_profile(admin_client, data=b"%PDF-1.4 v1"):
    return admin_client.post("/admin/files/new", data={
        "display_name": "الملف التعريفي", "public_path": "manasety-profile.pdf", "placements": ["footer"],
        "is_visible": "on", "direct_link_enabled": "on", "file": (io.BytesIO(data), "p.pdf")},
        content_type="multipart/form-data")


def test_disabled_direct_link_is_not_reachable_through_media(admin_client):
    _upload_profile(admin_client)
    f = db.session.query(DisplayFile).one()
    assert f.stored_filename.startswith("private/")
    admin_client.post(f"/admin/files/{f.id}", data={"display_name": "x", "confirm_disable": "on"})
    assert admin_client.get("/manasety-profile.pdf").status_code == 404
    assert admin_client.get(f"/media/{f.stored_filename}").status_code == 404
    name = f.stored_filename.split("/")[-1]
    for trick in (f"./private/{name}", f"x/../private/{name}", f"private//{name}", f"%2e/private/{name}"):
        assert admin_client.get(f"/media/{trick}").status_code == 404, trick


def test_consent_proof_is_never_public(admin_client, app):
    proof = Media(filename="proof.webp", original_name="p", mime="image/webp", kind="image", size=4, alt="proof")
    db.session.add(proof)
    db.session.flush()
    (app.config["MEDIA_DIR"]).mkdir(parents=True, exist_ok=True)
    (app.config["MEDIA_DIR"] / "proof.webp").write_bytes(b"RIFF")
    client = db.session.query(Client).limit(1).one()
    client.consent_proof_id = proof.id
    db.session.commit()
    assert admin_client.get("/media/proof.webp").status_code == 404
    assert admin_client.get(f"/admin/media/{proof.id}/file").status_code == 200


def test_rejected_file_save_does_not_touch_live_pdf(admin_client):
    _upload_profile(admin_client)
    f = db.session.query(DisplayFile).one()
    admin_client.post(f"/admin/files/{f.id}", data={"display_name": "", "direct_link_enabled": "on",
                                                     "file": (io.BytesIO(b"%PDF-1.4 v2"), "p.pdf")},
                      content_type="multipart/form-data")
    assert admin_client.get("/manasety-profile.pdf").data == b"%PDF-1.4 v1"


def test_lead_accepted_without_csrf_token_when_csrf_enabled(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    r = client.post("/api/leads", data={"name": "زائر", "phone": "+201000000000", "school": "x"},
                    headers={"Accept": "application/json"})
    assert r.status_code == 200 and db.session.query(Lead).count() == 1


def test_malformed_json_lead_is_400_not_500(client):
    assert client.post("/api/leads", json=[1]).status_code == 400
    r = client.post("/api/leads", json={"name": 123, "phone": 5, "website": 1})
    assert r.status_code == 400


def test_non_numeric_page_param_is_not_500(client):
    assert client.get("/blog?page=abc").status_code in (200, 404)


def test_duplicate_slug_gets_suffix_not_500(admin_client):
    for _ in range(2):
        r = admin_client.post("/admin/lib/tags/new", data={"name": "ذكاء"})
        assert r.status_code in (200, 302)
    slugs = [t.slug for t in db.session.query(Tag).all()]
    assert len(slugs) == len(set(slugs)) == 2


def test_duplicate_redirect_is_validation_error(admin_client):
    data = {"from_path": "/old", "to_path": "/new", "code": "301"}
    admin_client.post("/admin/lib/redirects/new", data=data)
    r = admin_client.post("/admin/lib/redirects/new", data=data)
    assert r.status_code == 200 and "مكررة" in r.data.decode()


def test_schedule_freezes_seo(client):
    page = db.session.query(Page).filter_by(slug="home").one()
    page.seo = {"ar": {"title": "A"}}
    schedule_page(page, utcnow() - timedelta(seconds=1))
    page.seo = {"ar": {"title": "B (draft for later)"}}
    db.session.commit()
    apply_scheduled()
    assert page.published_seo["ar"]["title"] == "A"


def test_backlink_check_pairs_rel_with_the_right_tag(monkeypatch):
    html = '<a name="top">x</a><a href="https://manasety.ai/" rel="nofollow">m</a><a href="https://manasety.ai.evil.com">e</a>'
    monkeypatch.setattr(linkcheck, "safe_request", lambda *a, **k: SimpleNamespace(ok=True, text=html, status_code=200))
    link = Backlink(source_url="https://example.com", target_url="https://manasety.ai/", status="published")
    linkcheck.check_backlink(link)
    assert link.rel == "nofollow" and link.status == "published"
    monkeypatch.setattr(linkcheck, "safe_request",
                        lambda *a, **k: SimpleNamespace(ok=True, text='<a href="https://manasety.ai.evil.com">e</a>', status_code=200))
    linkcheck.check_backlink(link)
    assert link.status == "lost"


def test_media_in_published_page_cannot_be_deleted(admin_client):
    m = Media(filename="hero.webp", original_name="h", mime="image/webp", kind="image", size=1, alt="hero")
    db.session.add(m)
    db.session.flush()
    page = db.session.query(Page).filter_by(slug="home").one()
    snap = [dict(s) for s in page.published_snapshot or []]
    snap[0] = {**snap[0], "content": {"ar": {**snap[0]["content"]["ar"], "image": m.id}}}
    page.published_snapshot = snap
    db.session.commit()
    admin_client.post(f"/admin/media/{m.id}/delete")
    assert db.session.get(Media, m.id) is not None
    _ = date.today()
