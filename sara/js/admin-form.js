// ============================================================================
//  Editor form — create or edit a birthday, upload photos + video, save
//  the JSON. Handles:
//    - Filling the form from an existing config (edit mode)
//    - Quiz builder (dynamic question rows)
//    - Memories builder (photo file input + preview + date label)
//    - Video (file OR YouTube URL)
//    - Publish flow: uploads files → PUT data/<slug>.json → success screen
// ============================================================================

import { CONFIG } from "../config.js";
import * as gh from "./github-api.js";
import { showScreen, publicUrlFor } from "./admin-list.js";

/* ================== Constants + state ================== */

const MAX_FILE_MB   = 50;
const WARN_FILE_MB  = 25;

/** { slug, sha, cfg } when editing; null when creating new. */
let editing = null;

/** Set true when the form has been touched but not yet published; used for
 *  the beforeunload guard and for prompting on Cancel. */
let dirty = false;
const markDirty = () => { dirty = true; };
const markClean = () => { dirty = false; };

const DEFAULT_QUESTION = () => ({
  question: "",
  options: ["", "", ""],
  correctIndex: 0,
});
const DEFAULT_MEMORY = () => ({ path: "", dateLabel: "" });

/* ================== Helpers ================== */

const $ = (id) => document.getElementById(id);

function slugify(s) {
  return (s || "")
    .toString()
    .trim()
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}\s-]/gu, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    // If nothing latin+digit survived (e.g. all Arabic), fall back to a hash
    .replace(/[^a-z0-9-]/g, "")
    .slice(0, 40);
}

function showError(field, msg) {
  const err = document.querySelector(`.error[data-for="${field}"]`);
  if (err) err.textContent = msg || "";
  const input = $(`f-${field}`);
  if (input) input.classList.toggle("invalid", Boolean(msg));
}

function extOf(name) {
  const m = /\.([a-z0-9]+)$/i.exec(name || "");
  return m ? m[1].toLowerCase() : "bin";
}

function fileSizeMb(file) { return file.size / (1024 * 1024); }

function cdnUrl(path) { return `${CONFIG.cdnBase}/${path}`; }

/* ================== Slug preview ================== */

$("f-name")?.addEventListener("input", (e) => {
  // Only auto-fill slug if the user hasn't already customized it.
  const slugInput = $("f-slug");
  if (!slugInput || slugInput.dataset.userEdited === "1") return;
  slugInput.value = slugify(e.target.value);
  updateSlugPreview();
});
$("f-slug")?.addEventListener("input", (e) => {
  e.target.dataset.userEdited = "1";
  updateSlugPreview();
});

function updateSlugPreview() {
  const slug = $("f-slug")?.value.trim();
  const preview = $("slug-preview");
  if (preview) preview.textContent = slug ? `${slug}.${CONFIG.domain}` : `<slug>.${CONFIG.domain}`;
}

/* ================== Quiz builder ================== */

const quizBuilder = $("quiz-builder");
$("add-question-btn")?.addEventListener("click", () => addQuestionRow(DEFAULT_QUESTION()));

function addQuestionRow(q) {
  const idx = quizBuilder.querySelectorAll(".q-row").length;
  const groupName = `q-correct-${Date.now()}-${idx}`;

  const row = document.createElement("div");
  row.className = "q-row";
  row.dataset.groupName = groupName;
  row.innerHTML = `
    <div class="q-row-header">
      <span class="q-num">Question ${idx + 1}</span>
      <button type="button" class="btn btn-ghost" data-action="remove-q">Remove</button>
    </div>
    <div class="field">
      <label>Question</label>
      <textarea class="q-text" rows="2" dir="auto" placeholder="بتحبي ايه أكتر؟"></textarea>
    </div>
    <div class="q-options">
      ${[0, 1, 2].map((i) => `
        <div class="q-option-row">
          <input type="radio" name="${groupName}" value="${i}" ${i === q.correctIndex ? "checked" : ""} title="Mark as correct" />
          <input type="text" class="q-option-text" dir="auto" placeholder="Option ${i + 1}" />
          <button type="button" class="btn btn-ghost q-opt-remove" data-action="remove-opt" title="Remove option">×</button>
        </div>
      `).join("")}
    </div>
    <button type="button" class="btn btn-ghost" data-action="add-opt">+ Add option</button>
  `;

  row.querySelector(".q-text").value = q.question || "";
  const optInputs = row.querySelectorAll(".q-option-text");
  q.options.forEach((v, i) => { if (optInputs[i]) optInputs[i].value = v; });

  wireQuestionRow(row);
  quizBuilder.appendChild(row);
  renumberQuestions();
}

