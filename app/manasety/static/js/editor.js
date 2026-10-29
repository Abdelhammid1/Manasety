/* Rich text editor for the dashboard: contenteditable + hidden textarea, no external library.
   Everything here only edits; the server re-sanitises on save (clean_rich) and again on display. */
(function () {
  'use strict';
  var d = document;
  var csrf = (d.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var each = function (list, fn) { Array.prototype.forEach.call(list, fn); };

  /* ───────── paste cleaning (Word, Google Docs, websites, ChatGPT) ───────── */

  var DROP = /^(SCRIPT|STYLE|META|LINK|TITLE|HEAD|XML|TEMPLATE|NOSCRIPT|OBJECT|EMBED|SVG|CANVAS|BUTTON|INPUT|SELECT|TEXTAREA|OPTION|FORM|NAV|ASIDE)$/;
  var CONTAINER = /^(DIV|SECTION|ARTICLE|MAIN|HEADER|FOOTER|BODY|CENTER|FIGURE|DETAILS|SUMMARY|ADDRESS)$/;
  var KEEP = { BLOCKQUOTE: 1, HR: 1, BR: 1, UL: 1, OL: 1, LI: 1, CODE: 1, SUP: 1, SUB: 1, U: 1, S: 1, DL: 1, DT: 1, DD: 1, FIGCAPTION: 1 };
  var BLOCK_SEL = 'p,div,h1,h2,h3,h4,h5,h6,ul,ol,li,table,blockquote,pre,hr,section,article,header,footer,figure';
  var INLINE = /^(#text|STRONG|EM|B|I|U|S|A|CODE|SUP|SUB|BR|SPAN|IMG|BDI)$/;
  var BULLET_RE = /^[\s ]*(?:[•·▪◦‣●○■•]|[-–*](?=[\s ]))[\s ]*/;
  var NUM_RE = /^[\s ]*(?:\d+|[٠-٩]+)[.)\-][\s ]+/;
  var CHECK_RE = /^[\s ]*[☐☑☒✓✔]/;
  var SAFE_HREF = /^(https?:\/\/|\/|#|mailto:|tel:)/i;
  var YT_RE = /^https:\/\/www\.youtube(-nocookie)?\.com\/embed\/[\w-]{11}/;

  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function styleOf(el) { return (el.getAttribute && el.getAttribute('style') || '').toLowerCase(); }
  function unwrap(el) { var p = el.parentNode; if (!p) return; while (el.firstChild) p.insertBefore(el.firstChild, el); p.removeChild(el); }
  function rename(el, tag) { var n = el.ownerDocument.createElement(tag); while (el.firstChild) n.appendChild(el.firstChild); el.parentNode.replaceChild(n, el); return n; }
  function textOf(el) { return (el.textContent || '').replace(/ /g, ' ').trim(); }

  /* Word writes lists as <p style="mso-list:l0 level2 lfo1"> with the marker inside <!--[if !supportLists]-->. */
  function wordLists(doc) {
    var state = null;
    each(doc.body.querySelectorAll('p, h1, h2, h3, h4, h5, h6'), function (p) {
      var m = styleOf(p).match(/mso-list:\s*l\d+\s+level(\d+)/);
      if (!m) return;
      var marker = '';
      // marker = everything between the supportLists comments (or the mso-list:Ignore span)
      var n = p.firstChild, inMarker = false, kill = [];
      while (n) {
        if (n.nodeType === 8 && /\[if !supportLists\]/i.test(n.data)) inMarker = true;
        else if (n.nodeType === 8 && /\[endif\]/i.test(n.data)) { kill.push(n); inMarker = false; n = n.nextSibling; continue; }
        if (inMarker) { kill.push(n); marker += n.textContent || ''; }
        n = n.nextSibling;
      }
      each(p.querySelectorAll('span'), function (s) { if (/mso-list:\s*ignore/.test(styleOf(s))) { marker += s.textContent; kill.push(s); } });
      kill.forEach(function (k) { if (k.parentNode) k.parentNode.removeChild(k); });
      marker = marker.replace(/ /g, ' ').trim();
      var type = /^[(]?([0-9٠-٩]+|[a-z]|[ivxl]+)[.)]/i.test(marker) ? 'ol' : 'ul';
      var level = Math.min(+m[1] || 1, 2);
      if (!state || p.previousElementSibling !== state.root) {
        state = { root: doc.createElement(type), stack: [] };
        p.parentNode.insertBefore(state.root, p);
        state.stack = [state.root];
      }
      while (state.stack.length > level) state.stack.pop();
      while (state.stack.length < level) {
        var top = state.stack[state.stack.length - 1];
        var sub = doc.createElement(type);
        (top.lastElementChild || top).appendChild(sub);
        state.stack.push(sub);
      }
      var li = doc.createElement('li');
      while (p.firstChild) li.appendChild(p.firstChild);
      state.stack[state.stack.length - 1].appendChild(li);
      p.parentNode.removeChild(p);
    });
  }

  /* Word Heading 1 / Docs "Heading 1" → H2 (the page H1 is the article title), next level → H3, deeper → H4. */
  function headingMap(doc) {
    var min = 7;
    each(doc.body.querySelectorAll('h1,h2,h3,h4,h5,h6'), function (h) { min = Math.min(min, +h.tagName[1]); });
    return function (level) { return 'h' + Math.min(2 + (level - (min === 7 ? 1 : min)), 4); };
  }

  function isNormalWeight(el) { return /font-weight:\s*(normal|[1-4]00)\b/.test(styleOf(el)); }
  function isBoldStyle(el) { return /font-weight:\s*(bold|bolder|[6-9]00)\b/.test(styleOf(el)); }
  function isItalicStyle(el) { return /font-style:\s*italic/.test(styleOf(el)); }

  function cleanHref(href) {
    href = (href || '').trim();
    var g = href.match(/^https?:\/\/www\.google\.[a-z.]+\/url\?q=([^&]+)/);  // Docs wraps links in a redirect
    if (g) { try { href = decodeURIComponent(g[1]); } catch (e) { /* keep as is */ } }
    return SAFE_HREF.test(href) && !/^javascript:/i.test(href) ? href : '';
  }

  function cleanNodes(target, src, ctx) {
    each(src.childNodes, function (n) {
      if (n.nodeType === 3) {
        var t = n.nodeValue.replace(/[ \r\n\t]/g, ' ').replace(/ {2,}/g, ' ');
        if (t) target.appendChild(d.createTextNode(t));
        return;
      }
      if (n.nodeType !== 1) return;  // comments, Word conditional blocks
      var tag = n.tagName.toUpperCase(), el = null, holder;
      if (DROP.test(tag)) return;
      if (/^H[1-6]$/.test(tag)) {
        el = d.createElement(ctx.heading(+tag[1]));
        var hid = n.getAttribute('id');
        if (hid && /^[\w-]{1,60}$/.test(hid) && ctx.keepIds) el.id = hid;
      } else if (tag === 'P') {
        el = d.createElement(/MsoTitle|MsoSubtitle/.test(n.className || '') ? 'h2' : 'p');
        if ((n.getAttribute('dir') || '').toLowerCase() === 'ltr') el.setAttribute('dir', 'ltr');
      } else if (CONTAINER.test(tag)) {
        if (n.querySelector(BLOCK_SEL)) { cleanNodes(target, n, ctx); return; }
        el = d.createElement('p');
      } else if (tag === 'PRE') {
        el = d.createElement('pre'); el.textContent = n.textContent; target.appendChild(el); return;
      } else if (tag === 'TABLE') {
        target.appendChild(cleanTable(n, ctx)); return;
      } else if (tag === 'A') {
        var href = cleanHref(n.getAttribute('href'));
        if (!href) { cleanNodes(target, n, ctx); return; }
        el = d.createElement('a'); el.setAttribute('href', href);
      } else if (tag === 'B' || tag === 'STRONG') {
        if (isNormalWeight(n) || n.querySelector(BLOCK_SEL)) { cleanNodes(target, n, ctx); return; }  // Docs wraps everything in <b style="font-weight:normal">
        el = d.createElement('strong');
      } else if (tag === 'I' || tag === 'EM') {
        if (/font-style:\s*normal/.test(styleOf(n)) || n.querySelector(BLOCK_SEL)) { cleanNodes(target, n, ctx); return; }
        el = d.createElement('em');
      } else if (tag === 'IMG') {
        var src2 = n.getAttribute('src') || '';
        if (src2.indexOf(location.origin + '/media/') === 0) src2 = src2.slice(location.origin.length);
        if (/^\/media\//.test(src2)) {
          el = d.createElement('img'); el.setAttribute('src', src2); el.setAttribute('alt', n.getAttribute('alt') || ''); el.setAttribute('loading', 'lazy');
          target.appendChild(el);
        } else { ctx.skippedImages++; }
        return;
      } else if (tag === 'IFRAME') {
        if (YT_RE.test(n.getAttribute('src') || '')) {
          el = d.createElement('iframe'); el.setAttribute('src', n.getAttribute('src')); el.setAttribute('title', 'YouTube');
          el.setAttribute('loading', 'lazy'); el.setAttribute('allowfullscreen', ''); target.appendChild(el);
        }
        return;
      } else if (KEEP[tag]) {
        el = d.createElement(tag.toLowerCase());
      } else if (tag === 'SPAN' || tag === 'FONT') {
        if (n.querySelector(BLOCK_SEL)) { cleanNodes(target, n, ctx); return; }
        var st = styleOf(n), wraps = [];
        if (isBoldStyle(n)) wraps.push('strong');
        if (isItalicStyle(n)) wraps.push('em');
        if (/vertical-align:\s*super/.test(st)) wraps.push('sup');
        if (/vertical-align:\s*sub/.test(st)) wraps.push('sub');
        var dir = (n.getAttribute('dir') || '').toLowerCase();
        if (dir === 'ltr' && ctx.keepIds) { var sp = d.createElement('span'); sp.setAttribute('dir', 'ltr'); wraps.unshift(sp); }
        holder = target;
        wraps.forEach(function (w) { var x = typeof w === 'string' ? d.createElement(w) : w; holder.appendChild(x); holder = x; });
        cleanNodes(holder, n, ctx);
        return;
      } else {
        cleanNodes(target, n, ctx); return;  // unknown/namespaced tags (o:p, font, …): keep the text only
      }
      cleanNodes(el, n, ctx);
      target.appendChild(el);
    });
  }

  function cleanTable(src, ctx) {
    var table = d.createElement('table'), thead = null, tbody = d.createElement('tbody');
    each(src.querySelectorAll('tr'), function (tr) {
      if (tr.closest('table') !== src) return;  // rows of nested tables are handled by their own table
      var inHead = tr.parentNode && tr.parentNode.tagName === 'THEAD';
      var row = d.createElement('tr');
      each(tr.children, function (c) {
        if (!/^T[DH]$/.test(c.tagName)) return;
        var cell = d.createElement(inHead ? 'th' : c.tagName.toLowerCase());
        ['colspan', 'rowspan'].forEach(function (a) {
          var v = c.getAttribute(a); if (v && /^\d{1,2}$/.test(v) && v !== '1') cell.setAttribute(a, v);
        });
        cleanNodes(cell, c, ctx);
        row.appendChild(cell);
      });
      if (!row.children.length) return;
      if (inHead) { thead = thead || d.createElement('thead'); thead.appendChild(row); } else { tbody.appendChild(row); }
    });
    var first = tbody.firstElementChild;
    // Word never marks header rows: a first row that is all <th> or all bold becomes the header
    var isHead = function (c) { return c.tagName === 'TH' || (textOf(c) && textOf(c) === Array.prototype.map.call(c.querySelectorAll('strong'), textOf).join(' ').trim()); };
    if (!thead && first && tbody.children.length > 1 && Array.prototype.every.call(first.children, isHead)) {
      each(Array.prototype.slice.call(first.children), function (c) { if (c.tagName === 'TD') { each(c.querySelectorAll('strong'), unwrap); rename(c, 'th'); } });
      thead = d.createElement('thead'); thead.appendChild(first);
    }
    if (thead) table.appendChild(thead);
    table.appendChild(tbody);
    return table;
  }

  /* Normalise a cleaned tree: no empty blocks, no <p> inside cells/items, inline runs wrapped in <p>, typed bullets removed. */
  function finish(root) {
    each(root.querySelectorAll('li > p, td > p, th > p, dd > p'), function (p) {
      if (p.nextSibling && textOf(p)) p.parentNode.insertBefore(d.createElement('br'), p.nextSibling);
      unwrap(p);
    });
    each(root.querySelectorAll('td h2, td h3, td h4, th h2, th h3, th h4, li h2, li h3, li h4'), function (h) { rename(h, 'strong'); });
    each(root.querySelectorAll('h2 strong, h3 strong, h4 strong, h2 b, h3 b, h4 b'), unwrap);
    each(root.querySelectorAll('p p, h2 p, h3 p, h4 p'), unwrap);
    // inline runs directly under the root → paragraphs
    var run = null;
    each(Array.prototype.slice.call(root.childNodes), function (n) {
      var name = n.nodeType === 3 ? '#text' : n.nodeType === 1 ? n.tagName : '';
      if (INLINE.test(name)) {
        if (n.nodeType === 3 && !n.nodeValue.trim() && !run) { root.removeChild(n); return; }
        if (!run) { run = d.createElement('p'); root.insertBefore(run, n); }
        run.appendChild(n);
      } else { run = null; }
    });
    // typed bullets inside real list items; ☐ ☑ items make the list a checklist
    each(root.querySelectorAll('li'), function (li) {
      var t = li.firstChild;
      while (t && t.nodeType === 1 && /^(STRONG|EM|SPAN|B|I)$/.test(t.tagName)) t = t.firstChild;
      if (t && t.nodeType === 3) t.nodeValue = t.nodeValue.replace(BULLET_RE, '').replace(NUM_RE, '');
    });
    each(root.querySelectorAll('ul'), function (ul) {
      var items = Array.prototype.filter.call(ul.children, function (c) { return c.tagName === 'LI'; });
      if (items.length && items.every(function (li) { return CHECK_RE.test(li.textContent); })) ul.className = 'checklist';
    });
    // collapse runs of <br>, drop empty inline wrappers and empty blocks
    each(root.querySelectorAll('br + br'), function (br) { br.parentNode.removeChild(br); });
    each(root.querySelectorAll('strong, em, a, sup, sub, u, s, span'), function (el) { if (!el.textContent && !el.querySelector('img')) el.parentNode.removeChild(el); });
    each(root.querySelectorAll('p, h2, h3, h4, li, blockquote'), function (el) {
      if (!textOf(el) && !el.querySelector('img, iframe, table, ul, ol')) el.parentNode.removeChild(el);
    });
    each(root.querySelectorAll('p, h2, h3, h4, li, td, th'), function (el) {
      var f = el.firstChild, l = el.lastChild;
      if (f && f.nodeType === 3) f.nodeValue = f.nodeValue.replace(/^\s+/, '');
      if (l && l.nodeType === 3) l.nodeValue = l.nodeValue.replace(/\s+$/, '');
      if (l && l.nodeType === 1 && l.tagName === 'BR' && el.tagName !== 'TD' && el.tagName !== 'TH') el.removeChild(l);
    });
  }

  function cleanHTML(html, opts) {
    var s = html.indexOf('<!--StartFragment-->'), e = html.indexOf('<!--EndFragment-->');
    if (s > -1 && e > s) html = html.slice(s + 20, e);
    var doc = new DOMParser().parseFromString(html, 'text/html');  // inert: nothing runs, nothing loads
    wordLists(doc);
    var ctx = { heading: headingMap(doc), skippedImages: 0, keepIds: !!(opts && opts.keepIds) };
    if (opts && opts.keepLevels) ctx.heading = function (level) { return 'h' + Math.min(Math.max(level, 2), 4); };
    var out = d.createElement('div');
    cleanNodes(out, doc.body, ctx);
    finish(out);
    return { html: out.innerHTML, skippedImages: ctx.skippedImages };
  }

  /* Plain text: one paragraph per line; runs of "• …" / "1. …" lines become lists. */
  function textToHTML(text) {
    var lines = String(text || '').replace(/\r\n?/g, '\n').split('\n'), html = '', list = null;
    function close() { if (list) { html += '</' + list + '>'; list = null; } }
    lines.forEach(function (line) {
      if (!line.trim()) { close(); return; }
      var kind = BULLET_RE.test(line) ? 'ul' : NUM_RE.test(line) ? 'ol' : null;
      if (kind) {
        if (list !== kind) { close(); html += '<' + kind + '>'; list = kind; }
        html += '<li>' + esc(line.replace(BULLET_RE, '').replace(NUM_RE, '').trim()) + '</li>';
      } else { close(); html += '<p>' + esc(line.trim()) + '</p>'; }
    });
    close();
    return html;
  }

  /* What gets saved: the editor DOM minus what browsers add while editing (inline styles, bare spans, <div> lines). */
  function serialize(ed) {
    var c = ed.cloneNode(true);
    each(c.querySelectorAll('[style]'), function (el) { el.removeAttribute('style'); });
    each(c.querySelectorAll('font, span:not([dir]):not([lang])'), unwrap);
    each(c.querySelectorAll('div'), function (el) { if (el.querySelector(BLOCK_SEL)) unwrap(el); else rename(el, 'p'); });
    each(c.querySelectorAll('li'), function (li) {
      var t = li.firstChild; if (t && t.nodeType === 3) t.nodeValue = t.nodeValue.replace(BULLET_RE, '');
    });
    return c.innerHTML;
  }

  /* Source view → editor: keep the markup as written (the server sanitiser decides what is stored);
     only stop scripts and event handlers from running inside the dashboard. */
  function defuse(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    each(doc.querySelectorAll('script, style, link, meta, object, embed, base'), function (x) { x.parentNode.removeChild(x); });
    each(doc.body.querySelectorAll('*'), function (el) {
      each(Array.prototype.slice.call(el.attributes), function (a) {
        if (/^on/i.test(a.name) || (/^(href|src|action|formaction)$/i.test(a.name) && /^\s*(javascript|vbscript|data):/i.test(a.value))) el.removeAttribute(a.name);
      });
    });
    return doc.body.innerHTML;
  }

  function isBoldLine(el) {
    if (el.tagName !== 'P') return false;
    var t = textOf(el);
    if (t.length < 2 || t.length > 150 || !el.querySelector('strong, b')) return false;
    var c = el.cloneNode(true);
    each(c.querySelectorAll('strong, b'), function (b) { b.parentNode.removeChild(b); });
    return !textOf(c);
  }

  function toHeading(el, tag) {
    var h = rename(el, tag || 'h2');
    each(h.querySelectorAll('strong, b'), unwrap);
    return h;
  }

  /* ───────── the editor ───────── */

  function setup(ta) {
    var wrap = d.createElement('div');
    wrap.className = 'rich' + (ta.dataset.rich === 'tall' ? ' tall' : '');
    var head = d.createElement('div'); head.className = 'head';
    var bar = d.createElement('div'); bar.className = 'bar'; bar.setAttribute('role', 'toolbar');
    var tbar = d.createElement('div'); tbar.className = 'bar tbar'; tbar.hidden = true; tbar.setAttribute('role', 'toolbar'); tbar.setAttribute('aria-label', 'أدوات الجدول');
    var panel = d.createElement('div'); panel.className = 'panel'; panel.hidden = true;
    var notice = d.createElement('div'); notice.className = 'notice'; notice.hidden = true;
    var ed = d.createElement('div'); ed.className = 'ed'; ed.contentEditable = 'true'; ed.dir = 'auto';
    ed.setAttribute('role', 'textbox'); ed.setAttribute('aria-multiline', 'true');
    ed.innerHTML = ta.value;
    if (ta.id) { var lab = d.querySelector('label[for="' + ta.id + '"]'); if (lab) { ed.setAttribute('aria-label', lab.textContent.trim()); bar.setAttribute('aria-label', 'أدوات ' + lab.textContent.trim()); } }
    var src = d.createElement('textarea'); src.className = 'src code'; src.setAttribute('aria-label', 'HTML'); src.dir = 'ltr';
    var foot = d.createElement('div'); foot.className = 'foot';
    var wc = d.createElement('span'), status = d.createElement('span'); status.className = 'status'; status.setAttribute('aria-live', 'polite');
    foot.appendChild(wc); foot.appendChild(status);
    var pv = null;
    var form = ta.closest('form');
    var plainNext = false;

    ta.hidden = true;
    ta.parentNode.insertBefore(wrap, ta);
    head.appendChild(bar); head.appendChild(tbar); head.appendChild(panel); head.appendChild(notice);
    wrap.appendChild(head); wrap.appendChild(ed); wrap.appendChild(src); wrap.appendChild(foot); wrap.appendChild(ta);

    function isSource() { return wrap.classList.contains('source'); }
    var syncT;
    function sync() {
      clearTimeout(syncT);
      var v = isSource() ? src.value : serialize(ed);
      if (v !== ta.value) { ta.value = v; ta.dispatchEvent(new Event('input', { bubbles: true })); }
      refresh();
    }
    function syncSoon() { clearTimeout(syncT); syncT = setTimeout(sync, 250); }  // typing: don't re-serialise on every key
    function flash(msg) { status.textContent = msg; clearTimeout(flash.t); flash.t = setTimeout(function () { status.textContent = status.dataset.keep || ''; }, 4000); }
    function block() {  // the block element holding the caret
      var sel = window.getSelection(); if (!sel.rangeCount) return null;
      var n = sel.anchorNode; if (!n || !ed.contains(n)) return null;
      n = n.nodeType === 3 ? n.parentNode : n;
      while (n && n !== ed && !/^(P|H[1-6]|LI|BLOCKQUOTE|DIV|TD|TH|PRE)$/.test(n.tagName)) n = n.parentNode;
      return n === ed ? null : n;
    }
    function cell() { var b = block(); return b && b.closest ? b.closest('td, th') : null; }
    function keepCaret(fn) {  // DOM moves drop the selection; restore it on the same text node
      var sel = window.getSelection(), r = sel.rangeCount ? sel.getRangeAt(0) : null;
      var node = r && r.startContainer, off = r && r.startOffset;
      fn();
      if (node && ed.contains(node)) { var nr = d.createRange(); nr.setStart(node, Math.min(off, (node.nodeValue || node.childNodes).length)); nr.collapse(true); sel.removeAllRanges(); sel.addRange(nr); }
    }
    function insertHTML(html) { ed.focus(); d.execCommand('insertHTML', false, html); sync(); }

    /* lists: two levels, built as valid nested lists (<li>…<ul>…</ul></li>) */
    function depth(li) { var k = 0, n = li; while (n && n !== ed) { if (/^(UL|OL)$/.test(n.tagName)) k++; n = n.parentNode; } return k; }
    function indent(li) {
      var prev = li.previousElementSibling;
      if (!prev || prev.tagName !== 'LI' || depth(li) >= 2) return;
      keepCaret(function () {
        var last = prev.lastElementChild;
        var sub = last && /^(UL|OL)$/.test(last.tagName) ? last : prev.appendChild(d.createElement(li.parentNode.tagName.toLowerCase()));
        sub.appendChild(li);
      });
    }
    function outdent(li) {
      var list = li.parentNode, parentLi = list.parentNode;
      if (!parentLi || parentLi.tagName !== 'LI') { d.execCommand('outdent'); return; }
      keepCaret(function () {
        var rest = [], n = li.nextElementSibling;
        while (n) { rest.push(n); n = n.nextElementSibling; }
        if (rest.length) { var sub = d.createElement(list.tagName.toLowerCase()); rest.forEach(function (x) { sub.appendChild(x); }); li.appendChild(sub); }
        parentLi.parentNode.insertBefore(li, parentLi.nextSibling);
        if (!list.children.length) list.parentNode.removeChild(list);
      });
    }

    /* tables */
    function tableHTML(rows, cols, header) {
      var h = '<table>';
      if (header) { h += '<thead><tr>'; for (var c = 0; c < cols; c++) h += '<th>عنوان ' + (c + 1) + '</th>'; h += '</tr></thead>'; }
      h += '<tbody>';
      for (var r = 0; r < rows; r++) { h += '<tr>'; for (var c2 = 0; c2 < cols; c2++) h += '<td><br></td>'; h += '</tr>'; }
      return h + '</tbody></table><p><br></p>';
    }
    function cellIndex(c) { return Array.prototype.indexOf.call(c.parentNode.children, c); }
    var tableOps = {
      addRow: function (c) {
        var tr = c.parentNode, table = tr.closest('table'), body = table.tBodies[0] || table.appendChild(d.createElement('tbody'));
        var row = d.createElement('tr');
        for (var i = 0; i < tr.children.length; i++) row.appendChild(d.createElement('td')).appendChild(d.createElement('br'));
        if (tr.parentNode.tagName === 'THEAD') body.insertBefore(row, body.firstChild); else tr.parentNode.insertBefore(row, tr.nextSibling);
      },
      delRow: function (c) {
        var tr = c.parentNode, sec = tr.parentNode, table = tr.closest('table');
        if (table.rows.length <= 1) return;
        sec.removeChild(tr);
        if (!sec.children.length) sec.parentNode.removeChild(sec);
      },
      addCol: function (c) {
        var idx = cellIndex(c);
        each(c.closest('table').rows, function (tr) {
          var n = d.createElement(tr.parentNode.tagName === 'THEAD' ? 'th' : 'td'); n.appendChild(d.createElement('br'));
          tr.insertBefore(n, tr.children[idx + 1] || null);
        });
      },
      delCol: function (c) {
        var idx = cellIndex(c), table = c.closest('table');
        if (c.parentNode.children.length <= 1) return;
        each(table.rows, function (tr) { if (tr.children[idx]) tr.removeChild(tr.children[idx]); });
      },
      delTable: function (c) { var t = c.closest('table'); t.parentNode.removeChild(t); }
    };

    function openTablePanel() {
      panel.innerHTML = '';
      panel.hidden = false;
      var mk = function (html) { var x = d.createElement('span'); x.innerHTML = html; return x.firstChild; };
      var rows = mk('<label>صفوف البيانات <input type="number" min="1" max="50" value="4"></label>');
      var cols = mk('<label>الأعمدة <input type="number" min="1" max="10" value="5"></label>');
      var hdr = mk('<label class="check"><input type="checkbox" checked> صف عناوين</label>');
      var ok = mk('<button type="button" class="btn sm dark">إدراج الجدول</button>');
      var cancel = mk('<button type="button" class="btn sm">إلغاء</button>');
      [rows, cols, hdr, ok, cancel].forEach(function (x) { panel.appendChild(x); });
      var saved = window.getSelection().rangeCount && ed.contains(window.getSelection().anchorNode) ? window.getSelection().getRangeAt(0).cloneRange() : null;
      ok.addEventListener('click', function () {
        var r = Math.min(Math.max(+rows.querySelector('input').value || 1, 1), 50);
        var c = Math.min(Math.max(+cols.querySelector('input').value || 1, 1), 10);
        panel.hidden = true;
        ed.focus();
        if (saved) { var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(saved); }
        insertHTML(tableHTML(r, c, hdr.querySelector('input').checked));
      });
      cancel.addEventListener('click', function () { panel.hidden = true; ed.focus(); });
      rows.querySelector('input').focus();
    }

    function link() {
      var url = prompt('الرابط (https://… أو /blog/…)');
      if (url && /^(https?:\/\/|\/|#|mailto:|tel:)/.test(url.trim())) { ed.focus(); d.execCommand('createLink', false, url.trim()); sync(); }
    }

    function plainPaste() {
      if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText().then(function (t) { insertHTML(textToHTML(t)); }, function () { flash('اضغط Ctrl+Shift+V للصق كنص عادي'); });
      } else { flash('اضغط Ctrl+Shift+V للصق كنص عادي'); }
    }

    function convertBoldLines() {
      var n = 0;
      each(ed.querySelectorAll('p'), function (p) { if (isBoldLine(p)) { toHeading(p, 'h2'); n++; } });
      sync();
      flash(n ? 'تم تحويل ' + n + ' سطر إلى H2' : 'لا توجد سطور غامقة');
    }

    function leaveSource() {
      ed.innerHTML = defuse(src.value);
      wrap.classList.remove('source');
    }

    var tools = [
      ['↶', 'undo', 'تراجع (Ctrl+Z)'], ['↷', 'redo', 'إعادة (Ctrl+Y)'], null,
      ['B', 'bold', 'غامق (Ctrl+B)'], ['I', 'italic', 'مائل (Ctrl+I)'], null,
      ['H2', 'block:h2', 'عنوان H2'], ['H3', 'block:h3', 'عنوان H3'], ['H4', 'block:h4', 'عنوان H4'], ['¶', 'block:p', 'فقرة'],
      ['تحويل لعنوان', 'toHeading', 'تحويل السطر الغامق الحالي إلى عنوان H2'], null,
      ['•', 'insertUnorderedList', 'قائمة نقطية'], ['1.', 'insertOrderedList', 'قائمة مرقمة'],
      ['⇥', 'indent', 'مستوى فرعي في القائمة (Tab)'], ['⇤', 'outdent', 'رجوع مستوى (Shift+Tab)'], null,
      ['❝', 'block:blockquote', 'اقتباس'], ['🔗', 'link', 'رابط (Ctrl+K)'], ['🖼', 'image', 'صورة من المكتبة'], ['▶', 'youtube', 'فيديو YouTube'],
      ['جدول', 'table', 'إدراج جدول'], null,
      ['لصق نص', 'plain', 'لصق كنص عادي (Ctrl+Shift+V)'], ['⌫', 'removeFormat', 'إزالة التنسيق'], ['</>', 'source', 'HTML']
    ];
    if (ta.hasAttribute('data-preview')) tools.push(['معاينة', 'preview', 'معاينة المقال كما سيظهر بجانب المحرر']);

    function run(cmd, btn) {
      if (cmd === 'source') {
        if (isSource()) leaveSource(); else { src.value = ta.value = serialize(ed); wrap.classList.add('source'); }
        btn.setAttribute('aria-pressed', String(isSource()));
        sync();
        return;
      }
      if (cmd === 'preview') { togglePreview(btn); return; }
      if (isSource()) return;
      ed.focus();
      var b = block();
      if (cmd === 'link') { link(); return; }
      if (cmd === 'table') { openTablePanel(); return; }
      if (cmd === 'plain') { plainPaste(); return; }
      if (cmd === 'toHeading') {
        if (b && b.tagName === 'P') { keepCaret(function () { toHeading(b, 'h2'); }); } else flash('ضع المؤشر داخل السطر الغامق أولًا');
      } else if (cmd === 'indent' || cmd === 'outdent') {
        var li = b && b.closest('li');
        if (li) { (cmd === 'indent' ? indent : outdent)(li); } else flash('ضع المؤشر داخل عنصر قائمة');
      } else if (cmd === 'image') {
        var src2 = prompt('رابط الصورة من مكتبة الوسائط (/media/…)');
        var alt = src2 ? prompt('النص البديل (alt) — إلزامي') : '';
        if (src2 && alt && /^\/media\//.test(src2)) d.execCommand('insertHTML', false, '<img src="' + esc(src2) + '" alt="' + esc(alt) + '" loading="lazy">');
      } else if (cmd === 'youtube') {
        var v = prompt('رابط فيديو YouTube');
        var m = v && v.match(/(?:v=|youtu\.be\/|embed\/)([\w-]{11})/);
        if (m) d.execCommand('insertHTML', false, '<iframe src="https://www.youtube-nocookie.com/embed/' + m[1] + '" title="YouTube" loading="lazy" allowfullscreen></iframe><p></p>');
      } else if (cmd.indexOf('block:') === 0) {
        d.execCommand('formatBlock', false, cmd.split(':')[1]);
      } else {
        d.execCommand(cmd, false, null);
      }
      sync();
    }

    tools.forEach(function (t) {
      if (!t) { var sep = d.createElement('span'); sep.className = 'sep'; sep.setAttribute('aria-hidden', 'true'); bar.appendChild(sep); return; }
      var b = d.createElement('button'); b.type = 'button'; b.textContent = t[0]; b.title = t[2]; b.setAttribute('aria-label', t[2]);
      if (t[0].length > 3) b.className = 'wide';
      b.dataset.cmd = t[1];
      if (t[1] === 'source' || t[1] === 'preview') b.setAttribute('aria-pressed', 'false');
      b.addEventListener('mousedown', function (e) { e.preventDefault(); });  // keep the caret in the text
      b.addEventListener('click', function () { run(t[1], b); });
      bar.appendChild(b);
    });
    [['+ صف', 'addRow'], ['− صف', 'delRow'], ['+ عمود', 'addCol'], ['− عمود', 'delCol'], ['حذف الجدول', 'delTable']].forEach(function (t) {
      var b = d.createElement('button'); b.type = 'button'; b.textContent = t[0]; b.className = 'wide';
      b.addEventListener('mousedown', function (e) { e.preventDefault(); });
      b.addEventListener('click', function () {
        var c = cell(); if (!c) return;
        if (t[1] === 'delTable' && !confirm('حذف الجدول كله؟')) return;
        tableOps[t[1]](c); sync();
      });
      tbar.appendChild(b);
    });

    /* paste: keep structure, drop Word/Docs styling */
    ed.addEventListener('paste', function (e) {
      var cd = e.clipboardData || window.clipboardData;
      if (!cd) return;
      e.preventDefault();
      var html = plainNext ? '' : cd.getData('text/html');
      plainNext = false;
      var out = html ? cleanHTML(html) : { html: textToHTML(cd.getData('text/plain')), skippedImages: 0 };
      if (out.html) d.execCommand('insertHTML', false, out.html);
      if (out.skippedImages) flash('تم تجاهل ' + out.skippedImages + ' صورة من المصدر: ارفعها لمكتبة الوسائط وأضفها بزر الصورة.');
      sync();
    });

    ed.addEventListener('keydown', function (e) {
      var mod = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
      if (mod && e.shiftKey && k === 'v') {  // the browser still fires paste; forget the flag if it doesn't
        plainNext = true; setTimeout(function () { plainNext = false; }, 1000); return;
      }
      if (mod && !e.shiftKey && k === 'k') { e.preventDefault(); link(); return; }
      if (mod && !e.shiftKey && (k === 'y')) { e.preventDefault(); d.execCommand('redo'); sync(); return; }
      if (e.key === 'Tab') {
        var b = block(), li = b && b.closest('li');
        if (!li) return;  // outside lists Tab keeps moving focus
        e.preventDefault();
        (e.shiftKey ? outdent : indent)(li);
        sync();
      }
    });
    ed.addEventListener('input', syncSoon);
    src.addEventListener('input', syncSoon);
    d.addEventListener('selectionchange', function () {
      if (!ed.contains(d.activeElement) && d.activeElement !== ed) return;
      tbar.hidden = !cell();
    });

    /* bold lines that look like headings + word count */
    var refreshT;
    function refresh() {
      clearTimeout(refreshT);
      refreshT = setTimeout(function () {
        var text = isSource() ? src.value.replace(/<[^>]+>/g, ' ') : (ed.innerText || '');
        var words = text.trim() ? text.trim().split(/\s+/).length : 0;
        wc.textContent = words + ' كلمة · ' + Math.max(1, Math.round(words / 200)) + ' دقيقة قراءة تقريبًا';
        var bold = isSource() ? 0 : Array.prototype.filter.call(ed.querySelectorAll('p'), isBoldLine).length;
        notice.hidden = !bold;
        if (bold) {
          notice.innerHTML = '';
          notice.appendChild(d.createTextNode(bold + ' سطر غامق يبدو كعنوان. '));
          var fix = d.createElement('button'); fix.type = 'button'; fix.className = 'btn sm'; fix.textContent = 'تحويلها كلها إلى H2';
          fix.addEventListener('click', convertBoldLines);
          notice.appendChild(fix);
        }
        if (pv) renderPreview();
      }, 300);
    }

    /* side preview: the article as it will appear. The frame is sandboxed without allow-scripts, so
       nothing in it runs (inline handlers included); the page shell loads once and only the body is swapped. */
    function renderPreview() {
      var title = form && form.elements.title ? form.elements.title.value : '';
      var body = ta.value.replace(/<table\b/gi, '<div class="table-wrap"><table').replace(/<\/table>/gi, '</table></div>');  // mirrors seo.wrap_tables
      var doc = pv.contentDocument, art = doc && doc.querySelector('.prose');
      if (art) { doc.querySelector('h1').textContent = title; art.innerHTML = body; return; }
      if (pv.dataset.loading) return;
      pv.dataset.loading = '1';
      pv.addEventListener('load', function () { if (pv) renderPreview(); });
      pv.srcdoc = '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><base href="' + esc(location.origin) + '/">' +
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap">' +
        '<link rel="stylesheet" href="/static/css/site.css"><style>body{background:var(--bg);margin:0;padding:16px}h1{font-size:26px;margin:8px 0 16px;color:var(--navy)}</style></head>' +
        '<body><h1></h1><article class="prose"></article></body></html>';
    }
    function togglePreview(btn) {
      var on = !wrap.classList.contains('split');
      wrap.classList.toggle('split', on);
      btn.setAttribute('aria-pressed', String(on));
      d.body.classList.toggle('editor-split', on);
      if (on) {
        pv = d.createElement('iframe'); pv.className = 'pv'; pv.title = 'معاينة المقال'; pv.setAttribute('sandbox', 'allow-same-origin');
        wrap.insertBefore(pv, foot);
        renderPreview();
        ed.focus();
      } else if (pv) { pv.parentNode.removeChild(pv); pv = null; }
    }
    wrap.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && wrap.classList.contains('split')) togglePreview(bar.querySelector('[data-cmd="preview"]'));
    });

    if (form) {
      form.addEventListener('submit', function () { if (isSource()) leaveSource(); sync(); });
      if (form.elements.title) form.elements.title.addEventListener('input', function () { if (pv) refresh(); });
    }
    try { d.execCommand('defaultParagraphSeparator', false, 'p'); } catch (e) { /* older browsers */ }
    refresh();
    return { ed: ed, ta: ta, sync: sync, flash: flash, status: status, form: form };
  }

  /* ───────── autosave (every 30 s, separate draft slot) + leave-page warning ───────── */

  function autosave(api) {
    var url = api.ta.dataset.autosave, form = api.form, last = api.ta.value, busy = false;
    var draftEl = d.getElementById('autosave-draft');
    var time = function (iso) { var t = new Date(/Z|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z'); return t.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }); };
    var LOCAL = 'manasety-new-article';
    var store = { get: function () { try { return JSON.parse(localStorage.getItem(LOCAL) || 'null'); } catch (e) { return null; } },
                  set: function (v) { try { localStorage.setItem(LOCAL, JSON.stringify(v)); } catch (e) { /* private mode */ } },
                  clear: function () { try { localStorage.removeItem(LOCAL); } catch (e) { /* ignore */ } } };

    var draft = null, stopped = false;
    var titleOf = function () { return form.elements.title ? form.elements.title.value : ''; };
    if (draftEl) { try { draft = JSON.parse(draftEl.textContent); } catch (e) { draft = null; } }
    var local = store.get();
    if (!url) { if (local && local.content_html && local.content_html !== api.ta.value) draft = local; }
    else if (local && local.title && local.title === titleOf()) store.clear();  // the new article was saved: drop its browser copy
    if (draft) {
      var bar = d.createElement('div'); bar.className = 'flash restore'; bar.setAttribute('role', 'status');
      bar.appendChild(d.createTextNode('توجد مسودة محفوظة تلقائيًا (' + time(draft.saved_at) + ') أحدث من آخر حفظ. '));
      var yes = d.createElement('button'); yes.type = 'button'; yes.className = 'btn sm dark'; yes.textContent = 'استرجاع المسودة';
      var no = d.createElement('button'); no.type = 'button'; no.className = 'btn sm'; no.textContent = 'تجاهل';
      yes.addEventListener('click', function () {
        api.ed.innerHTML = draft.content_html || '';
        if (draft.title && form.elements.title) form.elements.title.value = draft.title;
        api.sync(); dirty = true; bar.remove();
      });
      no.addEventListener('click', function () { bar.remove(); if (!url) store.clear(); });
      bar.appendChild(yes); bar.appendChild(no);
      form.parentNode.insertBefore(bar, form);
    }

    last = titleOf() + '\u0000' + last;
    function tick() {
      if (busy || stopped) return;
      api.sync();
      var now = titleOf() + '\u0000' + api.ta.value;
      if (now === last) return;
      last = now;
      if (!url) {  // a new article has no id yet: keep a copy in this browser until the first save succeeds
        store.set({ title: titleOf(), content_html: api.ta.value, saved_at: new Date().toISOString() });
        api.status.dataset.keep = 'نسخة احتياطية في المتصفح ' + time(new Date().toISOString()) + ' · احفظ المقال لتفعيل الحفظ التلقائي على الخادم';
        api.status.textContent = api.status.dataset.keep;
        return;
      }
      busy = true;
      var body = new FormData(form);
      body.set('content_html', api.ta.value);
      body.set('base', api.ta.dataset.base || '');
      fetch(url, { method: 'POST', body: body, headers: { 'X-CSRFToken': csrf, 'Accept': 'application/json' }, credentials: 'same-origin' })
        .then(function (r) {
          if (r.status === 409) { stopped = true; throw new Error('stale'); }
          if (!r.ok) throw new Error(r.status);
          return r.json();
        })
        .then(function (res) {
          api.status.dataset.keep = res.saved_at ? 'حُفظت مسودة تلقائيًا ' + time(res.saved_at) : 'لا توجد تغييرات غير محفوظة';
          api.status.textContent = api.status.dataset.keep;
          var list = d.getElementById('quality-checks');
          if (list && res.checks) {
            list.innerHTML = '';
            res.checks.forEach(function (c) { var li = d.createElement('li'); li.textContent = c.label; if (c.ok) li.className = 'ok'; list.appendChild(li); });
          }
        })
        .catch(function () {
          last = null;
          api.status.textContent = stopped ? 'حُفظ المقال من صفحة أخرى بعد فتح هذه الصفحة: أعد تحميلها قبل المتابعة'
                                           : 'تعذر الحفظ التلقائي، سنحاول مرة أخرى';
        })
        .then(function () { busy = false; });
    }
    setInterval(tick, 30000);

    var dirty = false;
    form.addEventListener('input', function () { dirty = true; });
    form.addEventListener('change', function () { dirty = true; });
    form.addEventListener('submit', function () { dirty = false; stopped = true; });  // the browser copy stays until the saved page loads
    window.addEventListener('beforeunload', function (e) { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  }

  d.querySelectorAll('textarea[data-rich]').forEach(function (ta) {
    var api = setup(ta);
    if (api.form && api.form.hasAttribute('data-guard') && ta.hasAttribute('data-preview')) autosave(api);
  });

  window.ManasetyEditor = { cleanHTML: cleanHTML, textToHTML: textToHTML };  // used by the tests
})();
