// ---------- Утилиты ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('show'), 2600);
}

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    showLogin();
    throw new Error('unauthorized');
  }
  if (!res.ok) {
    let detail = 'Ошибка запроса';
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    toast('❌ ' + detail);
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
function fmtDateTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function isoDate(d) {
  return d.toISOString().slice(0, 10);
}
function mondayOf(date) {
  const d = new Date(date);
  const day = (d.getDay() + 6) % 7; // 0 = понедельник
  d.setDate(d.getDate() - day);
  d.setHours(0, 0, 0, 0);
  return d;
}

// ---------- Авторизация ----------
function showLogin() {
  $('#app').classList.add('hidden');
  $('#login-screen').classList.remove('hidden');
}
function showApp() {
  $('#login-screen').classList.add('hidden');
  $('#app').classList.remove('hidden');
  bootstrap();
}

$('#login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = $('#login-password').value;
  try {
    await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }).then(async (res) => {
      if (!res.ok) throw new Error((await res.json()).detail || 'Ошибка входа');
      showApp();
    });
  } catch (err) {
    $('#login-error').textContent = err.message;
  }
});

$('#logout-btn').addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  showLogin();
});

// Проверяем, есть ли уже валидная сессия
(async function initialCheck() {
  try {
    await api('/positions');
    showApp();
  } catch (e) {
    showLogin();
  }
})();

// ---------- Навигация ----------
let POSITIONS = [];
let WARNING_LEVELS = [];
let MEMBERS = [];
let POINT_SETTINGS = [];

$$('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function switchView(view) {
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.view === view));
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === 'view-' + view));
  const loaders = {
    roster: loadRoster,
    points: loadPoints,
    reports: loadReports,
    summary: loadSummary,
    warnings: loadWarnings,
    norms: loadNorms,
    events: loadEvents,
  };
  loaders[view] && loaders[view]();
}

async function bootstrap() {
  POSITIONS = await api('/positions');
  WARNING_LEVELS = await api('/warning-levels');
  fillPositionSelect($('#member-position-select'));
  fillWarningLevelSelect($('#warning-level-select'));
  await refreshMembers();
  await refreshPointSettings();
  switchView('roster');
}

async function refreshMembers() {
  MEMBERS = await api('/members');
  fillMemberSelect($('#report-member-select'));
  fillMemberSelect($('#warning-member-select'));
}
async function refreshPointSettings() {
  POINT_SETTINGS = await api('/point-settings');
}

function fillPositionSelect(select) {
  select.innerHTML = POSITIONS.map((p) => `<option value="${p.key}">${p.label}</option>`).join('');
}
function fillWarningLevelSelect(select) {
  select.innerHTML = WARNING_LEVELS.map((w) => `<option value="${w.key}">${w.label}</option>`).join('');
}
function fillMemberSelect(select) {
  select.innerHTML = MEMBERS.map((m) => `<option value="${m.id}">${m.full_name} (${m.static_id})</option>`).join('');
}

// ---------- Модалки ----------
$$('[data-open-modal]').forEach((btn) => {
  btn.addEventListener('click', () => openModal(btn.dataset.openModal));
});
$$('[data-close-modal]').forEach((btn) => {
  btn.addEventListener('click', () => closeModal(btn.closest('.modal-backdrop').id));
});
function openModal(id) { $('#' + id).classList.add('open'); }
function closeModal(id) { $('#' + id).classList.remove('open'); }

// ========== СОСТАВ ==========
let editingMemberId = null;

async function loadRoster() {
  const container = $('#roster-groups');
  container.innerHTML = '';
  await refreshMembers();
  for (const pos of POSITIONS) {
    const group = MEMBERS.filter((m) => m.position_key === pos.key);
    if (!group.length) continue;
    const wrap = document.createElement('div');
    wrap.innerHTML = `<div class="roster-group-title">${pos.label} · ${group.length}</div>
      <div class="member-grid">${group.map(memberCardHtml).join('')}</div>`;
    container.appendChild(wrap);
  }
  if (!MEMBERS.length) container.innerHTML = '<p class="muted">Состав пуст. Добавьте первого сотрудника.</p>';
  $$('.member-card [data-edit]').forEach((b) => b.addEventListener('click', (e) => { e.stopPropagation(); openMemberEdit(+b.dataset.edit); }));
  $$('.member-card [data-del]').forEach((b) => b.addEventListener('click', (e) => { e.stopPropagation(); deleteMember(+b.dataset.del); }));
}