function wireQuestionRow(row) {
  row.querySelector('[data-action="remove-q"]').addEventListener("click", () => {
    row.remove();
    renumberQuestions();
  });
  row.querySelector('[data-action="add-opt"]').addEventListener("click", () => {
    addOptionInRow(row, "");
  });
  row.querySelectorAll('[data-action="remove-opt"]').forEach((btn) =>
    btn.addEventListener("click", (e) => e.currentTarget.closest(".q-option-row").remove())
  );
}

function addOptionInRow(row, val) {
  const container = row.querySelector(".q-options");
  const groupName = row.dataset.groupName;
  const i = container.querySelectorAll(".q-option-row").length;
  const el = document.createElement("div");
  el.className = "q-option-row";
  el.innerHTML = `
    <input type="radio" name="${groupName}" value="${i}" title="Mark as correct" />
    <input type="text" class="q-option-text" dir="auto" placeholder="Option ${i + 1}" />
    <button type="button" class="btn btn-ghost q-opt-remove" data-action="remove-opt" title="Remove option">×</button>
  `;
  el.querySelector(".q-option-text").value = val || "";
  el.querySelector('[data-action="remove-opt"]').addEventListener("click", () => el.remove());
  container.appendChild(el);
}

function renumberQuestions() {
  quizBuilder.querySelectorAll(".q-row").forEach((row, i) => {
    row.querySelector(".q-num").textContent = `Question ${i + 1}`;
  });
}

function readQuiz() {
  return [...quizBuilder.querySelectorAll(".q-row")].map((row) => {
    const question = row.querySelector(".q-text").value.trim();
    const opts = [...row.querySelectorAll(".q-option-text")].map((i) => i.value.trim());
    const options = opts.filter(Boolean);
    const radios = [...row.querySelectorAll('input[type="radio"]')];
    const checked = radios.findIndex((r) => r.checked);
    // Convert radio index (into full opts list) to index in the FILTERED list
    let correctIndex = 0;
    if (checked >= 0) {
      const beforeFilteredKept = opts.slice(0, checked + 1).filter(Boolean).length - 1;
      correctIndex = Math.max(0, beforeFilteredKept);
    }
    return { question, options, correctIndex };
  }).filter((q) => q.question && q.options.length >= 2);
}

/* ================== Memories builder ================== */

const memBuilder = $("memories-builder");
$("add-memory-btn")?.addEventListener("click", () => addMemoryRow(DEFAULT_MEMORY()));

function addMemoryRow(m) {
  const idx = memBuilder.querySelectorAll(".mem-row").length;
  const row = document.createElement("div");
  row.className = "mem-row";
  row.dataset.existingPath = m.path || "";
  row.innerHTML = `
    <div class="mem-thumb">
      ${m.path ? `<img src="${cdnUrl(m.path)}" alt="" />` : `<div class="mem-thumb-placeholder">#${idx + 1}</div>`}
    </div>
    <div class="mem-fields">
      <div class="field">
        <label>Replace photo (optional)</label>
        <input type="file" class="mem-file" accept="image/*" />
        <span class="hint mem-current" ${m.path ? "" : "hidden"}>Currently: <code>${m.path}</code></span>
      </div>
      <div class="field">
        <label>Date caption</label>
        <input type="text" class="mem-date" value="${m.dateLabel || ""}" placeholder="NOV 2024 · 23" />
      </div>
    </div>
    <button type="button" class="btn btn-ghost mem-remove" data-action="remove-mem" title="Remove photo">×</button>
  `;

  const fileInput = row.querySelector(".mem-file");
  const thumb = row.querySelector(".mem-thumb");
  fileInput.addEventListener("change", (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (fileSizeMb(f) > MAX_FILE_MB) {
      alert(`This file is ${fileSizeMb(f).toFixed(1)} MB. Max is ${MAX_FILE_MB} MB.`);
      fileInput.value = "";
      return;
    }
    const url = URL.createObjectURL(f);
    thumb.innerHTML = `<img src="${url}" alt="" />`;
  });

  row.querySelector('[data-action="remove-mem"]').addEventListener("click", () => {
    row.remove();
    renumberMemories();
  });

  memBuilder.appendChild(row);
  renumberMemories();
}

function renumberMemories() {
  memBuilder.querySelectorAll(".mem-row").forEach((row, i) => {
    const ph = row.querySelector(".mem-thumb-placeholder");
    if (ph) ph.textContent = `#${i + 1}`;
  });
}

