// ============================================================================
//  Interactive page flow — the same behavior as the original single-file
//  birthday page: petals, page-swap navigation, quiz click handling
//  (wrong-answer modal fires on click, not on submit), confetti bursts,
//  and the final scrollable flow reveal.
//
//  `initPageFlow()` must be called AFTER template.js has rendered the
//  quiz + memories DOM, otherwise the querySelectors below miss them.
// ============================================================================

export function initPageFlow() {

  /* ---------- Floating petals ---------- */
  const glyphs = ['🌸','🌷','🌺','✿','🌹','❀'];
  const petalsRoot = document.getElementById('petals');
  if (petalsRoot && !petalsRoot.dataset.rendered) {
    for (let i = 0; i < 18; i++) {
      const p = document.createElement('div');
      p.className = 'petal';
      p.textContent = glyphs[Math.floor(Math.random() * glyphs.length)];
      p.style.left = Math.random() * 100 + 'vw';
      p.style.animationDuration = (10 + Math.random() * 14) + 's';
      p.style.animationDelay = (-Math.random() * 12) + 's';
      p.style.fontSize = (14 + Math.random() * 20) + 'px';
      p.style.opacity = (0.35 + Math.random() * 0.5).toFixed(2);
      petalsRoot.appendChild(p);
    }
    petalsRoot.dataset.rendered = '1';
  }

  /* ---------- Page navigation (one page at a time) ---------- */
  function showPage(id) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const target = document.getElementById(id);
    if (target) target.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  /* ---------- Quiz click handling ----------
     Wrong click → open modal + clear selection.
     Right click → mark option selected. */
  document.querySelectorAll('.question').forEach(q => {
    q.querySelectorAll('.option').forEach(opt => {
      opt.addEventListener('click', () => {
        const correct = parseInt(q.dataset.correct, 10);
        const chosen  = parseInt(opt.dataset.i, 10);

        if (chosen !== correct) {
          q.querySelectorAll('.option').forEach(o => o.classList.remove('selected'));
          openModal();
          return;
        }
        q.querySelectorAll('.option').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
      });
    });
  });

  function openModal()  { document.getElementById('wrong-modal').classList.add('show'); }
  function closeModal() { document.getElementById('wrong-modal').classList.remove('show'); }

  /* ---------- Buttons ---------- */
  const startBtn      = document.getElementById('start-btn');
  const submitBtn     = document.getElementById('submit-btn');
  const celebrateBtn  = document.getElementById('celebrate-btn');
  const wrongCloseBtn = document.getElementById('wrong-close-btn');

  if (startBtn)      startBtn.addEventListener('click',      () => showPage('quiz-screen'));
  if (wrongCloseBtn) wrongCloseBtn.addEventListener('click', closeModal);

  if (submitBtn) submitBtn.addEventListener('click', () => {
    const questions = document.querySelectorAll('.question');
    for (const q of questions) {
      if (!q.querySelector('.option.selected')) {
        alert('اختاري إجابة لكل سؤال 🌸');
        return;
      }
    }
    // Small celebration confetti when answers confirmed
    if (typeof confetti === 'function') {
      confetti({
        particleCount: 120, spread: 90, origin: { y: 0.6 },
        colors: ['#a13b58', '#f7d9e1', '#efc8d2', '#4a1f2e', '#ffffff'],
      });
    }
    showPage('celebrate-screen');
  });

  if (celebrateBtn) celebrateBtn.addEventListener('click', () => {
    // Big confetti burst
    if (typeof confetti === 'function') {
      const duration = 3000;
      const end = Date.now() + duration;
      (function frame() {
        confetti({ particleCount: 5, angle: 60,  spread: 55, origin: { x: 0 },
          colors: ['#a13b58', '#f7d9e1', '#efc8d2', '#4a1f2e', '#ffd700'] });
        confetti({ particleCount: 5, angle: 120, spread: 55, origin: { x: 1 },
          colors: ['#a13b58', '#f7d9e1', '#efc8d2', '#4a1f2e', '#ffd700'] });
        if (Date.now() < end) requestAnimationFrame(frame);
      })();
    }

    // Swap to the final flow (Memories → Letter → Video scroll together)
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById('final-flow').classList.add('active');
    document.body.classList.add('scrollable');
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  });

  /* ---------- Video fallback (only for <video> element, not iframe) ---------- */
  const vid = document.querySelector('#video-screen video');
  const vidFallback = document.getElementById('video-fallback');
  if (vid && vidFallback) {
    vid.addEventListener('error', () => {
      vid.style.display = 'none';
      vidFallback.style.display = 'flex';
    });
  }
}
