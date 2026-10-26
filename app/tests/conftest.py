import pyotp
import pytest

from manasety import create_app
from manasety.config import TestConfig
from manasety.extensions import db as _db
from manasety.models import User
from manasety.seed import seed_all


@pytest.fixture()
def app(tmp_path):
    class Cfg(TestConfig):
        MEDIA_DIR = tmp_path / "media"
        BACKUP_STATUS_FILE = str(tmp_path / "backup.json")

    app = create_app(Cfg)
    with app.app_context():
        _db.create_all()
        seed_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(role: str, email: str | None = None, with_2fa: bool = True) -> tuple[User, str]:
    user = User(email=email or f"{role}@test.local", name=role, role=role)
    user.set_password("correct-horse-battery")
    secret = pyotp.random_base32()
    if with_2fa:
        user.totp_secret, user.totp_enabled = secret, True
    _db.session.add(user)
    _db.session.commit()
    return user, secret


def login(client, user: User, secret: str | None) -> None:
    r = client.post("/admin/login", data={"email": user.email, "password": "correct-horse-battery"})
    if secret and user.totp_enabled:
        assert r.status_code == 302 and "/admin/2fa" in r.headers["Location"]
        r = client.post("/admin/2fa", data={"code": pyotp.TOTP(secret).now()})
    assert r.status_code == 302


@pytest.fixture()
def admin_client(client):
    user, secret = make_user("admin")
    login(client, user, secret)
    return client
