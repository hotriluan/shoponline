/* Sidebar drawer: the menu button opens it below 1024px; Esc, the scrim or a link closes it. */
(function () {
  var body = document.body;
  var button = document.querySelector('[data-nav-toggle]');
  if (!button) return;
  function setOpen(open) {
    body.classList.toggle('nav-open', open);
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  button.addEventListener('click', function () { setOpen(!body.classList.contains('nav-open')); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && body.classList.contains('nav-open')) { setOpen(false); button.focus(); }
  });
  var scrim = document.querySelector('[data-nav-scrim]');
  if (scrim) scrim.addEventListener('click', function () { setOpen(false); });
})();

/* Autosave: an element with data-autosave="<url>" (a table row or a form) posts all its named
   fields to that url shortly after any of them changes, and shows the result in its
   [data-autosave-status]. data-autosave-require lists fields that must be filled before
   saving; data-autosave-reload reloads the page after a successful save. */
(function () {
  var failed = new Set();
  document.querySelectorAll('[data-autosave]').forEach(function (box) {
    var status = box.querySelector('[data-autosave-status]');
    var required = (box.dataset.autosaveRequire || '').split(',').filter(Boolean);
    var timer = null, chain = Promise.resolve();
    function fields() {
      return Array.prototype.filter.call(
        box.querySelectorAll('input[name], select[name], textarea[name]'),
        function (f) { return f.type !== 'file' && (f.type !== 'checkbox' || f.checked); });
    }
    function body() {
      var params = new URLSearchParams();
      fields().forEach(function (f) { params.append(f.name, f.value); });
      return params.toString();
    }
    function show(text, kind) {
      if (!status) return;
      status.textContent = text;
      status.className = kind === 'error' ? 'bad' : (kind === 'ok' ? 'ok' : 'muted');
    }
    var saved = body();
    function save() {
      timer = null;
      var payload = body();
      if (payload === saved && !failed.has(box)) return;
      var missing = required.some(function (name) {
        var f = box.querySelector('[name="' + name + '"]');
        return f && !f.value.trim();
      });
      if (missing) { show('Chưa đủ thông tin, chưa lưu', 'wait'); return; }
      show('Đang lưu…', 'wait');
      chain = chain.then(function () {
        return fetch(box.dataset.autosave, {
          method: 'POST', body: payload, keepalive: true, credentials: 'same-origin',
          headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-Autosave': '1'}
        }).then(function (resp) {
          return resp.json().catch(function () { return {ok: false, message: 'Lỗi máy chủ (' + resp.status + ')'}; });
        }).then(function (data) {
          if (data.ok) {
            saved = payload; failed.delete(box);
            show('✓ ' + data.message + ' ' + new Date().toLocaleTimeString('vi-VN', {hour: '2-digit', minute: '2-digit'}), 'ok');
            if (box.dataset.autosaveReload !== undefined) location.reload();
          } else { failed.add(box); show('✗ ' + (data.message || 'Dữ liệu không hợp lệ'), 'error'); }
        }, function () { failed.add(box); show('✗ Mất kết nối, chưa lưu. Sửa lại ô để thử lại.', 'error'); });
      });
    }
    box.addEventListener('change', function () { clearTimeout(timer); timer = setTimeout(save, 600); });
    box.addEventListener('focusout', function () { if (timer) { clearTimeout(timer); save(); } });
    if (box.tagName === 'FORM') box.addEventListener('submit', function (e) { e.preventDefault(); clearTimeout(timer); save(); });
  });
  window.addEventListener('beforeunload', function (e) {
    if (failed.size) { e.preventDefault(); e.returnValue = ''; }
  });
})();
