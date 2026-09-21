// ============================================================================
//  PAT gate for the admin panel.
//    - Shows the login form when no PAT is stored (or when the stored PAT
//      fails verification)
//    - On successful verify, hides the gate and reveals #admin-app, then
//      dispatches an "admin:signed-in" event so admin-list / admin-form
//      can pick up
//    - Sign-out button clears the PAT and reloads
// ============================================================================

import { getPat, setPat, clearPat, verifyPat } from "./github-api.js";

const gate     = document.getElementById("gate");
const app      = document.getElementById("admin-app");
const form     = document.getElementById("pat-form");
const input    = document.getElementById("pat-input");
const submit   = document.getElementById("pat-submit");
const errorEl  = document.getElementById("pat-error");
const whoami   = document.getElementById("whoami");
const signout  = document.getElementById("signout-btn");

async function attemptSignIn(pat) {
  errorEl.textContent = "";
  input.classList.remove("invalid");
  submit.disabled = true;
  submit.textContent = "Checking…";
  try {
    const login = await verifyPat(pat);
    setPat(pat);
    if (whoami) whoami.textContent = `Signed in as ${login}`;
    gate.hidden = true;
    app.hidden = false;
    document.dispatchEvent(new CustomEvent("admin:signed-in", { detail: { login } }));
  } catch (err) {
    console.error(err);
    // Keep messages simple + non-technical — the client doesn't need to know
    // this is a GitHub PAT under the hood.
    const status = err && err.message ? err.message.match(/\d{3}/)?.[0] : "";
    let msg = "Invalid access code — please try again.";
    if (status === "403") msg = "This code doesn't have access. Ask the admin for a valid one.";
    if (!status && err && err.name === "TypeError") msg = "Network problem — check your connection and retry.";
    errorEl.textContent = msg;
    input.classList.add("invalid");
    input.focus();
    input.select();
  } finally {
    submit.disabled = false;
    submit.textContent = "Continue";
  }
}

if (form) {
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const pat = (input.value || "").trim();
    if (!pat) {
      errorEl.textContent = "Please enter your access code.";
      input.classList.add("invalid");
      input.focus();
      return;
    }
    attemptSignIn(pat);
  });
  input.addEventListener("input", () => {
    input.classList.remove("invalid");
    if (errorEl.textContent) errorEl.textContent = "";
  });
}

if (signout) {
  signout.addEventListener("click", () => {
    clearPat();
    location.reload();
  });
}

// On load, if a PAT is already stored, try silent sign-in.
(async () => {
  const existing = getPat();
  if (existing) await attemptSignIn(existing);
})();
