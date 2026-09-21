// ============================================================================
//  Template renderer — takes a birthday config object and populates every
//  slot in the page (name, quiz, memories, letter, video, wrong-answer
//  modal). Stage A: pulls from a hard-coded DEMO_CONFIG. Stage B: fetches
//  the doc from Firestore based on ?for=<slug>.
// ============================================================================

import { initPageFlow } from "./page-flow.js";
import { getSlug, loadBirthday, mapPathsToUrls } from "./loader.js";
import { CONFIG } from "../config.js";

/* ---------- Defaults: any missing field falls back to these ---------- */
export const DEFAULTS = {
  name: "Someone",
  eyebrowText: "A Special Day",
  celebrationSub: "✨ Let the celebration begin",
  startButtonText: "ابدأ الكويز",
  quizTitle: "Quick Quiz",
  quizSub: "جاوبي صح عشان تعدي",
  confirmButtonText: "تأكيد الإجابات",
  wrongEmoji: "😠",
  wrongMessage: "طب مفيش عيييد ميلاد 🎂",
  wrongButtonText: "حاولي تاني",
  celebrateEyebrow: "✦ A Celebration ✦",
  celebrationTitle: "Let's Celebrate",
  celebrateButtonText: "CELEBRATE! 🎉",
  memoriesEyebrow: "✦ Memories ✦",
  memoriesTitle: "Our Beautiful Moments",
  letterEyebrow: "✦ من القلب",
  letterName: "",
  letterAr: "",
  letterEn: "",
  signatureEn: "Yours ❤️",
  signatureAr: "",
  videoEyebrow: "✦ A Message ✦",
  videoTitle: "🎬 Watch This",
  videoUrl: "",
};

/* ---------- Stage-A demo config — mirrors the original hard-coded page ---------- */
export const DEMO_CONFIG = {
  name: "Sara",
  quiz: [
    { question: "بتحبي ايه أكتر؟",
      options: ["الشوكولاتة", "الورد", "انا"],
      correctIndex: 2 },
    { question: "لو جيت في يوم زعلانة.. هعمل ايه؟",
      options: ["تسيبني في حالي", "تحضني وتقولي كل حاجة هتبقى تمام", "تقولي اتفرجي على فيلم"],
      correctIndex: 1 },
    { question: "لو كسرتي حاجة غالية عليّا.. هقولك ايه؟",
      options: ["ولا يهمك حبيبتي، انتي أغلى", "معلش بس دي كانت غالية", "خلاص هزعل منك شوية"],
      correctIndex: 0 },
  ],
  memories: [
    { url: "", dateLabel: "NOV 2024 · 23" },
    { url: "", dateLabel: "MAY 2025 · 04" },
    { url: "", dateLabel: "OCT 2024 · 24" },
    { url: "", dateLabel: "OCT 2024 · 06" },
  ],
  letterName: "سارة حبيبتي",
  letterAr:
    "كل سنة وانتي طيبة يا حبيبتي، وكل سنة وانتي السبب في كل الراحة والسعادة اللي بحس بيها. " +
    "يارب تفضلي دايماً معايا، ونعيش سوا أيام كتير حلوة وخفيفة، وأفضل أشوفك مبسوطة ومرتاحة طول العمر ❤️",
  letterEn:
    "I really can't explain how much you mean to me. With you, everything feels softer, safer, and happier. " +
    "Your smile, your voice, and even the smallest details you do always make my heart feel full.\n\n" +
    "I hope we always stay this close, sharing our days, our little moments, and building beautiful memories together. " +
    "And no matter what happens, I just want you to know that you'll always have a very special place in my heart ❤️",
  signatureEn: "Yours ❤️",
  signatureAr: "— اسمك هنا",
  videoUrl: "",
};

/* ------------------------------ Helpers ------------------------------ */

const $ = (id) => document.getElementById(id);

function set(id, value) {
  const el = $(id);
  if (el && value != null) el.textContent = value;
}