function readMemories() {
  return [...memBuilder.querySelectorAll(".mem-row")].map((row) => {
    const file = row.querySelector(".mem-file").files?.[0] || null;
    const dateLabel = row.querySelector(".mem-date").value.trim();
    const existingPath = row.dataset.existingPath || "";
    return { file, existingPath, dateLabel };
  });
}

/* ================== Video ================== */

$("f-video-file")?.addEventListener("change", (e) => {
  const f = e.target.files?.[0];
  if (!f) return;
  if (fileSizeMb(f) > MAX_FILE_MB) {
    alert(`Video is ${fileSizeMb(f).toFixed(1)} MB. Max is ${MAX_FILE_MB} MB.`);
    e.target.value = "";
    return;
  }
  if (fileSizeMb(f) > WARN_FILE_MB) {
    if (!confirm(`Video is ${fileSizeMb(f).toFixed(1)} MB — that's large for the GitHub API. Continue?`)) {
      e.target.value = "";
    }
  }
});
$("video-remove-btn")?.addEventListener("click", () => {
  const info = $("video-existing");
  if (info) { info.hidden = true; info.dataset.removed = "1"; }
});

/* ================== Form fill / read ================== */

function fillForm(cfg) {
  $("f-name").value = cfg.name || "";
  $("f-slug").value = editing?.slug || "";
  $("f-slug").dataset.userEdited = editing ? "1" : "";
  updateSlugPreview();

  const textFields = [
    "eyebrowText", "celebrationSub", "startButtonText",
    "wrongEmoji", "wrongMessage", "wrongButtonText",
    "confirmButtonText", "celebrateButtonText",
    "letterEyebrow", "letterName", "letterAr", "letterEn",
    "signatureEn", "signatureAr",
  ];
  for (const key of textFields) {
    const el = $(`f-${key}`);
    if (el) el.value = cfg[key] || "";
  }

  // Quiz
  quizBuilder.innerHTML = "";
  const quiz = Array.isArray(cfg.quiz) && cfg.quiz.length ? cfg.quiz : [DEFAULT_QUESTION()];
  quiz.forEach(addQuestionRow);

  // Memories
  memBuilder.innerHTML = "";
  const memories = Array.isArray(cfg.memories) ? cfg.memories : [];
  if (memories.length === 0) {
    addMemoryRow(DEFAULT_MEMORY());
  } else {
    memories.forEach(addMemoryRow);
  }

  // Video
  const vidExistingWrap = $("video-existing");
  const vidExistingPath = $("video-existing-path");
  $("f-video-file").value = "";
  if (cfg.videoPath) {
    vidExistingWrap.hidden = false;
    vidExistingWrap.dataset.removed = "";
    vidExistingPath.textContent = cfg.videoPath;
  } else {
    vidExistingWrap.hidden = true;
  }
  $("f-video-url").value = cfg.videoUrl || "";

  // Clear any prior errors
  document.querySelectorAll(".error[data-for]").forEach((e) => (e.textContent = ""));
  document.querySelectorAll("input.invalid, textarea.invalid").forEach((i) =>
    i.classList.remove("invalid")
  );
}