function memberCardHtml(m) {
  return `<div class="member-card">
    <div class="actions">
      <button class="btn-small" data-edit="${m.id}">✎</button>
      <button class="btn-small" data-del="${m.id}">✕</button>
    </div>
    <div class="name">${m.full_name}</div>
    <div class="static">STATIC ${m.static_id}</div>
  </div>`;
}

function openMemberEdit(id) {
  const m = MEMBERS.find((x) => x.id === id);
  editingMemberId = id;
  const form = $('#form-member');
  form.first_name.value = m.first_name;
  form.last_name.value = m.last_name;
  form.static_id.value = m.static_id;
  form.position.value = m.position_key;
  form.discord_id.value = m.discord_id || '';
  $('#modal-member h3').textContent = 'Изменить сотрудника';
  openModal('modal-member');
}

$('#form-member').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = {
    first_name: f.first_name.value.trim(),
    last_name: f.last_name.value.trim(),
    static_id: f.static_id.value.trim(),
    position: f.position.value,
    discord_id: f.discord_id.value ? Number(f.discord_id.value) : null,
  };
  if (editingMemberId) {
    await api(`/members/${editingMemberId}`, { method: 'PUT', body });
    toast('✅ Данные обновлены');
  } else {
    await api('/members', { method: 'POST', body });
    toast('✅ Сотрудник добавлен');
  }
  editingMemberId = null;
  $('#modal-member h3').textContent = 'Добавить сотрудника';
  f.reset();
  closeModal('modal-member');
  loadRoster();
});

async function deleteMember(id) {
  if (!confirm('Удалить сотрудника из состава?')) return;
  await api(`/members/${id}`, { method: 'DELETE' });
  toast('Сотрудник удалён');
  loadRoster();
}

// сброс режима редактирования при открытии модалки "с нуля"
$('[data-open-modal="modal-member"]').addEventListener('click', () => {
  editingMemberId = null;
  $('#modal-member h3').textContent = 'Добавить сотрудника';
  $('#form-member').reset();
});

// ========== БАЛЛЫ — НАСТРОЙКА ==========
async function loadPoints() {
  await refreshPointSettings();
  const tbody = $('#points-tbody');
  tbody.innerHTML = POINT_SETTINGS.map((s) => `
    <tr>
      <td>${s.title}</td>
      <td>${s.points}</td>
      <td><button class="btn-small" data-del-point="${s.id}">Удалить</button></td>
    </tr>`).join('') || '<tr><td colspan="3" class="muted">Пока нет ни одного вида работы</td></tr>';
  $$('[data-del-point]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Удалить вид работы?')) return;
    await api(`/point-settings/${b.dataset.delPoint}`, { method: 'DELETE' });
    toast('Удалено');
    loadPoints();
  }));
}

$('#form-point').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  await api('/point-settings', { method: 'POST', body: { title: f.title.value.trim(), points: Number(f.points.value) } });
  toast('✅ Вид работы добавлен');
  f.reset();
  closeModal('modal-point');
  loadPoints();
});

// ========== ОТЧЁТЫ ==========
let reportsWeek = mondayOf(new Date());

function weekLabel(monday) {
  const end = new Date(monday);
  end.setDate(end.getDate() + 6);
  return `${monday.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })} — ${end.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })}`;
}

$('#reports-week-prev').addEventListener('click', () => { reportsWeek.setDate(reportsWeek.getDate() - 7); loadReports(); });
$('#reports-week-next').addEventListener('click', () => { reportsWeek.setDate(reportsWeek.getDate() + 7); loadReports(); });

