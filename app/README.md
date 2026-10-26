# منصتي — Landing page + Dashboard

Flask + PostgreSQL app that serves **manasety.ai** (Manasety School landing page, blog, legal pages)
and the **/admin** dashboard that controls every word, image, section, article, FAQ, file, redirect,
integration and lead. Built from the spec «مواصفات اللاندينج بيدج الجديدة لمنصتي» (26 Oct 2026) and the
approved Claude Design canvas: https://claude.ai/artifact/Y7tPDB5uTewd9y9sidM5oA

The old static site in the repo root is untouched and stays the rollback target.

## Local development

```bash
cd app
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # (bin/ on Linux/macOS)
export SESSION_COOKIE_SECURE=0                       # http://localhost only
flask --app wsgi db upgrade -d migrations            # SQLite at instance/dev.db by default
flask --app wsgi seed --legal-dir <folder with live privacy/terms/refund.html> --profile-pdf <manasety-profile.pdf>
flask --app wsgi create-admin                         # 2FA enrolment is forced on first login
flask --app wsgi run
pytest -q
```

## Rules the code enforces (spec «سجل الادعاءات»)

| Rule | Where |
| --- | --- |
| A client/partner name or logo appears only with consent + consent date + proof file + visible | `Client.is_publishable`, `publishing.public_clients()` (SQL + property) |
| A number appears only with source + verification date + visible. Write numbers as `[[fact:key]]` or `[[if:key]]…[[/if]]` | `Fact.is_publishable`, `publishing.resolve_facts()` |
| Case-study client name and URL only after consent; before that the anonymous label shows | `CaseStudy.display_name()/display_url()` |
| "قريبًا" features show a badge; a date only with the confirmed-date flag, never in free text | `Feature.validation_errors()` |
| FAQ answer containing a number needs a source | `FaqItem.validation_errors()` |
| Public page reads only the **published** snapshot; edits are drafts until Publish (or scheduled) | `Page.published_snapshot`, `publishing.publish_page()` |
| No prices / packages / direct payment on the page (PayTabs review) | content + test `test_no_prices_or_packages_on_page` |
| Every admin change logged with before/after | `security.audit()` → `/admin/audit` |
| Admin & Editor can't use the dashboard without TOTP 2FA | `admin/__init__.py` gate |
| No secrets in the integrations registry | `crud._integrations` validator; keys live in `.env` |

Roles: **Admin** everything · **Editor** page/sections/features/clients/facts/case studies/FAQ/files/legal/media ·
**Marketer** articles/SEO/redirects/backlinks/integrations/media · **Sales** leads only.

## What was kept from the live site (inventory 26 Oct 2026)

- Google Analytics `G-RB896Z7ZBD`, Meta Pixel `1365676268753546`, Meta domain-verification tag: seeded **verbatim**
  into the integrations registry and injected in `<head>`. Same event names from `static/js/site.js`
  (`click_whatsapp`, `click_submit_form`, `click_book_session`, Pixel `Lead` + `WhatsAppClick`).
- Marsoud CRM lead endpoint + web3forms email backup: same payload, now sent **from the server**
  (`services/leads.py`) so the token is no longer exposed in the browser. Set `MARSOUD_CONTACT_TOKEN` and
  `WEB3FORMS_ACCESS_KEY` in `.env`, otherwise leads are saved but not forwarded (the dashboard shows a red warning).
- `/privacy.html`, `/terms.html`, `/refund.html`: imported byte-for-byte (bilingual markup + `legal.css/js`), same URLs.
- `/manasety-profile.pdf`: same URL. Hiding it removes it from pages only; the direct link keeps working.
- Anchors `#services #portfolio #ai #contact`, plus `#pricing`, which now lands on the form. `/index.html` → 301 `/`.
- Old static pages that still answer 200 (`contact.html`, `saas.html`, `lexoffice.html`, `gym-system.html`, …) and
  favicons/manifest: served from `LEGACY_DIR` (see `config.LEGACY_FILES`).
- Search Console: no HTML tag on the current page (DNS verification): nothing to move, nothing touched.

## Deploy (spec «خطة النشر»)

1. Snapshot the current site: `cp -a /var/www/manasety /opt/manasety/legacy-site-$(date +%F)` and point
   `/opt/manasety/legacy-site` at it.
2. `cp .env.example .env` and fill it in. Use `STAGING=1` + `STAGING_USER/PASSWORD` for the staging subdomain
   (the whole site becomes noindex + basic auth).
3. `docker compose up -d --build` → `docker compose exec web flask --app wsgi seed --legal-dir /legacy --profile-pdf /legacy/manasety-profile.pdf`
   → `docker compose exec web flask --app wsgi create-admin`.
4. Test on staging (table in the spec): Tag Assistant for GA, Pixel Helper for Meta, a real demo request reaching Marsoud,
   the three legal URLs, the profile PDF, `/sitemap.xml`.
5. Switch: copy `deploy/snippets/*` to `/etc/nginx/snippets/`, `ln -sf …/manasety-app.conf …/manasety-active.conf`,
   install `deploy/nginx-manasety.conf`, `nginx -t && systemctl reload nginx`.
6. **Rollback:** `ln -sf …/manasety-legacy.conf …/manasety-active.conf && systemctl reload nginx`. Takes minutes.
7. `crontab deploy/crontab` (scheduled publishing, daily off-server backup, weekly link checks).
   Submit the sitemap in Search Console.

## Not done here / needs a decision

See the summary in the PR / handover message: client consents, verified numbers, AI-provider line,
ShalabyVerse, Mahamy domain, English copy.
