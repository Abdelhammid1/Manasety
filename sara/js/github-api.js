// ============================================================================
//  Thin wrapper over the GitHub REST Contents API.
//  Reads the admin's PAT from localStorage (set by admin-auth.js). If no
//  PAT is stored, unauthenticated calls still work for public read endpoints
//  but writes will fail with a 401 — which is the intended failure mode.
// ============================================================================

import { CONFIG } from "../config.js";

const API = "https://api.github.com";
const PAT_KEY = "manasety.pat.v1";

export function getPat() { return localStorage.getItem(PAT_KEY) || ""; }
export function setPat(t) { localStorage.setItem(PAT_KEY, t); }
export function clearPat() { localStorage.removeItem(PAT_KEY); }

function headers(extra = {}) {
  const h = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", ...extra };
  const pat = getPat();
  if (pat) h.Authorization = `Bearer ${pat}`;
  return h;
}

/** Verify a PAT by calling /user. Returns the login string or throws. */
export async function verifyPat(pat) {
  const res = await fetch(`${API}/user`, { headers: { ...headers(), Authorization: `Bearer ${pat}` } });
  if (!res.ok) throw new Error(`Token check failed (${res.status})`);
  const data = await res.json();
  return data.login;
}

/**
 * Fetch a file from the media repo. Returns { content, sha, size } where
 * `content` is the decoded UTF-8 string. Returns null on 404.
 */
export async function getFile(path) {
  const url = `${API}/repos/${CONFIG.mediaOwner}/${CONFIG.mediaRepo}/contents/${encodeURI(path)}?ref=${CONFIG.mediaBranch}`;
  const res = await fetch(url, { headers: headers(), cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`getFile(${path}) → ${res.status}`);
  const data = await res.json();
  let content = "";
  if (data.content) {
    const bin = atob(data.content.replace(/\n/g, ""));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    content = new TextDecoder("utf-8").decode(bytes);
  }
  return { sha: data.sha, size: data.size, content };
}

/**
 * List a directory in the media repo. Returns an array of { name, path,
 * type, sha, size } or null on 404.
 */
export async function listDir(path) {
  const url = `${API}/repos/${CONFIG.mediaOwner}/${CONFIG.mediaRepo}/contents/${encodeURI(path)}?ref=${CONFIG.mediaBranch}`;
  const res = await fetch(url, { headers: headers(), cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`listDir(${path}) → ${res.status}`);
  return await res.json();
}

/**
 * Create-or-update a file. `content` may be a string (utf-8) OR an
 * ArrayBuffer (for binary). `sha` is required for updates and must be
 * omitted for creates.
 */
export async function putFile(path, { content, message, sha }) {
  const url = `${API}/repos/${CONFIG.mediaOwner}/${CONFIG.mediaRepo}/contents/${encodeURI(path)}`;
  const body = {
    message: message || `Update ${path}`,
    branch: CONFIG.mediaBranch,
    content: encodeContent(content),
  };
  if (sha) body.sha = sha;

  const res = await fetch(url, {
    method: "PUT",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    throw new Error(`putFile(${path}) → ${res.status} ${errText}`);
  }
  return await res.json();
}

/** Delete a file. Requires the file's current sha. */
export async function deleteFile(path, sha, message) {
  const url = `${API}/repos/${CONFIG.mediaOwner}/${CONFIG.mediaRepo}/contents/${encodeURI(path)}`;
  const res = await fetch(url, {
    method: "DELETE",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ message: message || `Delete ${path}`, sha, branch: CONFIG.mediaBranch }),
  });
  if (!res.ok) throw new Error(`deleteFile(${path}) → ${res.status}`);
  return await res.json();
}

/** utf-8 string → base64. ArrayBuffer → base64. */
function encodeContent(content) {
  if (typeof content === "string") {
    return btoa(unescape(encodeURIComponent(content)));
  }
  if (content instanceof ArrayBuffer) {
    const bytes = new Uint8Array(content);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }
  throw new Error("encodeContent: unsupported content type");
}

/** File → base64 string via FileReader. */
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => {
      const dataUrl = fr.result;
      const comma   = dataUrl.indexOf(",");
      resolve(dataUrl.slice(comma + 1));
    };
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
}