async function loadReports() {
  $('#reports-week-label').textContent = weekLabel(reportsWeek);
  const reports = await api('/reports?week_start=' + isoDate(reportsWeek));
  const list = $('#reports-list');
  if (!reports.length) {
    list.innerHTML = '<p class="muted">Отчётов за эту неделю ещё нет.</p>';
    return;
  }
  list.innerHTML = reports.map((r) => `
    <div class="item-card">
      <div class="item-top">
        <span class="item-title">${r.member_name}</span>
        <span class="item-points">${r.total_points} баллов</span>
      </div>
      <div class="item-sub">Сдан: ${fmtDateTime(r.submitted_at)}</div>
      ${r.content ? `<div class="item-lines">${r.content}</div>` : ''}
      ${r.items.length ? `<div class="item-lines">${r.items.map((i) => `• ${i.title} × ${i.quantity} (${i.points_at_submission * i.quantity} б.)`).join('<br>')}</div>` : ''}
    </div>`).join('');
}

let reportItemRowCount = 0;
function addReportItemRow() {
  reportItemRowCount++;
  const row = document.createElement('div');
  row.className = 'report-item-row';
  row.innerHTML = `
    <select class="report-item-setting">${POINT_SETTINGS.map((s) => `<option value="${s.id}">${s.title} (${s.points} б.)</option>`).join('')}</select>
    <input type="number" class="report-item-qty" value="1" min="1">
    <button type="button" class="btn-small" data-remove-row>✕</button>`;
  row.querySelector('[data-remove-row]').addEventListener('click', () => row.remove());
  $('#report-items').appendChild(row);
}
$('#report-add-item').addEventListener('click', addReportItemRow);
$('[data-open-modal="modal-report"]').addEventListener('click', () => {
  fillMemberSelect($('#report-member-select'));
  $('#report-items').innerHTML = '';
  reportItemRowCount = 0;
  addReportItemRow();
});

$('#form-report').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  const items = $$('.report-item-row').map((row) => ({
    point_setting_id: Number(row.querySelector('.report-item-setting').value),
    quantity: Number(row.querySelector('.report-item-qty').value) || 1,
  }));
  await api('/reports', {
    method: 'POST',
    body: {
      member_id: Number(f.member_id.value),
      content: f.content.value.trim(),
      week_start: isoDate(reportsWeek),
      items,
    },
  });
  toast('✅ Отчёт сохранён');
  f.reset();
  closeModal('modal-report');
  loadReports();
});

// ========== СВОДКА ==========
let summaryWeek = mondayOf(new Date());
$('#summary-week-prev').addEventListener('click', () => { summaryWeek.setDate(summaryWeek.getDate() - 7); loadSummary(); });
$('#summary-week-next').addEventListener('click', () => { summaryWeek.setDate(summaryWeek.getDate() + 7); loadSummary(); });

async function loadSummary() {
  $('#summary-week-label').textContent = weekLabel(summaryWeek);
  const rows = await api('/reports/summary?week_start=' + isoDate(summaryWeek));
  const submitted = rows.filter((r) => r.submitted);
  $('#summary-stats').innerHTML = `
    <div class="stat-box"><div class="stat-num">${submitted.length}/${rows.length}</div><div class="stat-label">Сдали отчёт</div></div>
    <div class="stat-box"><div class="stat-num">${submitted.reduce((s, r) => s + r.points, 0)}</div><div class="stat-label">Баллов начислено</div></div>
    <div class="stat-box"><div class="stat-num">${rows.length - submitted.length}</div><div class="stat-label">Не сдали</div></div>`;

  $('#summary-tbody').innerHTML = rows.map((r) => `
    <tr>
      <td>${r.member_name}</td>
      <td class="muted">${r.position}</td>
      <td>${r.submitted ? '<span class="badge badge-good">Сдан</span>' : '<span class="badge badge-bad">Не сдан</span>'}</td>
      <td>${r.points}</td>
    </tr>`).join('');
}

// ========== ВЫГОВОРЫ ==========
async function loadWarnings() {
  fillMemberSelect($('#warning-member-select'));
  const warnings = await api('/warnings');
  $('#warnings-tbody').innerHTML = warnings.map((w) => `
    <tr>
      <td>${w.member_name}</td>
      <td>${warningBadge(w.level)}</td>
      <td>${w.reason}</td>
      <td class="muted">${w.issued_by}</td>
      <td class="muted">${fmtDate(w.issued_at)}</td>
      <td><button class="btn-small" data-del-warn="${w.id}">Снять</button></td>
    </tr>`).join('') || '<tr><td colspan="6" class="muted">Выговоров нет</td></tr>';
  $$('[data-del-warn]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('Снять выговор?')) return;
    await api(`/warnings/${b.dataset.delWarn}`, { method: 'DELETE' });
    toast('Выговор снят');
    loadWarnings();
  }));
}
function warningBadge(level) {
  if (level.includes('Понижение')) return `<span class="badge badge-bad">${level}</span>`;
  if (level.includes('2')) return `<span class="badge badge-warn">${level}</span>`;
  return `<span class="badge badge-warn" style="opacity:.7">${level}</span>`;
}

