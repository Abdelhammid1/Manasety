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
    errorEl.textContent =
      "That token didn't work. Check that it's a fine-grained token with " +
      "Contents: Read + Write on the birthday-media repo, then try again.";
  } finally {
    submit.disabled = false;
    submit.textContent = "Continue";
  }
}

if (form) {
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const pat = (input.value || "").trim();
    if (!pat) { errorEl.textContent = "Paste your GitHub PAT to continue."; return; }
    attemptSignIn(pat);
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
