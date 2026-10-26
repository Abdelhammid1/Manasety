"""Login, TOTP 2FA (enrolment, verification, backup codes), logout, own password."""
from __future__ import annotations

import io
from urllib.parse import urlsplit

import pyotp
import qrcode
import qrcode.image.svg
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup

from ..extensions import db, limiter
from ..models import User, utcnow
from ..security import audit

bp = Blueprint("admin_auth", __name__, url_prefix="/admin")


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/admin") and not urlsplit(target).netloc:
        return target
    return url_for("admin_core.dashboard")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
def login():
    if current_user.is_authenticated and (session.get("2fa_ok") or not current_user.totp_enabled):
        return redirect(url_for("admin_core.dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = db.session.query(User).filter_by(email=email).first()
        if user is None or not user.is_active or not user.check_password(request.form.get("password") or ""):
            audit("login_failed", "user", None, summary=email[:200])
            db.session.commit()
            flash("البريد أو كلمة المرور غير صحيحة.", "error")
            return render_template("admin/login.html"), 401
        session.clear()
        if user.totp_enabled:
            session["pending_uid"] = user.id
            session["pending_next"] = request.args.get("next")
            return redirect(url_for("admin_auth.verify"))
        login_user(user)
        user.last_login_at = utcnow()
        audit("login", "user", user.id)
        db.session.commit()
        if user.requires_2fa:
            return redirect(url_for("admin_auth.setup_2fa"))
        return redirect(_safe_next(request.args.get("next")))
    return render_template("admin/login.html")


@bp.route("/2fa", methods=["GET", "POST"])
@limiter.limit("10 per 15 minutes", methods=["POST"])
def verify():
    uid = session.get("pending_uid")
    user = db.session.get(User, uid) if uid else (current_user if current_user.is_authenticated else None)
    if user is None or not user.totp_enabled:
        return redirect(url_for("admin_auth.login"))
    if request.method == "POST":
        code = (request.form.get("code") or "").replace(" ", "")
        ok = pyotp.TOTP(user.totp_secret or "").verify(code, valid_window=1) if code.isdigit() else user.use_backup_code(code)
        if ok:
            nxt = session.pop("pending_next", None)
            session.pop("pending_uid", None)
            login_user(user)
            session["2fa_ok"] = True
            user.last_login_at = utcnow()
            audit("login", "user", user.id, summary="2FA")
            db.session.commit()
            return redirect(_safe_next(nxt))
        audit("2fa_failed", "user", user.id)
        db.session.commit()
        flash("الرمز غير صحيح.", "error")
    return render_template("admin/verify_2fa.html")


@bp.route("/2fa/setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    user: User = current_user  # type: ignore[assignment]
    if user.totp_enabled and not request.args.get("reset"):
        return redirect(url_for("admin_core.dashboard"))
    secret = session.get("totp_setup_secret") or pyotp.random_base32()
    session["totp_setup_secret"] = secret
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Manasety Admin")
    if request.method == "POST":
        if pyotp.TOTP(secret).verify((request.form.get("code") or "").strip(), valid_window=1):
            user.totp_secret = secret
            user.totp_enabled = True
            codes = user.generate_backup_codes()
            session.pop("totp_setup_secret", None)
            session["2fa_ok"] = True
            audit("2fa_enabled", "user", user.id)
            db.session.commit()
            return render_template("admin/backup_codes.html", codes=codes)
        flash("الرمز غير صحيح، تأكد من وقت الجهاز وحاول مرة أخرى.", "error")
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode()
    svg = svg[svg.find("<svg"):]
    return render_template("admin/setup_2fa.html", qr=Markup(svg), secret=secret, forced=user.requires_2fa)


@bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    user: User = current_user  # type: ignore[assignment]
    if request.method == "POST":
        if not user.check_password(request.form.get("current") or ""):
            flash("كلمة المرور الحالية غير صحيحة.", "error")
        elif len(request.form.get("new") or "") < 12:
            flash("كلمة المرور الجديدة 12 حرفًا على الأقل.", "error")
        else:
            user.set_password(request.form["new"])
            user.session_version += 1  # signs out every other session
            audit("password_changed", "user", user.id)
            db.session.commit()
            login_user(user)
            session["2fa_ok"] = True
            flash("تم تغيير كلمة المرور.", "ok")
    return render_template("admin/account.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        audit("logout", "user", current_user.id)
        db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for("admin_auth.login"))
