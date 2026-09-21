# Manasety Birthday — Multi-Person Template

A shareable birthday invitation with a quiz, memories, love letter, and
video. One deployed site serves **any number of birthdays**, each on its
own subdomain like `medo.manasety.ai`. Admin panel lets you create /
edit / delete birthdays entirely through the browser — photos and videos
upload directly, no code changes needed.

> **Status:** All 5 stages complete. Deploy, generate a PAT, create your
> first birthday.

---

## How it fits together

```
┌────────────────────────┐   ┌─────────────────────────────┐
│  Cloudflare Pages       │   │  GitHub repo                 │
│                        │   │  zyadwael/birthday-media     │
│  Serves the template   │◄──┤  data/<slug>.json            │
│  at *.manasety.ai      │   │  media/<slug>/1.jpg, vid.mp4 │
└────────────────────────┘   └─────────────────────────────┘
         ▲                                ▲
         │                                │ Admin panel commits here
         │                                │ via GitHub REST API
   Guest visits                     ┌──────────────┐
   medo.manasety.ai                 │ admin.       │
                                    │  manasety.ai │
                                    └──────────────┘
```

- **Public** — `<slug>.manasety.ai` fetches `data/<slug>.json` from the
  media repo via jsdelivr CDN, renders the birthday template.
- **Admin** — `admin.manasety.ai` is a static page that talks directly to
  the GitHub REST API using a Personal Access Token stored in your
  browser's localStorage. When you click Publish, it commits the JSON +
  media files to the media repo. No server involved.
- **Zero-cost hosting.** GitHub Pages / Cloudflare Pages are free.
  jsdelivr CDN is free. GitHub repos are free. The only recurring cost
  is the domain (`manasety.ai` is already yours).

---

## First-time setup

### 1. Site-code repo
Create an empty public GitHub repo (I'll call it `SITE_REPO`
throughout — you can name it anything, e.g. `manasety-birthday-site`).
Push the **contents** of this `birthday/` folder to its root:

```bash
git init
git add .
git commit -m "Initial import"
git remote add origin https://github.com/zyadwael/SITE_REPO.git
git branch -M main
git push -u origin main
```

### 2. Media repo (already exists)
Nothing to do — the admin panel creates `data/` and `media/` folders on
first Publish. If you want to prime the repo, just add an empty
`README.md`.

### 3. Cloudflare Pages

1. Log in to <https://dash.cloudflare.com/> and pick your account.
2. Sidebar → **Workers & Pages** → **Create application** → **Pages** →
   **Connect to Git** → authorize GitHub → pick `SITE_REPO`.
3. Setup:
   - Framework preset: **None**
   - Build command: *(leave blank)*
   - Build output directory: `/`
4. Click **Save and Deploy**. First deploy takes ~30 seconds.

### 4. Custom domains

In the Pages project → **Custom domains** → **Set up a custom domain**:

- Add `admin.manasety.ai`
- Add `*.manasety.ai` (wildcard — catches every birthday slug)

Cloudflare auto-creates the DNS records if `manasety.ai` is on Cloudflare
DNS. If DNS is elsewhere, follow Cloudflare's prompt to add CNAMEs.

### 5. GitHub Personal Access Token

1. GitHub → **Settings → Developer settings → Fine-grained tokens →
   Generate new token**.
2. **Repository access** → *Only select repositories* → pick
   `birthday-media`.
3. **Repository permissions** → set **Contents: Read and write**. Leave
   everything else at "No access".
4. Expiration: 1 year (renew before it expires — nothing else needs it).
5. Click **Generate token**. Copy the string that starts with
   `github_pat_`.

### 6. Sign in to the admin panel

Open `admin.manasety.ai`, paste the token, click **Continue**. Token is
saved in your browser's localStorage — you won't need to paste it again
on that device.

---

## Making a birthday (workflow)

1. Sign in at `admin.manasety.ai` with your PAT.
2. Click **+ New birthday** on the dashboard.
3. Fill in the form:
   - **Name** — English or Arabic; the slug auto-fills from it
   - **Slug** — the URL identifier (`medo` → `medo.manasety.ai`); edit if
     you want something specific
   - **Advanced text** (collapsed by default) — override any label,
     button text, or the wrong-answer modal wording
   - **Quiz** — click **+ Add question** for each. Each question has 3
     option slots (add more with **+ Add option**); click the radio next
     to the correct one
   - **Memories** — click **+ Add photo** for each; pick a file
     (thumbnail previews instantly) and type a date caption
   - **Letter** — 4 fields for the eyebrow, recipient name, Arabic body,
     English body + two signature lines
   - **Video** — pick a file (warned above 25 MB, refused above 50 MB)
     OR paste a YouTube URL. If both are set, the file wins
4. Click **Publish**. A progress bar shows each file uploading. Total
   time for ~6 photos + 1 short video: ~15 seconds on a decent connection.
5. Success screen shows the public URL with **Copy link**, **Edit
   again**, and **Back to dashboard** buttons.

