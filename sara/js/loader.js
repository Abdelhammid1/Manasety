// ============================================================================
//  Loader — figures out which birthday to render and fetches its JSON.
//    Slug resolution priority:
//      1. ?for=<slug> in query string
//      2. First DNS label of location.hostname when it's under CONFIG.domain
//         and not a reserved label (admin, www, api)
//      3. null → caller shows a "not found / how to make one" card
// ============================================================================

import { CONFIG } from "../config.js";

const RESERVED_LABELS = new Set(["admin", "www", "api"]);

export function getSlug() {
  const params = new URLSearchParams(location.search);
  const queryFor = params.get("for");
  if (queryFor) return queryFor.toLowerCase().trim();

  const host = location.hostname;
  // Only extract a subdomain if the host lives under our configured domain.
  if (host.endsWith("." + CONFIG.domain) && host !== CONFIG.domain) {
    const label = host.split(".")[0];
    if (label && !RESERVED_LABELS.has(label)) return label.toLowerCase();
  }
  return null;
}

/** Fetch the birthday JSON from the CDN, falling back to raw on 404. */
export async function loadBirthday(slug) {
  const paths = [
    `${CONFIG.cdnBase}/data/${slug}.json`,
    `${CONFIG.rawBase}/data/${slug}.json`,
  ];
  for (const url of paths) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (res.ok) return await res.json();
    } catch (_) {
      /* network error — try the next URL */
    }
  }
  return null;
}

/**
 * Convert repo-relative `path` fields on memories + video into absolute
 * CDN URLs the template can render directly. Existing `url` / `videoUrl`
 * fields (e.g. YouTube links pasted by admin) win over derived paths.
 */
export function mapPathsToUrls(cfg) {
  const cdn = CONFIG.cdnBase;

  if (Array.isArray(cfg.memories)) {
    cfg.memories = cfg.memories.map((m) => ({
      ...m,
      url: m.url || (m.path ? `${cdn}/${m.path}` : ""),
    }));
  }

  if (!cfg.videoUrl && cfg.videoPath) {
    cfg.videoUrl = `${cdn}/${cfg.videoPath}`;
  }

  return cfg;
}