/** URL heuristic: mp4 → <video>, YouTube → embed iframe, else → assume embed. */
function videoTypeFor(url) {
  if (!url) return "none";
  const lc = url.toLowerCase();
  if (lc.endsWith(".mp4") || lc.endsWith(".webm") || lc.endsWith(".mov")) return "file";
  if (/youtube\.com|youtu\.be/.test(lc)) return "youtube";
  return "iframe";
}

function toYoutubeEmbed(url) {
  const m = url.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/))([\w-]{6,})/);
  return m ? `https://www.youtube.com/embed/${m[1]}` : url;
}

/* ------------------------------ Renderers ------------------------------ */

function renderHero(cfg) {
  set("hero-eyebrow", cfg.eyebrowText);
  set("hero-name",    cfg.name + "'s");
  set("hero-subtitle", cfg.celebrationSub);
  const startBtn = $("start-btn");
  if (startBtn) startBtn.innerHTML = `${cfg.startButtonText} &nbsp;→`;
}

function renderQuiz(cfg) {
  set("quiz-title-name", cfg.name);
  set("quiz-sub", cfg.quizSub);
  set("submit-btn", cfg.confirmButtonText);

  const container = $("quiz-questions");
  if (!container) return;
  container.innerHTML = "";

  const labels = ["السؤال الأول", "السؤال الثاني", "السؤال الثالث", "السؤال الرابع", "السؤال الخامس"];

  cfg.quiz.forEach((q, qi) => {
    const qDiv = document.createElement("div");
    qDiv.className = "question";
    qDiv.dataset.q = String(qi);
    qDiv.dataset.correct = String(q.correctIndex);

    const label = document.createElement("div");
    label.className = "q-label";
    label.textContent = labels[qi] || `السؤال ${qi + 1}`;

    const text = document.createElement("div");
    text.className = "q-text";
    text.textContent = q.question;

    const options = document.createElement("div");
    options.className = "options";
    q.options.forEach((opt, oi) => {
      const optDiv = document.createElement("div");
      optDiv.className = "option";
      optDiv.dataset.i = String(oi);
      const span = document.createElement("span");
      span.textContent = opt;
      const radio = document.createElement("div");
      radio.className = "radio";
      optDiv.append(span, radio);
      options.appendChild(optDiv);
    });

    qDiv.append(label, text, options);
    if (qi > 0) {
      const divider = document.createElement("div");
      divider.className = "q-divider";
      container.appendChild(divider);
    }
    container.appendChild(qDiv);
  });
}

function renderCelebrate(cfg) {
  set("celebrate-eyebrow", cfg.celebrateEyebrow);
  set("celebrate-name",    cfg.name + "!");
  const btn = $("celebrate-btn");
  if (btn) btn.textContent = cfg.celebrateButtonText;
  // The "Let's Celebrate" prefix text is set once in HTML; the em holds the name.
  set("celebrate-prefix", cfg.celebrationTitle);
}

function renderMemories(cfg) {
  set("memories-eyebrow", cfg.memoriesEyebrow);
  set("memories-title-name", cfg.name);
  set("memories-title-prefix", cfg.memoriesTitle);

  const grid = $("memories-grid");
  if (!grid) return;
  grid.innerHTML = "";

  cfg.memories.forEach((m, i) => {
    const wrap = document.createElement("div");
    wrap.className = "memory";

    const imgWrap = document.createElement("div");
    imgWrap.className = "img-wrap";
    if (m.url) {
      const img = document.createElement("img");
      img.src = m.url;
      img.alt = m.dateLabel || `photo ${i + 1}`;
      img.loading = "lazy";
      img.addEventListener("error", () => {
        imgWrap.innerHTML = `<span>photo ${i + 1}</span>`;
      });
      imgWrap.appendChild(img);
    } else {
      imgWrap.innerHTML = `<span>photo ${i + 1}</span>`;
    }

    const caption = document.createElement("div");
    caption.className = "caption";
    caption.textContent = m.dateLabel || "";

    wrap.append(imgWrap, caption);
    grid.appendChild(wrap);
  });
}

function renderLetter(cfg) {
  set("letter-eyebrow",  cfg.letterEyebrow);
  set("letter-name",     cfg.letterName);
  set("letter-ar",       cfg.letterAr);
  set("letter-en",       cfg.letterEn);
  set("signature-en",    cfg.signatureEn);
  set("signature-ar",    cfg.signatureAr);
}

