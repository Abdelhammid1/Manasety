// ============================================================================
//  Dashboard: list every `data/*.json` in the media repo. Each row → View,
//  Edit, Copy Link. Delete is handled in Stage E.
//  Also exports showScreen(id) — the shared screen manager used by form.
// ============================================================================

import { CONFIG } from "../config.js";
import { listDir, getFile, deleteFile } from "./github-api.js";

const SCREENS = ["dashboard", "editor", "success"];

export function showScreen(id) {
  for (const s of SCREENS) {
    const el = document.getElementById(s);
    if (el) el.hidden = (s !== id);
  }
  window.scrollTo({ top: 0 });
}

/**
 * Public URL for a slug. Path-based by default so it works on ANY host
 * without DNS setup: the URL is the current deployment directory + ?for=<slug>.
 *
 * If you later add a wildcard DNS record (`*.manasety.ai`) and want cleaner
 * subdomain URLs, change this to:
 *   return `https://${slug}.${CONFIG.domain}/`;
 */
export function publicUrlFor(slug) {
  // Strip the trailing filename (admin.html, index.html) to get the folder,
  // then append ?for=<slug>. Works on localhost, pages.dev, and manasety.ai/sara/.
  const dir = location.pathname.replace(/[^/]*$/, "");
  return `${location.origin}${dir}?for=${slug}`;
}

/* ---------- Row rendering ---------- */
function rowHtml(item, meta) {
  const url = publicUrlFor(item.slug);
  return `
    <li class="dash-row" data-slug="${item.slug}">
      <div class="dash-row-main">
        <div class="dash-name">${meta.name || item.slug}</div>
        <div class="dash-slug"><code>${item.slug}</code></div>
      </div>
      <div class="dash-row-actions">
        <a class="btn btn-ghost" href="${url}" target="_blank" rel="noopener">View</a>
        <button class="btn btn-outline" data-action="edit">Edit</button>
        <button class="btn btn-ghost" data-action="copy" data-url="${url}">Copy link</button>
        <button class="btn btn-ghost dash-delete" data-action="delete">Delete</button>
      </div>
    </li>
  `;
}

/* ---------- Delete a birthday ----------
   Removes every file under media/<slug>/ then data/<slug>.json.
   Each file is one commit (GitHub API limitation without a tree API dance). */
async function deleteBirthday(slug, dataSha) {
  let files = [];
  try {
    const items = await listDir(`media/${slug}`);
    if (Array.isArray(items)) files = items.filter((f) => f.type === "file");
  } catch (_) { /* no media folder — fine */ }

  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    await deleteFile(`media/${slug}/${f.name}`, f.sha, `Delete ${f.name} for ${slug}`);
  }
  await deleteFile(`data/${slug}.json`, dataSha, `Delete birthday ${slug}`);
}

/* ---------- Load + render the list ---------- */
async function loadList() {
  const noteEl = document.getElementById("dash-note");
  const listEl = document.getElementById("dash-list");
  if (!noteEl || !listEl) return;

  noteEl.textContent = "Loading…";
  listEl.innerHTML = "";

  let items;
  try {
    items = await listDir("data");
  } catch (err) {
    console.error(err);
    noteEl.textContent = "Could not read the media repo. Check your PAT scope.";
    return;
  }

  // 404 → the folder doesn't exist yet. Show an empty state.
  if (items === null || (Array.isArray(items) && items.length === 0)) {
    noteEl.textContent = "No birthdays yet. Click + New birthday to create the first one.";
    return;
  }

  // Filter down to JSON files
  const jsonFiles = items.filter((it) => it.type === "file" && it.name.endsWith(".json"));
  if (jsonFiles.length === 0) {
    noteEl.textContent = "No birthdays yet. Click + New birthday to create the first one.";
    return;
  }

  noteEl.textContent = `${jsonFiles.length} birthday${jsonFiles.length === 1 ? "" : "s"}`;

  // Fetch each JSON in parallel (small folders — fine)
  const entries = await Promise.all(
    jsonFiles.map(async (f) => {
      const slug = f.name.replace(/\.json$/, "");
      try {
        const file = await getFile(`data/${f.name}`);
        const cfg  = file ? JSON.parse(file.content) : {};
        return { slug, sha: f.sha, cfg };
      } catch (e) {
        return { slug, sha: f.sha, cfg: {}, error: e };
      }
    })
  );

  listEl.innerHTML = entries.map((e) => rowHtml({ slug: e.slug }, e.cfg)).join("");

  // Wire row actions
  listEl.querySelectorAll(".dash-row").forEach((row) => {
    const slug = row.dataset.slug;
    row.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.dataset.action;
        if (action === "copy") {
          try {
            await navigator.clipboard.writeText(btn.dataset.url);
            const original = btn.textContent;
            btn.textContent = "Copied ✓";
            setTimeout(() => { btn.textContent = original; }, 1500);
          } catch (_) { /* ignore */ }
        } else if (action === "edit") {
          const entry = entries.find((e) => e.slug === slug);
          document.dispatchEvent(new CustomEvent("admin:edit", { detail: entry }));
        } else if (action === "delete") {
          const entry = entries.find((e) => e.slug === slug);
          if (!entry) return;
          const name = entry.cfg?.name || slug;
          if (!confirm(`Delete "${name}" and all its media? This cannot be undone.`)) return;
          btn.disabled = true;
          const originalText = btn.textContent;
          btn.textContent = "Deleting…";
          try {
            await deleteBirthday(slug, entry.sha);
            loadList();
          } catch (err) {
            console.error(err);
            alert("Delete failed: " + err.message);
            btn.disabled = false;
            btn.textContent = originalText;
          }
        }
      });
    });
  });
}

/* ---------- Public actions ---------- */
export function refreshDashboard() { loadList(); }

/* ---------- Event wiring ---------- */
document.addEventListener("admin:signed-in", () => {
  showScreen("dashboard");
  loadList();
});

document.getElementById("new-btn")?.addEventListener("click", () => {
  document.dispatchEvent(new CustomEvent("admin:new"));
});

document.getElementById("back-btn")?.addEventListener("click", () => {
  showScreen("dashboard");
});
document.getElementById("back-to-dash-btn")?.addEventListener("click", () => {
  showScreen("dashboard");
  loadList();
});
