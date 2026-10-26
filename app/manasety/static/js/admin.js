/* Dashboard helpers. Output of the rich editor is re-sanitised on the server; this file only edits. */
(function () {
  'use strict';
  var d = document;
  var csrf = (d.querySelector('meta[name="csrf-token"]') || {}).content || '';

  /* ── rich text editor (contenteditable + hidden textarea) ── */
  d.querySelectorAll('textarea[data-rich]').forEach(function (ta) {
    var wrap = d.createElement('div');
    wrap.className = 'rich' + (ta.dataset.rich === 'tall' ? ' tall' : '');
    var bar = d.createElement('div'); bar.className = 'bar';
    var ed = d.createElement('div'); ed.className = 'ed'; ed.contentEditable = 'true'; ed.dir = 'auto';
    ed.innerHTML = ta.value;
    ed.setAttribute('role', 'textbox'); ed.setAttribute('aria-multiline', 'true');
    if (ta.id) { var lab = d.querySelector('label[for="' + ta.id + '"]'); if (lab) ed.setAttribute('aria-label', lab.textContent.trim()); }
    var tools = [
      ['B', 'bold', 'غامق'], ['I', 'italic', 'مائل'], ['H2', 'formatBlock:h2', 'عنوان H2'], ['H3', 'formatBlock:h3', 'عنوان H3'],
      ['¶', 'formatBlock:p', 'فقرة'], ['•', 'insertUnorderedList', 'قائمة'], ['1.', 'insertOrderedList', 'قائمة مرقمة'],
      ['❝', 'formatBlock:blockquote', 'اقتباس'], ['🔗', 'link', 'رابط'], ['🖼', 'image', 'صورة من المكتبة'],
      ['▶', 'youtube', 'فيديو YouTube'], ['⌫', 'removeFormat', 'إزالة التنسيق'], ['</>', 'source', 'HTML']
    ];
    tools.forEach(function (t) {
      var b = d.createElement('button'); b.type = 'button'; b.textContent = t[0]; b.title = t[2]; b.setAttribute('aria-label', t[2]);
      b.addEventListener('click', function () {
        var cmd = t[1];
        if (cmd === 'source') {
          if (wrap.classList.toggle('source')) { src.value = ed.innerHTML; } else { ed.innerHTML = src.value; }
          return;
        }
        ed.focus();
        if (cmd === 'link') {
          var url = prompt('الرابط (https://… أو /blog/…)');
          if (url && /^(https?:\/\/|\/|mailto:|tel:)/.test(url)) d.execCommand('createLink', false, url);
        } else if (cmd === 'image') {
          var src2 = prompt('رابط الصورة من مكتبة الوسائط (/media/…)');
          var alt = src2 ? prompt('النص البديل (alt) — إلزامي') : '';
          if (src2 && alt && /^\/media\//.test(src2)) d.execCommand('insertHTML', false, '<img src="' + src2 + '" alt="' + alt.replace(/"/g, '') + '" loading="lazy">');
        } else if (cmd === 'youtube') {
          var v = prompt('رابط فيديو YouTube');
          var m = v && v.match(/(?:v=|youtu\.be\/|embed\/)([\w-]{11})/);
          if (m) d.execCommand('insertHTML', false, '<iframe src="https://www.youtube-nocookie.com/embed/' + m[1] + '" title="YouTube" loading="lazy" allowfullscreen></iframe><p></p>');
        } else if (cmd.indexOf('formatBlock:') === 0) {
          d.execCommand('formatBlock', false, cmd.split(':')[1]);
        } else {
          d.execCommand(cmd, false, null);
        }
        sync();
      });
      bar.appendChild(b);
    });
    var src = d.createElement('textarea'); src.className = 'src code'; src.setAttribute('aria-label', 'HTML');
    ta.style.display = 'none';
    ta.parentNode.insertBefore(wrap, ta);
    wrap.appendChild(bar); wrap.appendChild(ed); wrap.appendChild(src); wrap.appendChild(ta);
    function sync() { ta.value = wrap.classList.contains('source') ? src.value : ed.innerHTML; ta.dispatchEvent(new Event('input', { bubbles: true })); }
    ed.addEventListener('input', sync); src.addEventListener('input', sync);
    ed.addEventListener('paste', function (e) {
      // paste as plain text so Word/Docs styles don't leak in
      e.preventDefault();
      var text = (e.clipboardData || window.clipboardData).getData('text/plain');
      d.execCommand('insertText', false, text);
    });
    var form = ta.closest('form'); if (form) form.addEventListener('submit', sync);
  });

  /* ── repeatable list rows (block fields) ── */
  d.addEventListener('click', function (e) {
    var add = e.target.closest('[data-add-row]');
    if (add) {
      var box = d.getElementById(add.dataset.addRow);
      var tpl = d.getElementById(add.dataset.addRow + '-tpl');
      var idx = Number(box.dataset.next || box.children.length);
      box.dataset.next = idx + 1;
      box.insertAdjacentHTML('beforeend', tpl.innerHTML.replace(/__IDX__/g, idx));
      return;
    }
    var rm = e.target.closest('[data-remove-row]');
    if (rm) { rm.closest('.list-row').remove(); return; }
    var mv = e.target.closest('[data-move]');
    if (mv) {
      var row = mv.closest('.list-row');
      if (mv.dataset.move === 'up' && row.previousElementSibling) row.parentNode.insertBefore(row, row.previousElementSibling);
      if (mv.dataset.move === 'down' && row.nextElementSibling) row.parentNode.insertBefore(row.nextElementSibling, row);
      renumber(row.parentNode);
    }
  });
  /* keep names in visual order so the server saves the order the editor sees */
  function renumber(box) {
    Array.prototype.forEach.call(box.children, function (row, i) {
      row.querySelectorAll('[name]').forEach(function (el) { el.name = el.name.replace(/__\d+__/, '__' + i + '__'); });
    });
  }

  /* ── drag & drop ordering (sections, FAQ…) ── */
  d.querySelectorAll('[data-sortable]').forEach(function (list) {
    var dragging = null;
    list.querySelectorAll('[data-id]').forEach(function (item) {
      item.draggable = true;
      item.addEventListener('dragstart', function () { dragging = item; item.classList.add('dragging'); });
      item.addEventListener('dragend', function () { item.classList.remove('dragging'); dragging = null; save(); });
      item.addEventListener('dragover', function (e) {
        e.preventDefault();
        if (!dragging || dragging === item) return;
        var r = item.getBoundingClientRect();
        list.insertBefore(dragging, (e.clientY - r.top) > r.height / 2 ? item.nextSibling : item);
      });
      /* keyboard: Alt+ArrowUp/Down moves the focused row */
      item.addEventListener('keydown', function (e) {
        if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return;
        e.preventDefault();
        if (e.key === 'ArrowUp' && item.previousElementSibling) list.insertBefore(item, item.previousElementSibling);
        if (e.key === 'ArrowDown' && item.nextElementSibling) list.insertBefore(item.nextElementSibling, item);
        item.querySelector('a, button').focus();
        save();
      });
    });
    function save() {
      var order = Array.prototype.map.call(list.querySelectorAll('[data-id]'), function (x) { return x.dataset.id; });
      fetch(list.dataset.sortable, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }, body: JSON.stringify({ order: order }), credentials: 'same-origin' })
        .then(function (r) { if (!r.ok) alert('تعذر حفظ الترتيب'); else { var s = d.getElementById('order-saved'); if (s) { s.hidden = false; setTimeout(function () { s.hidden = true; }, 1500); } } });
    }
  });

  /* ── live character counters + SERP preview ── */
  d.querySelectorAll('[data-count]').forEach(function (el) {
    var out = d.createElement('span'); out.className = 'count';
    el.insertAdjacentElement('afterend', out);
    var parts = el.dataset.count.split('-'); var min = +parts[0], max = +parts[1];
    function upd() { var n = el.value.length; out.textContent = n + ' / ' + min + '–' + max; out.classList.toggle('bad', n > 0 && (n < min || n > max)); }
    el.addEventListener('input', upd); upd();
  });
  var serp = d.getElementById('serp');
  if (serp) {
    var f = serp.closest('form');
    function upd() {
      serp.querySelector('.t').textContent = (f.meta_title.value || f.title.value || 'عنوان المقال');
      serp.querySelector('.d').textContent = (f.meta_description.value || f.excerpt.value || '');
      serp.querySelector('.u').textContent = 'manasety.ai › blog › ' + (f.slug.value || '…');
    }
    f.addEventListener('input', upd); upd();
  }

  /* ── confirm destructive buttons ── */
  d.addEventListener('submit', function (e) {
    var msg = e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) e.preventDefault();
  });
})();
