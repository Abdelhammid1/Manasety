"""Manasety landing page + dashboard (one Flask app, one PostgreSQL DB)."""
from __future__ import annotations

import base64
import hmac
import re
import time
from pathlib import Path

from flask import Flask, Response, g, redirect, request, send_from_directory
from flask_login import current_user

from .config import Config
from .extensions import csrf, db, limiter, login_manager, migrate


def create_app(config: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config)
    if app.config.get("TRUST_PROXY"):
        # One reverse proxy (host Nginx): real client IP for rate limits/audit, https scheme for URLs.
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(Path(__file__).resolve().parent.parent / "migrations"))
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "admin_auth.login"  # type: ignore[assignment]
    login_manager.login_message = "سجّل الدخول أولًا."

    from . import models  # noqa: F401  (register tables)

    @login_manager.user_loader
    def load_user(token: str):
        from .models import User
        try:
            uid, version = (int(x) for x in token.split(":", 1))
        except ValueError:
            return None
        user = db.session.get(User, uid)
        return user if user and user.session_version == version else None

    from .admin import register_admin
    from .public.routes import bp as public_bp
    from .template_utils import register_template_utils

    app.register_blueprint(public_bp)
    register_admin(app)
    register_template_utils(app)
    _register_hooks(app)

    from .cli import register_cli
    register_cli(app)

    if not app.testing:
        for key in ("MARSOUD_CONTACT_TOKEN", "WEB3FORMS_ACCESS_KEY"):
            if not app.config.get(key):
                app.logger.warning("%s is not set: leads will NOT be forwarded to that integration.", key)

    @app.route("/media/<path:filename>")
    def media(filename: str):
        from flask import abort
        from .models import Client, Media
        # Public media are flat generated names ("<hex>.webp"). Anything with a folder, "..", or odd
        # characters is refused, which also covers "./private/x" or "a/../private/x" tricks.
        if not re.fullmatch(r"[A-Za-z0-9_\-]+\.[A-Za-z0-9]{2,5}", filename):
            abort(404)
        # Consent proofs (WhatsApp screenshots etc.) are evidence, never public.
        proof = (db.session.query(Media.id).join(Client, Client.consent_proof_id == Media.id)
                 .filter(Media.filename == filename).first())
        if proof is not None:
            abort(404)
        import mimetypes
        for _ext, _mt in ((".webp", "image/webp"), (".svg", "image/svg+xml"), (".avif", "image/avif")):
            mimetypes.add_type(_mt, _ext)
        resp = send_from_directory(app.config["MEDIA_DIR"], filename, max_age=60 * 60 * 24 * 30,
                                   mimetype=mimetypes.guess_type(filename)[0] or None)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    return app


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def staging_gate():
        """Staging runs behind basic auth so it can't leak before launch (spec: deploy step 2)."""
        if not app.config.get("STAGING") or request.path.startswith("/static/"):
            return None
        user, pwd = app.config.get("STAGING_USER"), app.config.get("STAGING_PASSWORD")
        if not (user and pwd):
            return None
        header = request.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                u, _, p = base64.b64decode(header[6:]).decode().partition(":")
                if hmac.compare_digest(u, user) and hmac.compare_digest(p, pwd):
                    return None
            except Exception:
                pass
        return Response("Staging", 401, {"WWW-Authenticate": 'Basic realm="staging"'})

    @app.before_request
    def legacy_redirects():
        if request.method not in ("GET", "HEAD") or request.path.startswith(("/admin", "/static/", "/media/", "/api/")):
            return None  # never redirect form posts (a 307/308 would forward their bodies)
        from .models import Redirect
        row = db.session.query(Redirect).filter_by(from_path=request.path).first()
        if row is None:
            return None
        row.hits += 1
        db.session.commit()
        return redirect(row.to_path, code=row.code)

    @app.before_request
    def scheduled_publishing():
        # Cheap lazy check at most once a minute per worker; `flask publish-scheduled` covers idle times.
        if request.path.startswith(("/static/", "/media/")):
            return None
        last = app.config.get("_last_schedule_check", 0)
        if time.time() - last > 60:
            app.config["_last_schedule_check"] = time.time()
            from .publishing import apply_scheduled
            apply_scheduled()
        return None

    @app.after_request
    def security_headers(resp: Response):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        if app.config.get("STAGING"):
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        if request.path.startswith("/admin"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @app.context_processor
    def inject_user():
        return {"current_user": current_user, "g": g}
