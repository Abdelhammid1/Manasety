"""SEO overview: sitemap/robots status, internal-link report, broken-link scan, backlink report,
backlink live check, Search Console numbers."""
from __future__ import annotations

from collections import Counter

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import BACKLINK_CHANNELS, BACKLINK_STATUSES, Article, Backlink, utcnow
from ..publishing import live_articles
from ..security import audit, permission_required
from ..services import gsc
from ..services.linkcheck import check_backlink, scan_broken_links
from ..services.seo import article_checks
from ..settings_store import get_setting, set_setting

bp = Blueprint("admin_seo", __name__, url_prefix="/admin/seo")


@bp.route("/")
@permission_required("seo")
def index():
    product = get_setting("product_page_url") or "/"
    min_rel = int(get_setting("internal_links_min_related") or 2)
    arts = live_articles("ar") + live_articles("en")
    report = []
    for a in arts:
        failing = [c["label"] for c in article_checks(a, product, min_rel) if not c["ok"]]
        report.append({"article": a, "failing": failing})
    links = db.session.query(Backlink).all()
    by_target = Counter(b.target_url for b in links if b.status == "published")
    return render_template(
        "admin/seo.html", report=report, site=current_app.config["SITE_URL"],
        broken=get_setting("broken_links_report") or {}, by_target=by_target.most_common(20),
        lost=[b for b in links if b.status == "lost"],
        by_channel=Counter(BACKLINK_CHANNELS.get(b.channel, b.channel) for b in links if b.status == "published"),
        statuses=BACKLINK_STATUSES,
    )


@bp.route("/broken-links", methods=["POST"])
@permission_required("seo")
def broken_links():
    site = current_app.config["SITE_URL"]
    broken = scan_broken_links(site, extra_urls=[f"{site}/privacy.html", f"{site}/terms.html", f"{site}/refund.html",
                                                 f"{site}/manasety-profile.pdf", f"{site}/sitemap.xml"])
    set_setting("broken_links_report", {"at": utcnow().isoformat(timespec="minutes"), "items": broken})
    audit("scan", "broken_links", None, summary=f"{len(broken)} رابط معطّل")
    db.session.commit()
    flash(f"اكتمل الفحص: {len(broken)} رابط معطّل.", "ok" if not broken else "error")
    return redirect(url_for("admin_seo.index"))


@bp.route("/backlinks/<int:bid>/check", methods=["POST"])
@permission_required("backlinks")
def check_backlink_view(bid: int):
    link = db.session.get(Backlink, bid) or abort(404)
    check_backlink(link)
    audit("check", "backlink", link.id, after={"result": link.last_check_result, "status": link.status})
    db.session.commit()
    flash(f"نتيجة الفحص: {link.last_check_result}", "ok")
    return redirect(request.referrer or url_for("admin_crud.index", resource="backlinks"))


# Endpoint name used by the CRUD row action.
bp.add_url_rule("/backlinks/<int:bid>/check-row", "check_backlink", check_backlink_view, methods=["POST"])


@bp.route("/search-console")
@permission_required("seo")
def search_console():
    if not gsc.is_configured():
        return render_template("admin/gsc.html", configured=False)
    try:
        days = int(request.args.get("days", 28))
        data = {"pages": gsc.query("page", days), "queries": gsc.query("query", days)}
        error = None
    except Exception as exc:  # surface API/auth problems instead of a 500
        data, error = {"pages": [], "queries": []}, f"{exc.__class__.__name__}: {exc}"
    return render_template("admin/gsc.html", configured=True, data=data, error=error, days=request.args.get("days", 28))