function renderVideo(cfg) {
  set("video-eyebrow", cfg.videoEyebrow);
  set("video-title",   cfg.videoTitle);

  const container = $("video-container");
  if (!container) return;
  container.innerHTML = "";

  const kind = videoTypeFor(cfg.videoUrl);
  if (kind === "none") {
    container.innerHTML = `
      <div class="video-placeholder">
        <div>No video attached yet.<br>Admin can add one from the editor.</div>
      </div>`;
    return;
  }

  if (kind === "file") {
    const v = document.createElement("video");
    v.controls = true;
    v.preload  = "metadata";
    const src = document.createElement("source");
    src.src = cfg.videoUrl;
    src.type = "video/mp4";
    v.appendChild(src);
    container.appendChild(v);
    const fb = document.createElement("div");
    fb.className = "video-placeholder";
    fb.id = "video-fallback";
    fb.style.display = "none";
    fb.innerHTML = `<div>Could not load the video.<br>Check the URL in the admin panel.</div>`;
    container.appendChild(fb);
    return;
  }

  const iframe = document.createElement("iframe");
  iframe.src = kind === "youtube" ? toYoutubeEmbed(cfg.videoUrl) : cfg.videoUrl;
  iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
  iframe.allowFullscreen = true;
  container.appendChild(iframe);
}

function renderWrongModal(cfg) {
  set("wrong-emoji",     cfg.wrongEmoji);
  set("wrong-message",   cfg.wrongMessage);
  set("wrong-close-btn", cfg.wrongButtonText);
}

/* ------------------------------ Entry point ------------------------------ */

export function renderTemplate(rawConfig) {
  const cfg = { ...DEFAULTS, ...rawConfig };
  // Guarantee at least an empty quiz + memories array so renderers don't blow up.
  cfg.quiz     = Array.isArray(cfg.quiz)     ? cfg.quiz     : [];
  cfg.memories = Array.isArray(cfg.memories) ? cfg.memories : [];

  renderHero(cfg);
  renderQuiz(cfg);
  renderCelebrate(cfg);
  renderMemories(cfg);
  renderLetter(cfg);
  renderVideo(cfg);
  renderWrongModal(cfg);

  document.title = `Happy Birthday, ${cfg.name}`;
}

/* ------------------------------ Bootstrap ------------------------------ */
//   Stage B: resolve slug → fetch JSON from birthday-media on GitHub →
//   render. Falls back to DEMO_CONFIG only when slug === "demo" AND the
//   fetch fails (useful for local dev before any JSON is committed).

function showLoading(msg = "Loading…") {
  hideLoading();
  const el = document.createElement("div");
  el.id = "loading";
  el.className = "loading";
  el.textContent = msg;
  document.body.appendChild(el);
}
function hideLoading() {
  const el = document.getElementById("loading");
  if (el) el.remove();
}

function showNotFound(slug) {
  hideLoading();
  const main = document.querySelector("main");
  if (!main) return;
  main.innerHTML = `
    <section class="screen page active">
      <div class="container">
        <div class="notfound-card">
          <h2>Birthday not found</h2>
          <p>
            No birthday exists at <code>${slug ? slug : "(no slug)"}</code> yet.
          </p>
          <p>
            To create one, open the admin panel at
            <code>admin.${CONFIG.domain}</code>.
          </p>
        </div>
      </div>
    </section>`;
}

async function bootstrap() {
  showLoading("Loading birthday…");
  const slug = getSlug();

  if (!slug) {
    showNotFound(null);
    return;
  }

  let cfg = await loadBirthday(slug);

  // Local-dev convenience: if the slug is "demo" and no JSON is committed
  // yet, fall back to the hard-coded demo.
  if (!cfg && slug === "demo") {
    cfg = { ...DEMO_CONFIG, slug: "demo" };
  }

  if (!cfg) {
    showNotFound(slug);
    return;
  }

  cfg = mapPathsToUrls(cfg);
  hideLoading();
  renderTemplate(cfg);
  initPageFlow();
}

bootstrap();