function collectForm() {
  const cfg = {};
  cfg.name = $("f-name").value.trim();
  cfg.slug = $("f-slug").value.trim().toLowerCase();

  const textFields = [
    "eyebrowText", "celebrationSub", "startButtonText",
    "wrongEmoji", "wrongMessage", "wrongButtonText",
    "confirmButtonText", "celebrateButtonText",
    "letterEyebrow", "letterName", "letterAr", "letterEn",
    "signatureEn", "signatureAr",
  ];
  for (const key of textFields) {
    const el = $(`f-${key}`);
    const v = (el?.value || "").trim();
    if (v) cfg[key] = v;
  }

  cfg.quiz = readQuiz();
  cfg.memoriesDraft = readMemories();

  const videoFile = $("f-video-file").files?.[0] || null;
  const videoUrl  = $("f-video-url").value.trim();
  const removed = $("video-existing")?.dataset.removed === "1";
  cfg._videoDraft = { file: videoFile, url: videoUrl, removed };

  return cfg;
}

/* ================== Validation ================== */

function validate(cfg) {
  let ok = true;
  if (!cfg.name) { showError("f-name", "Please enter a name."); ok = false; } else showError("f-name", "");
  if (!/^[a-z0-9-]{1,40}$/.test(cfg.slug)) {
    showError("f-slug", "Slug must be lowercase letters, digits, or hyphens.");
    ok = false;
  } else showError("f-slug", "");

  if (!cfg.quiz.length) {
    showError("quiz", "Add at least one question with 2+ options.");
    ok = false;
  } else showError("quiz", "");
  return ok;
}

/* ================== Publish flow ================== */

function setProgress(pct, text) {
  const wrap = $("publish-progress");
  const fill = $("progress-fill");
  const t    = $("progress-text");
  wrap.hidden = false;
  fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
  t.textContent = text;
}
function hideProgress() { $("publish-progress").hidden = true; }

async function uploadFileTo(path, file, commitMsg) {
  const buffer = await file.arrayBuffer();
  // Detect if a file already exists at this exact path so we send `sha`.
  let sha;
  try {
    const existing = await gh.getFile(path);
    if (existing?.sha) sha = existing.sha;
  } catch (_) { /* 404 is expected */ }

  await gh.putFile(path, { content: buffer, message: commitMsg, sha });
  return path;
}

async function publishFlow(cfg) {
  const slug = cfg.slug;
  const now = new Date().toISOString();

  // Compute total steps for progress
  const memsToUpload = cfg.memoriesDraft.filter((m) => m.file).length;
  const videoNew    = Boolean(cfg._videoDraft.file);
  const total = memsToUpload + (videoNew ? 1 : 0) + 1; // + 1 for the JSON
  let done = 0;
  const bump = (msg) => { done++; setProgress((done / total) * 100, msg); };

  // 1. Upload memories that have a new File
  const finalMemories = [];
  for (let i = 0; i < cfg.memoriesDraft.length; i++) {
    const m = cfg.memoriesDraft[i];
    if (m.file) {
      const ext = extOf(m.file.name);
      const path = `media/${slug}/photo-${Date.now()}-${i + 1}.${ext}`;
      setProgress((done / total) * 100, `Uploading photo ${i + 1}/${cfg.memoriesDraft.length}…`);
      await uploadFileTo(path, m.file, `Add photo ${i + 1} for ${slug}`);
      finalMemories.push({ path, dateLabel: m.dateLabel });
      bump(`Photo ${i + 1} uploaded`);
    } else if (m.existingPath) {
      finalMemories.push({ path: m.existingPath, dateLabel: m.dateLabel });
    }
    // else: empty row, skip
  }

  // 2. Video
  let videoPath;
  let videoUrl;
  if (cfg._videoDraft.file) {
    const ext = extOf(cfg._videoDraft.file.name);
    videoPath = `media/${slug}/video-${Date.now()}.${ext}`;
    setProgress((done / total) * 100, "Uploading video…");
    await uploadFileTo(videoPath, cfg._videoDraft.file, `Add video for ${slug}`);
    bump("Video uploaded");
  } else if (!cfg._videoDraft.removed && editing?.cfg?.videoPath) {
    // Keep the previously-attached path
    videoPath = editing.cfg.videoPath;
  }
  if (cfg._videoDraft.url) videoUrl = cfg._videoDraft.url;

  // 3. Build final JSON
  const jsonBody = {
    slug,
    name: cfg.name,
    quiz: cfg.quiz,
    memories: finalMemories,
    createdAt: editing?.cfg?.createdAt || now,
    updatedAt: now,
  };
  // Copy over optional text fields
  const textFields = [
    "eyebrowText", "celebrationSub", "startButtonText",
    "wrongEmoji", "wrongMessage", "wrongButtonText",
    "confirmButtonText", "celebrateButtonText",
    "letterEyebrow", "letterName", "letterAr", "letterEn",
    "signatureEn", "signatureAr",
  ];
  for (const k of textFields) if (cfg[k]) jsonBody[k] = cfg[k];
  if (videoPath) jsonBody.videoPath = videoPath;
  if (videoUrl)  jsonBody.videoUrl  = videoUrl;

  // 4. PUT data/<slug>.json
  setProgress((done / total) * 100, "Saving birthday…");
  const path = `data/${slug}.json`;
  let sha;
  if (editing?.sha) {
    sha = editing.sha;
  } else {
    // Might already exist (creating with existing slug) — grab sha if so
    try { const existing = await gh.getFile(path); if (existing?.sha) sha = existing.sha; } catch(_) {}
  }
  const putRes = await gh.putFile(path, {
    content: JSON.stringify(jsonBody, null, 2),
    message: (editing ? "Update" : "Add") + ` birthday ${slug}`,
    sha,
  });
  bump("Saved");
  editing = { slug, sha: putRes.content?.sha || null, cfg: jsonBody };
  return jsonBody;
}