### Editing an existing birthday
Dashboard → **Edit** on any row. Form pre-fills. Photos you don't touch
keep their existing paths. Attach new files only for the ones you want
to replace. Any change marks the form as dirty; navigating away without
publishing prompts to confirm.

### Deleting
Dashboard → **Delete** on the row. Confirms first; then removes every
file under `media/<slug>/` and finally `data/<slug>.json`. Each removal
is a separate commit in the media repo (visible in the repo history).

---

## Local development

```bash
cd birthday/
python -m http.server 8000
```

- <http://localhost:8000/?for=demo> — renders the bundled Sara demo
  (falls back to `DEMO_CONFIG` if no real `demo.json` in the media repo)
- <http://localhost:8000/?for=medo> — fetches from the media repo, shows
  "Birthday not found" if it isn't there yet
- <http://localhost:8000/admin.html> — admin panel

`_redirects` is only honored by Cloudflare — during local dev you'd
navigate to `admin.html` directly.

---

## Project layout

```
birthday/                     ← SITE_REPO root after push
├── index.html                public template
├── admin.html                admin panel (login gate + dashboard)
├── config.js                 media repo owner/name/branch, domain, CDN base
├── _redirects                Cloudflare: admin.* → /admin.html
├── README.md                 this file
├── css/
│   ├── style.css             template styles
│   └── admin.css             admin panel styles
└── js/
    ├── template.js           renderer + bootstrap
    ├── page-flow.js          quiz + transitions + confetti
    ├── loader.js             slug resolution + JSON fetch
    ├── github-api.js         GitHub REST helpers (get/put/delete + base64)
    └── admin-auth.js         PAT gate + verify against /user
```

## Roadmap — all shipped

- [x] **Stage A** — Extract template from single-file birthday page
- [x] **Stage B** — Slug routing + fetch from media repo
- [x] **Stage C** — Admin login gate + Cloudflare deployment setup
- [x] **Stage D** — Dashboard listing + editor form + Publish flow
- [x] **Stage E** — Delete flow + unsaved-changes guard + docs

## Cost + limits

| Thing | Free tier | Reality for this project |
|---|---|---|
| GitHub repos | Unlimited public | Fine |
| GitHub Contents API | 5000 req/hour authenticated | You'd never hit it |
| jsdelivr CDN | Unlimited bandwidth | Fine |
| Cloudflare Pages | 500 builds/month, unlimited traffic | Way under |
| Individual file size | 100 MB (GitHub API) | We warn > 25 MB, refuse > 50 MB |

## Security notes

- The **PAT lives in your browser's localStorage**. It never leaves the
  admin panel except in `Authorization: Bearer …` headers to
  `api.github.com`. Anyone with access to the device you signed in on can
  use it — treat it like a saved password. Sign out to clear it.
- The token is scoped to `birthday-media` only. Even if it leaked, an
  attacker could only modify birthdays, not touch your other repos.
- Data is **public** by design — anyone with a `<slug>.manasety.ai` link
  can view. Don't put anything private in a birthday (real addresses,
  phone numbers, etc.).
- If you rotate the PAT (expiration renewal or after suspected leak),
  sign out on every device you used, generate a new fine-grained token
  with the same scope, and sign in again.

## Troubleshooting

**"Token check failed (401)"** on sign-in
→ The PAT is missing the `Contents: Read and write` scope for
  `birthday-media`, or the token is invalid / expired. Regenerate.

**"Token check failed (403)"**
→ The PAT is fine but the fine-grained token doesn't include the
  `birthday-media` repo in its Repository access list. Edit the token
  and add the repo.

**Publish fails with 409 on a PUT**
→ Someone else (or another tab) just committed to the same file. Reload
  the editor to fetch the latest `sha`, then Publish again.

**A birthday looks stale after Publish**
→ jsdelivr CDN caches for ~5–15 minutes. The site falls back to the
  fresher `raw.githubusercontent.com` on CDN miss, but that path is
  rate-limited. Wait a few minutes or view via `?for=<slug>` on the
  Cloudflare deployment URL (which uses raw).

**"Birthday not found" on `medo.manasety.ai` right after publish**
→ Same cause. Try `?for=medo` on the Cloudflare Pages URL first — it
  reads from raw and will show up immediately.

**Deleting a birthday takes ages**
→ Each file is one commit. A birthday with 8 photos + 1 video → 10
  DELETE commits + 1 for the JSON = 11 total. Normal.

## Migrating off GitHub later

Everything is plain JSON + plain image / video files in the media repo.
To move to any other host (S3, R2, a proper CMS), you'd:

1. Clone the `birthday-media` repo — you now have every birthday's data
   and every uploaded photo/video.
2. Point the new host at those files (or re-upload).
3. Change `CONFIG.cdnBase` in `config.js` to the new URL prefix.
4. Redeploy the site repo.

No lock-in, no export tool needed, no proprietary formats.
