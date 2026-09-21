// ============================================================================
//  Single source of truth for repo / domain settings.
//  Edit this file if you rename the media repo, change the branch, or move
//  the site to a different domain.
// ============================================================================

export const CONFIG = {
  mediaOwner:  "zyadwael",
  mediaRepo:   "birthday-media",
  mediaBranch: "main",

  // Public domain the birthday subdomains live under.
  domain:      "manasety.ai",

  // Public read path — jsdelivr CDN is fast, cached, and has no rate limit.
  // It lags fresh commits by ~5–15 min; the loader falls back to rawBase.
  cdnBase:     "https://cdn.jsdelivr.net/gh/zyadwael/birthday-media@main",

  // Fresher but rate-limited — used as the fallback when CDN 404s a
  // just-committed file. Also what the admin panel reads while editing.
  rawBase:     "https://raw.githubusercontent.com/zyadwael/birthday-media/main",
};
