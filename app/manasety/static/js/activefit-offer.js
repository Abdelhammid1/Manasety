/* ActiveFit gyms campaign - /activefit only, and only for visitors from utm_campaign=activefit_gyms.
   To close the offer set OFFER_ACTIVE = false: banner gone, WhatsApp message back to normal, page back to normal. */
var OFFER_ACTIVE = true;
(function () {
  'use strict';
  if (!OFFER_ACTIVE) return;
  var d = document;
  var CAMPAIGN = 'activefit_gyms';
  var OFFER_NAME = 'عرض الجيم';
  var WA_NUMBER = '201044203322';
  var KEY = 'mn_af_offer';
  var TTL = 7 * 24 * 60 * 60 * 1000;
  var KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content'];

  if (location.pathname.replace(/\/+$/, '') !== '/activefit') return;

  function read(store) {
    try {
      var o = JSON.parse(store.getItem(KEY) || 'null');
      if (o && o.utm_campaign === CAMPAIGN && o.ts && Date.now() - o.ts < TTL) return o;
    } catch (e) {}
    return null;
  }
  function save(o) {
    var s = JSON.stringify(o);
    try { sessionStorage.setItem(KEY, s); } catch (e) {}
    try { localStorage.setItem(KEY, s); } catch (e) {}
  }

  /* 1) capture + persist UTM (7 days) */
  var qs = new URLSearchParams(location.search);
  var urlCampaign = qs.get('utm_campaign');
  var data = null;
  if (urlCampaign === CAMPAIGN) {
    data = { ts: Date.now() };
    KEYS.forEach(function (k) { data[k] = qs.get(k) || ''; });
    save(data);
  } else if (!urlCampaign) {
    data = read(sessionStorage) || read(localStorage);
  }
  if (!data) return;  /* normal visitor: page untouched */

  window.__afOffer = { utm_content: data.utm_content || '' };  /* read by site.js for the Lead params */
  d.documentElement.classList.add('af-offer');

  /* 2) banner + headline */
  var st = d.createElement('style');
  st.textContent =
    '.af-banner{position:sticky;top:0;z-index:1000;background:#1849A9;color:#fff;text-align:center;font-weight:700;font-size:14px;line-height:1.7;padding:10px 14px}' +
    'html.af-offer .dom-switch,html.af-offer .nav-links,html.af-offer .nav-toggle,html.af-offer .mobile-menu,html.af-offer .lang-switch,html.af-offer .social-float{display:none!important}';
  d.head.appendChild(st);

  var banner = d.createElement('div');
  banner.className = 'af-banner';
  banner.setAttribute('role', 'note');
  banner.textContent = '🎁 أول 20 نادي يشتركوا: تجربة 14 يوم + نقل بيانات ناديك مجانًا + خصم 30% على الاشتراك السنوي';
  d.body.insertBefore(banner, d.body.firstChild);
  var header = d.querySelector('.site-header');
  function place() { if (header) header.style.top = banner.offsetHeight + 'px'; }
  place();
  window.addEventListener('resize', place);

  var h1 = d.querySelector('.hero h1');
  if (h1) h1.textContent = 'كام عضو دخل عندك الجيم النهارده؟';
  var lead = d.querySelector('.hero .lead');
  if (lead) lead.textContent = 'ActiveFit يرفض الاشتراك المنتهي عند الباب تلقائيًا، ويقفّل كاشك آخر اليوم. وإحنا ننقل بياناتك ونجهّز ناديك مجانًا.';
  var ghost = d.querySelector('.hero-ctas .btn-ghost');
  if (ghost) ghost.remove();  /* "visit ActiveFit site" button */

  d.querySelectorAll('a.btn[href="#contact"]').forEach(function (a) {
    if (!a.children.length) a.textContent = 'احجز عرض الجيم';
  });
  var navCta = d.querySelector('.site-header .nav .btn-primary');
  if (navCta) {
    navCta.setAttribute('href', '#contact');
    if (!navCta.children.length) navCta.textContent = 'احجز عرض الجيم';
  }

  /* 5) plug the leaks: everything leads back to the form */
  d.querySelectorAll('a[href*="activefit.manasety.ai"]').forEach(function (a) { a.setAttribute('href', '#contact'); });
  d.querySelectorAll('a[href$="#pricing"]').forEach(function (a) { a.setAttribute('href', '#contact'); });
  d.querySelectorAll('main a[href^="/"]').forEach(function (a) {
    var h = a.getAttribute('href');
    if (h.indexOf('//') !== 0 && !/^\/(privacy|terms|refund)\.html/.test(h)) a.setAttribute('href', '#contact');
  });
  var brand = d.querySelector('.site-header .brand');
  if (brand) brand.setAttribute('href', '#top');
  d.querySelectorAll('.site-footer h2').forEach(function (h) {
    if (h.textContent.trim() === 'صفحاتنا' && h.parentElement) h.parentElement.style.display = 'none';
  });

  var bubble = d.querySelector('.wa-bubble');
  if (bubble) {
    var BUBBLE = 'مرحباً.. عايز تعرف تفاصيل عرض الجيم؟';
    var done = false;
    Array.prototype.forEach.call(bubble.childNodes, function (n) {
      if (!done && n.nodeType === 3 && n.nodeValue.trim()) { n.nodeValue = BUBBLE; done = true; }
    });
    if (!done && !bubble.children.length) bubble.textContent = BUBBLE;
  }

  /* 3) WhatsApp prefilled message on every wa.me link of the Egypt number */
  var msg = [
    'السلام عليكم',
    'أنا شفت إعلان ActiveFit على فيسبوك وعايز آخد *عرض الجيم*',
    '(تجربة 14 يوم + نقل بيانات ناديي مجانًا + خصم 30% على الاشتراك السنوي)',
    '',
    'اسم ناديي:',
    'عدد الفروع:'
  ].join('\n');
  var waHref = 'https://wa.me/' + WA_NUMBER + '?text=' + encodeURIComponent(msg);
  d.querySelectorAll('a[href*="wa.me/' + WA_NUMBER + '"]').forEach(function (a) { a.setAttribute('href', waHref); });

  /* 4) form: hidden utm_* + offer, submit label */
  var form = d.getElementById('demo-form');
  if (form) {
    var put = function (name, value) {
      var el = form.elements[name];
      if (!el) { el = d.createElement('input'); el.type = 'hidden'; el.name = name; form.appendChild(el); }
      el.value = value;
    };
    KEYS.forEach(function (k) { put(k, data[k] || ''); });
    put('offer', OFFER_NAME);
    var btn = form.querySelector('[type="submit"]');
    if (btn) btn.textContent = 'احجز عرض الجيم';
  }
})();
