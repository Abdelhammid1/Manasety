/* Manasety — light progressive enhancement. Everything works without JS except the tab switcher. */
(function () {
  'use strict';
  var d = document;

  function track(gaEvent, gaParams, fbEvent, fbParams, custom) {
    try { if (typeof window.gtag === 'function') window.gtag('event', gaEvent, gaParams || {}); } catch (e) {}
    try {
      if (typeof window.fbq === 'function') {
        if (fbEvent) window.fbq('track', fbEvent, fbParams || {});
        if (custom) window.fbq('trackCustom', custom[0], custom[1]);
      }
    } catch (e) {}
  }

  /* mobile menu */
  var toggle = d.querySelector('.nav-toggle');
  var menu = d.getElementById('mobile-menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var open = menu.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    menu.addEventListener('click', function (e) {
      if (e.target.closest('a')) { menu.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); }
    });
  }

  /* feature tabs (roving tabindex + arrow keys, RTL aware) */
  d.querySelectorAll('[role="tablist"]').forEach(function (list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function select(tab) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        var panel = d.getElementById(t.getAttribute('aria-controls'));
        if (panel) panel.hidden = !on;
      });
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(t); });
      t.addEventListener('keydown', function (e) {
        var rtl = d.documentElement.dir === 'rtl';
        var next = { ArrowLeft: rtl ? 1 : -1, ArrowRight: rtl ? -1 : 1 }[e.key];
        if (e.key === 'Home') next = -i; else if (e.key === 'End') next = tabs.length - 1 - i;
        if (next === undefined) return;
        e.preventDefault();
        var target = tabs[(i + next + tabs.length) % tabs.length];
        select(target); target.focus();
      });
    });
  });

  /* reveal on scroll */
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } });
    }, { rootMargin: '0px 0px -8% 0px' });
    d.querySelectorAll('.rv').forEach(function (el) { io.observe(el); });
  } else {
    d.querySelectorAll('.rv').forEach(function (el) { el.classList.add('in'); });
  }

  /* UTM capture: first touch kept for the session */
  var UTM = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'];
  var stored = {};
  try { stored = JSON.parse(sessionStorage.getItem('mn_utm') || '{}'); } catch (e) {}
  var qs = new URLSearchParams(location.search);
  if (UTM.some(function (k) { return qs.get(k); })) {
    stored = {};
    UTM.forEach(function (k) { if (qs.get(k)) stored[k] = qs.get(k); });
    stored.referrer = d.referrer || '';
    stored.landing_path = location.pathname + location.search;
    try { sessionStorage.setItem('mn_utm', JSON.stringify(stored)); } catch (e) {}
  }

  /* demo form */
  var form = d.getElementById('demo-form');
  if (form) {
    var msg = form.querySelector('.form-msg');
    Object.keys(stored).forEach(function (k) { if (form.elements[k]) form.elements[k].value = stored[k]; });
    if (form.elements.referrer && !form.elements.referrer.value) form.elements.referrer.value = d.referrer || '';
    if (form.elements.landing_path && !form.elements.landing_path.value) form.elements.landing_path.value = location.pathname + location.search;

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      msg.className = 'form-msg'; msg.textContent = '';
      if (!form.checkValidity()) {
        msg.className = 'form-msg err';
        msg.textContent = 'من فضلك أكمل الحقول المطلوبة.';
        var bad = form.querySelector(':invalid'); if (bad) bad.focus();
        return;
      }
      track('click_submit_form', { event_category: 'Form' });
      var btn = form.querySelector('[type="submit"]');
      btn.disabled = true;
      fetch(form.action, { method: 'POST', body: new FormData(form), headers: { Accept: 'application/json' }, credentials: 'same-origin' })
        .then(function (r) {
          return r.json().catch(function () { return { ok: false, errors: [] }; })
            .then(function (j) { return { ok: r.ok, body: j }; });
        })
        .then(function (res) {
          if (!res.ok || !res.body.ok) throw new Error((res.body.errors || []).join(' ') || 'error');
          track('generate_lead', { event_category: 'Form' }, 'Lead', { content_name: 'Demo Request', content_category: 'Landing Page' });
          window.location.href = '/thank-you.html';
        })
        .catch(function (err) {
          btn.disabled = false;
          msg.className = 'form-msg err';
          msg.textContent = err.message && err.message !== 'error' ? err.message : 'تعذر الإرسال. حاول مرة أخرى أو راسلنا على واتساب.';
        });
    });
  }

  /* CTA + WhatsApp tracking (same event names as the previous site) */
  d.addEventListener('click', function (e) {
    var a = e.target.closest('a');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (/wa\.me|whatsapp/.test(href)) {
      var source = a.getAttribute('data-wa-source') || 'landing-website';
      track('click_whatsapp', { event_category: 'Contact', event_label: source }, 'Lead',
        { content_name: 'WhatsApp Click', content_category: 'Landing Page WhatsApp', source: source },
        ['WhatsAppClick', { source: source }]);
    } else if (/#contact$/.test(href)) {
      track('click_book_session', { event_category: 'CTA' });
    }
  });

  /* consent bar: integrations flagged "requires consent" stay inert until accepted */
  var bar = d.getElementById('cookie-bar');
  function activate() {
    d.querySelectorAll('template[data-consent-code]').forEach(function (tpl) {
      var frag = tpl.content.cloneNode(true);
      frag.querySelectorAll('script').forEach(function (old) {
        var s = d.createElement('script');
        Array.prototype.forEach.call(old.attributes, function (at) { s.setAttribute(at.name, at.value); });
        s.text = old.text;
        old.parentNode.replaceChild(s, old);
      });
      tpl.parentNode.insertBefore(frag, tpl);
      tpl.remove();
    });
  }
  if (bar) {
    var choice = null;
    try { choice = localStorage.getItem('mn_consent'); } catch (e) {}
    if (choice === 'yes') activate();
    else if (choice !== 'no') bar.hidden = false;
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('[data-consent]');
      if (!b) return;
      var v = b.getAttribute('data-consent');
      try { localStorage.setItem('mn_consent', v); } catch (err) {}
      bar.hidden = true;
      if (v === 'yes') activate();
    });
  }
})();