$('#form-warning').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  await api('/warnings', {
    method: 'POST',
    body: { member_id: Number(f.member_id.value), level: f.level.value, reason: f.reason.value.trim() },
  });
  toast('⚠️ Выговор выдан');
  f.reset();
  closeModal('modal-warning');
  loadWarnings();
});

// ========== ДНЕВНАЯ НОРМА ==========
$('#norms-range').addEventListener('change', loadNorms);

async function loadNorms() {
  const days = Number($('#norms-range').value);
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  const data = await api(`/norms?start=${isoDate(start)}&end=${isoDate(end)}`);
  const table = $('#norms-table');

  const thead = `<thead><tr><th>Сотрудник</th>${data.days.map((d) => `<th class="norm-day">${d.slice(8, 10)}.${d.slice(5, 7)}</th>`).join('')}</tr></thead>`;
  const rows = data.rows.map((row) => `
    <tr>
      <td>${row.member_name}</td>
      ${data.days.map((d) => {
        const day = row.days[d];
        return `<td class="norm-cell" title="Холл: ${day.hall_hour_done ? 'да' : 'нет'} · Волна: ${day.gov_wave_done ? 'да' : 'нет'}">
          <span class="norm-dot ${day.completed ? 'done' : 'undone'}"></span>
        </td>`;
      }).join('')}
    </tr>`).join('');
  table.innerHTML = thead + `<tbody>${rows || `<tr><td colspan="${data.days.length + 1}" class="muted">Состав пуст</td></tr>`}</tbody>`;
}

// ========== СОБЫТИЯ ==========
async function loadEvents() {
  const events = await api('/events?upcoming_only=false');
  const list = $('#events-list');
  if (!events.length) {
    list.innerHTML = '<p class="muted">Событий пока нет.</p>';
    return;
  }
  list.innerHTML = events.map((e) => `
    <div class="item-card event-card" data-event="${e.id}">
      <div class="item-top">
        <span class="item-title">${e.title}</span>
        <span class="item-points">${fmtDateTime(e.event_datetime)}</span>
      </div>
      ${e.description ? `<div class="item-sub">${e.description}</div>` : ''}
    </div>`).join('');
  $$('[data-event]').forEach((card) => card.addEventListener('click', () => openEventDetail(+card.dataset.event)));
}

$('#form-event').addEventListener('submit', async (e) => {
  e.preventDefault();
  const f = e.target;
  await api('/events', {
    method: 'POST',
    body: { title: f.title.value.trim(), description: f.description.value.trim(), event_datetime: f.event_datetime.value },
  });
  toast('✅ Событие создано, состав приглашён');
  f.reset();
  closeModal('modal-event');
  loadEvents();
});

async function openEventDetail(id) {
  const e = await api(`/events/${id}`);
  $('#event-detail-title').textContent = e.title;
  $('#event-detail-meta').textContent = `${fmtDateTime(e.event_datetime)}${e.description ? ' · ' + e.description : ''}`;
  $('#event-detail-attendance').innerHTML = e.attendance.map((a) => `
    <div class="attendance-row" data-att-member="${a.member_id}">
      <span>${a.member_name}</span>
      <span class="att-btns">
        <button class="att-btn yes ${a.present === true ? 'on' : ''}" data-present="true">Был</button>
        <button class="att-btn no ${a.present === false ? 'on' : ''}" data-present="false">Не был</button>
      </span>
    </div>`).join('');
  $$('#event-detail-attendance .att-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const row = btn.closest('[data-att-member]');
      const memberId = Number(row.dataset.attMember);
      const present = btn.dataset.present === 'true';
      await api(`/events/${id}/attendance`, { method: 'POST', body: { member_id: memberId, present } });
      openEventDetail(id);
    });
  });
  openModal('modal-event-detail');
}