/* ================== Publish button handler ================== */

const form = $("editor-form");
form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const errEl = $("publish-error");
  errEl.textContent = "";

  const cfg = collectForm();
  if (!validate(cfg)) return;

  const btn = $("publish-btn");
  btn.disabled = true;
  btn.textContent = "Publishing…";

  try {
    const finalCfg = await publishFlow(cfg);
    markClean();
    // Success screen
    const url = publicUrlFor(finalCfg.slug);
    $("success-url").textContent = url;
    $("success-link").href = url;
    showScreen("success");
    hideProgress();
  } catch (err) {
    console.error(err);
    errEl.textContent = err.message || "Could not publish. Check the console for details.";
    hideProgress();
  } finally {
    btn.disabled = false;
    btn.textContent = "Publish";
  }
});

/* ================== Success screen buttons ================== */

$("copy-url-btn")?.addEventListener("click", async () => {
  const url = $("success-url").textContent;
  try {
    await navigator.clipboard.writeText(url);
    const b = $("copy-url-btn");
    const orig = b.textContent;
    b.textContent = "Copied ✓";
    setTimeout(() => { b.textContent = orig; }, 1500);
  } catch (_) { /* ignore */ }
});
$("edit-again-btn")?.addEventListener("click", () => {
  showScreen("editor");
});

/* ================== Screen entry points ================== */

document.addEventListener("admin:new", () => {
  editing = null;
  $("editor-title").textContent = "New birthday";
  fillForm({});
  markClean();
  showScreen("editor");
});

document.addEventListener("admin:edit", (e) => {
  editing = e.detail;
  $("editor-title").textContent = `Edit — ${editing.cfg?.name || editing.slug}`;
  fillForm(editing.cfg || {});
  markClean();
  showScreen("editor");
});

/* ================== Unsaved-changes guard ================== */
// Any input/change inside the editor form marks the form dirty.
form?.addEventListener("input", markDirty);
form?.addEventListener("change", markDirty);
$("add-question-btn")?.addEventListener("click", markDirty);
$("add-memory-btn")?.addEventListener("click", markDirty);

// Intercept Cancel button — prompt if dirty.
const backBtn = $("back-btn");
if (backBtn) {
  const origHandler = backBtn.onclick;
  backBtn.addEventListener("click", (e) => {
    if (dirty && !confirm("You have unsaved changes. Discard them?")) {
      e.stopImmediatePropagation();
      e.preventDefault();
      return;
    }
    markClean();
  }, true); // capture phase so this runs before the admin-list.js handler
}

// Warn on tab close / navigate away while dirty.
window.addEventListener("beforeunload", (e) => {
  if (!dirty) return;
  e.preventDefault();
  e.returnValue = "";
});
