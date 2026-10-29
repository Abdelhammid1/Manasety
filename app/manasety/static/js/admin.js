/* Dashboard helpers (list rows, ordering, counters, SERP preview, confirmations). */
(function () {
  'use strict';
  var d = document;
  var csrf = (d.querySelector('meta[name="csrf-token"]') || {}).content || '';

  /* The rich text editor lives in editor.js. */

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
