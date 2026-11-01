"""Ticket: a dashboard user linked to an author gets that author pre-filled on new articles."""
import re

from manasety.extensions import db
from manasety.models import Article, Author, User
from tests.conftest import login, make_user


def _author(slug: str = "shalaby") -> Author:
    a = Author(name="عبدالحميد شلبي", slug=slug, job_title="", bio="", same_as=[])
    db.session.add(a)
    db.session.commit()
    return a


def _selected_author(html: str) -> str | None:
    select = re.search(r'<select id="author" name="author_id">(.*?)</select>', html, re.S)
    assert select
    m = re.search(r'<option value="(\d+)" selected>', select.group(1))
    return m.group(1) if m else None


def test_linked_user_gets_author_prefilled_and_can_change_it(client):
    author = _author()
    other = _author("other")
    user, secret = make_user("marketer")
    user.author_id = author.id
    db.session.commit()
    login(client, user, secret)
    assert _selected_author(client.get("/admin/articles/new").data.decode()) == str(author.id)
    # the field stays editable: whatever the form sends is saved
    client.post("/admin/articles/new", data={"title": "مقال", "author_id": str(other.id), "status": "draft"})
    assert db.session.query(Article).filter_by(title="مقال").one().author_id == other.id


def test_unlinked_user_keeps_empty_author(client):
    user, secret = make_user("marketer")
    login(client, user, secret)
    assert _selected_author(client.get("/admin/articles/new").data.decode()) is None


def test_existing_articles_keep_their_author(client):
    author = _author()
    user, secret = make_user("marketer")
    user.author_id = author.id
    art = Article(slug="old", title="قديم", content_html="<p>x</p>", status="draft", author_id=None)
    db.session.add(art)
    db.session.commit()
    login(client, user, secret)
    assert _selected_author(client.get(f"/admin/articles/{art.id}").data.decode()) is None


def test_admin_links_author_on_create_and_update(admin_client):
    author = _author()
    admin_client.post("/admin/users", data={"name": "محرر", "email": "new@manasety.ai", "role": "editor", "author_id": str(author.id)})
    u = db.session.query(User).filter_by(email="new@manasety.ai").one()
    assert u.author_id == author.id
    admin_client.post(f"/admin/users/{u.id}", data={"action": "author", "author_id": ""})
    assert u.author_id is None
    admin_client.post(f"/admin/users/{u.id}", data={"action": "author", "author_id": "99999"})  # unknown author → none
    assert u.author_id is None
    assert "الكاتب المرتبط" in admin_client.get("/admin/users").data.decode()


def test_bad_or_stale_author_ids_never_500(admin_client):
    author = _author()
    u = db.session.query(User).first()
    assert u is not None
    for raw in ("²", "٣", "-1", "1e3"):
        r = admin_client.post(f"/admin/users/{u.id}", data={"action": "author", "author_id": raw})
        assert r.status_code == 302
        assert u.author_id is None
    # an article saved with a deleted author id gets no author instead of an FK error
    admin_client.post("/admin/articles/new", data={"title": "مقال قديم", "author_id": "99999", "status": "draft"})
    assert db.session.query(Article).filter_by(title="مقال قديم").one().author_id is None
    # deleting an author clears the users linked to it
    u.author_id = author.id
    db.session.commit()
    admin_client.post(f"/admin/lib/authors/{author.id}/delete")
    db.session.refresh(u)
    assert u.author_id is None
