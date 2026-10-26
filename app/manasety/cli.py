"""flask CLI: seed, create-admin, publish-scheduled, scan-links, check-backlinks."""
from __future__ import annotations

from pathlib import Path

import click
from flask import Flask


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    @click.option("--legal-dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
                  help="Folder holding the live privacy.html / terms.html / refund.html to import verbatim.")
    @click.option("--profile-pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                  help="The current manasety-profile.pdf (served at the same URL).")
    def seed_cmd(legal_dir: Path | None, profile_pdf: Path | None) -> None:
        """Load the approved content. Safe to re-run: existing rows are kept."""
        from .seed import seed_all
        for line in seed_all(legal_dir, profile_pdf):
            click.echo(f"  + {line}")
        click.echo("done")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    @click.password_option()
    def create_admin(email: str, name: str, password: str) -> None:
        """Create the first Admin. 2FA enrolment is forced on first login."""
        from .extensions import db
        from .models import User
        if len(password) < 12:
            raise click.ClickException("كلمة المرور 12 حرفًا على الأقل.")
        if db.session.query(User).filter_by(email=email.strip().lower()).first():
            raise click.ClickException("البريد موجود بالفعل.")
        user = User(email=email.strip().lower(), name=name, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"admin created: {user.email}")

    @app.cli.command("publish-scheduled")
    def publish_scheduled() -> None:
        """Run from cron every minute so scheduled pages/articles go live even with no traffic."""
        from .publishing import apply_scheduled
        click.echo(f"published: {apply_scheduled()}")

    @app.cli.command("scan-links")
    def scan_links() -> None:
        from .extensions import db
        from .models import utcnow
        from .services.linkcheck import scan_broken_links
        from .settings_store import set_setting
        site = app.config["SITE_URL"]
        broken = scan_broken_links(site, [f"{site}/privacy.html", f"{site}/terms.html", f"{site}/refund.html",
                                          f"{site}/manasety-profile.pdf"])
        set_setting("broken_links_report", {"at": utcnow().isoformat(timespec="minutes"), "items": broken})
        db.session.commit()
        click.echo(f"broken: {len(broken)}")

    @app.cli.command("check-backlinks")
    def check_backlinks() -> None:
        from .extensions import db
        from .models import Backlink
        from .services.linkcheck import check_backlink
        rows = db.session.query(Backlink).filter(Backlink.status.in_(["published", "lost"])).all()
        for link in rows:
            check_backlink(link)
        db.session.commit()
        click.echo(f"checked: {len(rows)}")
