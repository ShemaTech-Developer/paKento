/* ================= paKento — Debt Ledger logic ================= */

let state = { user: null, debtors: [], calMonth: null, selectedDay: null, currentStudent: null, payDebt: null };
const $ = (id) => document.getElementById(id);

/* ---------- API ---------- */
const TOKEN_KEY = 'pakento_token';

const API = window.PAKENTO_API ||
  ((window.location.origin.includes('5500') || window.location.protocol === 'file:')
    ? 'http://localhost:5000'
    : '');

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res = await fetch(API + '/api' + path, {
    headers,
    credentials: 'include',
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Error ${res.status}`);
  return body;
}

const fmt = (n) => Number(n).toLocaleString();
const esc = (s) => String(s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let toastTimer;
function toast(msg, kind = 'ok') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast ' + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 2800);
}

/* ---------- Entry / login ---------- */
$('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const data = await api('/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('username').value.trim(), password: $('password').value }),
    });
    localStorage.setItem(TOKEN_KEY, data.token);
    state.user = data.user;
    enterApp();
  } catch (err) {
    $('login-error').textContent = err.message;
    $('login-error').classList.remove('hidden');
  }
});

function enterApp() {
  $('screen-entry').classList.remove('active');
  $('screen-app').classList.add('active');
  state.calMonth = new Date().toISOString().slice(0, 7);
  state.selectedDay = new Date().toISOString().slice(0, 10);
  refreshAll();
}

$('btn-logout').addEventListener('click', async () => {
  try { await api('/logout', { method: 'POST' }); } catch {}
  localStorage.removeItem(TOKEN_KEY);
  location.reload();
});

/* ---------- Tabs ---------- */
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('#screen-app .tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $('tab-' + btn.dataset.tab).classList.add('active');
  });
});

/* ---------- Load all ---------- */
async function refreshAll() {
  try {
    await loadStats();
    await loadToday();
    await loadDebtors();
    await loadCalendar();
    await loadDay(state.selectedDay);
  } catch (err) { toast(err.message, 'err'); }
}

async function loadStats() {
  const s = await api('/stats');
  $('stat-debtors').textContent = s.debtors;
  $('stat-owed').textContent = fmt(s.total_owed);
  $('stat-paid').textContent = fmt(s.paid_today);
  $('stat-newdebt').textContent = fmt(s.debts_today);
}

const dows = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const niceDate = (iso) => {
  const d = new Date(iso + 'T12:00:00');
  return `${dows[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })} ${d.getFullYear()}`;
};

/* ---------- Today's ledger ---------- */
async function loadToday() {
  const data = await api('/day');
  $('home-date').textContent = niceDate(data.date);
  $('today-list').innerHTML = data.entries.length
    ? data.entries.map(e => ledgerItem(e)).join('')
    : '<div class="empty">No money recorded today 🎉</div>';
}

function ledgerItem(e) {
  const used = e.remaining === 0;
  return `<div class="ledger-item ${used ? 'paid' : ''}">
    <div class="who">
      <span class="student-name">${esc(e.name)} <span class="muted">(${esc(e.class)})</span></span>
      <span class="when">${e.created_at.slice(11, 16)} · by ${esc(e.recorded_by)}</span>
    </div>
    <div style="text-align:right">
      <div class="amt ${used ? 'green' : 'red'}">${used ? 'USED' : fmt(e.remaining) + ' RWF'}</div>
      <span class="badge ${used ? 'green' : 'red'}">${used ? '✅ used' : '🏦 holds'}</span>
    </div>
  </div>`;
}

/* ---------- Debtors ---------- */
async function loadDebtors() {
  state.debtors = await api('/students');
  renderDebtors();
}

function renderDebtors() {
  const q = ($('debtors-search').value || '').trim().toLowerCase();
  // Debtors = students whose money the canteen is still holding (not used up)
  let list = state.debtors.filter(s => s.owes > 0);
  if (q) list = list.filter(s =>
    s.name.toLowerCase().includes(q) || s.class.toLowerCase().includes(q));
  const el = $('debtors-list');
  el.innerHTML = list.length ? '' : '<div class="empty">No debtors — every student\'s money is used up 🎉</div>';
  for (const s of list) {
    const div = document.createElement('div');
    div.className = 'student-item';
    div.dataset.id = s.id;
    const selected = state.selectMode && state.selected.has(s.id);
    if (selected) div.classList.add('selected');
    div.innerHTML = `
      ${state.selectMode
        ? `<button class="pick ${selected ? 'on' : ''}" data-id="${s.id}" title="Select to clear">${selected ? '✔' : ''}</button>`
        : ''}
      <div class="student-info">
        <span class="student-name">${esc(s.name)}</span>
        <span class="student-sub">${esc(s.class)}</span>
      </div>
      <div style="text-align:right">
        <div class="student-balance" style="font-weight:800;color:var(--accent)">
          ${fmt(s.owes)} RWF</div>
        <span class="badge red">🏦 canteen holds</span>
      </div>`;
    el.appendChild(div);
  }
  updateClearBar();
}

/* Selection mode + Clear (archive) */
state.selected = new Set();
state.selectMode = false;

function setSelectMode(on) {
  state.selectMode = on;
  if (!on) state.selected.clear();
  $('btn-select-mode').textContent = on ? '✖ Cancel' : '🔘 Select';
  $('btn-select-mode').classList.toggle('active', on);
  $('select-hint').classList.toggle('hidden', !on);
  renderDebtors();
}

$('btn-select-mode').addEventListener('click', () => setSelectMode(!state.selectMode));

$('debtors-list').addEventListener('click', (e) => {
  const row = e.target.closest('.student-item');
  if (!row) return;
  const id = +row.dataset.id;
  if (state.selectMode) {
    state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id);
    renderDebtors();
    return;
  }
  openDetail(id);
});

function updateClearBar() {
  const n = state.selected.size;
  $('clear-count').textContent = `${n} selected`;
  $('clear-bar').classList.toggle('hidden', n === 0);
}

$('btn-clear-selected').addEventListener('click', async () => {
  try {
    const res = await api('/archive', {
      method: 'POST',
      body: JSON.stringify({ student_ids: [...state.selected] }),
    });
    toast(`🧹 Cleared ${res.archived} entries — see History in Settings`, 'ok');
    state.selected.clear();
    state.selectMode = false;
    $('btn-select-mode').textContent = '🔘 Select';
    $('btn-select-mode').classList.remove('active');
    $('select-hint').classList.add('hidden');
    await refreshAll();
    // jump to Settings → History
    document.querySelector('[data-tab="settings"]').click();
    openHistory();
  } catch (err) { toast(err.message, 'err'); }
});

/* ---------- History (Settings) ---------- */
async function openHistory() {
  const box = $('history-box');
  try {
    const h = await api('/history');
    box.innerHTML = `
      <div class="hist-total">
        Total cleared all-time: <b>${fmt(h.total)} RWF</b>
        <span class="muted">(${h.entries.length} entries)</span>
      </div>
      ${h.entries.length ? h.entries.map(e => `
        <div class="history-item">
          <div>
            <div style="font-weight:700">${esc(e.name)} <span class="muted">(${esc(e.class)})</span></div>
            <div class="when">given ${e.created_at.slice(0, 10)} · used up ${e.cleared_at ? e.cleared_at.slice(0, 10) : '—'} · by ${esc(e.recorded_by)}</div>
          </div>
          <span class="badge green">✅ ${fmt(e.paid)} used</span>
        </div>`).join('')
        : '<div class="empty">Nothing cleared yet</div>'}`;
    box.classList.remove('hidden');
  } catch (err) { toast(err.message, 'err'); }
}
$('btn-open-history').addEventListener('click', () => {
  const box = $('history-box');
  box.classList.contains('hidden') ? openHistory() : box.classList.add('hidden');
});

$('debtors-search').addEventListener('input', renderDebtors);

/* ---------- Record debt (staff) ---------- */
document.querySelectorAll('#tab-record .chip, #modal-add .chip').forEach(c =>
  c.addEventListener('click', () => {
    const input = c.closest('.form').querySelector('input[type="number"]');
    input.value = c.dataset.amt;
  }));

$('debt-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await writeDebt({
    name: $('debt-name').value, class: $('debt-class').value,
    amount: +$('debt-amount').value,
  });
  $('debt-form').reset();
});

$('btn-add-student').addEventListener('click', () => $('modal-add').classList.remove('hidden'));

$('add-student-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const ok = await writeDebt({
    name: $('new-name').value, class: $('new-class').value,
    amount: +$('new-amount').value,
  });
  if (ok) { $('add-student-form').reset(); $('modal-add').classList.add('hidden'); }
});

async function writeDebt(payload) {
  try {
    await api('/debts', { method: 'POST', body: JSON.stringify(payload) });
    toast('🟢 Money recorded — canteen holds it', 'ok');
    await refreshAll();
    document.querySelector('[data-tab="home"]').click();
    return true;
  } catch (err) { toast(err.message, 'err'); return false; }
}

/* ---------- Edit student (floating tab) ---------- */
let editState = { id: null, op: null };

async function openDetail(id) {
  try {
    const s = await api(`/students/${id}`);
    editState = { id: s.id, op: null };
    $('edit-name').value = s.name;
    $('edit-class').value = s.class;
    $('edit-no').textContent = s.student_no;
    $('edit-amount').value = '';
    setOp(null);
    updateEditOwes(s.owes);
    renderEditHistory(s.history);
    $('modal-edit').classList.remove('hidden');
  } catch (err) { toast(err.message, 'err'); }
}

function updateEditOwes(owes) {
  $('edit-owes').textContent = fmt(owes);
  $('edit-owes-label').textContent = owes === 0 ? 'ALL USED UP ✅' : 'CANTEEN HOLDS';
  $('edit-owes-box').classList.toggle('ok', owes === 0);
}

function renderEditHistory(history) {
  $('edit-history').innerHTML = history.map(h => h.kind === 'debt'
    ? `<div class="history-item">
         <span>🟢 Money given to canteen</span>
         <span class="amt green">+${fmt(h.amount)}</span>
         <span class="when">${h.created_at.slice(0, 16)} · ${esc(h.by)}</span>
       </div>`
    : `<div class="history-item">
         <span>🛒 Money used (bought)</span>
         <span class="amt red">−${fmt(h.amount)}</span>
         <span class="when">${h.created_at.slice(0, 16)} · ${esc(h.by)}</span>
       </div>`).join('') || '<div class="empty">Nothing yet</div>';
}

/* ➕ / ➖ selection */
function setOp(op) {
  editState.op = op;
  $('pm-plus').classList.toggle('active', op === 'plus');
  $('pm-minus').classList.toggle('active', op === 'minus');
  const note = $('adjust-note');
  const amt = +$('edit-amount').value || 0;
  if (!op || !amt) {
    note.classList.add('hidden');
    return;
  }
  note.classList.remove('hidden');
  const who = $('edit-name').value.trim() || 'student';
  note.textContent = op === 'plus'
    ? `On save: ADD ${fmt(amt)} RWF — ${who} gave money to the canteen (➕)`
    : `On save: SUBTRACT ${fmt(amt)} RWF — ${who} used money (bought) (➖)`;
}
$('pm-plus').addEventListener('click', () => setOp('plus'));
$('pm-minus').addEventListener('click', () => setOp('minus'));
$('edit-amount').addEventListener('input', () => setOp(editState.op));

document.querySelectorAll('#modal-edit .chip').forEach(c =>
  c.addEventListener('click', () => {
    $('edit-amount').value = c.dataset.amt;
    setOp(editState.op);
  }));

/* Save Changes: 1) edit name/class  2) apply ➕/➖ adjustment */
$('edit-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await api(`/students/${editState.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name: $('edit-name').value, class: $('edit-class').value }),
    });

    const amt = +$('edit-amount').value || 0;
    if (editState.op && amt > 0) {
      const res = await api('/adjust', {
        method: 'POST',
        body: JSON.stringify({ student_id: editState.id, op: editState.op, amount: amt }),
      });
      toast(res.direction === 'added'
        ? `➕ ${fmt(amt)} RWF recorded — canteen holds more`
        : `➖ ${fmt(amt)} RWF used by the student`, 'ok');
    } else {
      toast('💾 Changes saved', 'ok');
    }
    $('modal-edit').classList.add('hidden');
    await refreshAll();
  } catch (err) { toast(err.message, 'err'); }
});

/* ---------- Calendar / timetable ---------- */
$('cal-prev').addEventListener('click', () => shiftMonth(-1));
$('cal-next').addEventListener('click', () => shiftMonth(1));

function shiftMonth(d) {
  const [y, m] = state.calMonth.split('-').map(Number);
  const dt = new Date(y, m - 1 + d, 15);
  state.calMonth = dt.toISOString().slice(0, 7);
  loadCalendar();
}

async function loadCalendar() {
  const [y, m] = state.calMonth.split('-');
  $('cal-month').textContent = new Date(y, m - 1, 1)
    .toLocaleString('en', { month: 'long', year: 'numeric' });
  const data = await api('/calendar?month=' + state.calMonth);
  const marks = Object.fromEntries(data.days.map(d => [d.day, d]));
  const first = new Date(y, m - 1, 1).getDay();
  const daysIn = new Date(y, m, 0).getDate();
  const todayIso = new Date().toISOString().slice(0, 10);
  let html = ['S', 'M', 'T', 'W', 'T', 'F', 'S'].map(d => `<div class="cal-dow">${d}</div>`).join('');
  html += '<div class="cal-day empty-cell"></div>'.repeat(first);
  for (let day = 1; day <= daysIn; day++) {
    const iso = `${state.calMonth}-${String(day).padStart(2, '0')}`;
    const mk = marks[iso];
    const cls = [
      'cal-day',
      mk ? (mk.unpaid > 0 ? 'red' : 'green') : '',
      iso === todayIso ? 'today' : '',
      iso === state.selectedDay ? 'selected' : '',
    ].join(' ');
    html += `<div class="${cls}" data-day="${iso}">${day}${mk ? '<span class="mark"></span>' : ''}</div>`;
  }
  $('cal-grid').innerHTML = html;
}

$('cal-grid').addEventListener('click', (e) => {
  const cell = e.target.closest('.cal-day[data-day]');
  if (!cell) return;
  state.selectedDay = cell.dataset.day;
  document.querySelectorAll('.cal-day.selected').forEach(c => c.classList.remove('selected'));
  cell.classList.add('selected');
  loadDay(state.selectedDay);
});

async function loadDay(iso) {
  const data = await api('/day?date=' + iso);
  $('day-title').innerHTML = `📅 ${niceDate(iso)} — <span class="${data.total_unpaid ? 'badge red' : 'badge green'}">${data.total_unpaid ? fmt(data.total_unpaid) + ' RWF held' : 'all used up'}</span>`;
  $('day-list').innerHTML = data.entries.length
    ? data.entries.map(e => ledgerItem(e)).join('')
    : '<div class="empty">No money recorded on this day</div>';
}

/* ---------- Settings: change password ---------- */
$('password-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  if ($('pw-new').value !== $('pw-new2').value) {
    toast('New passwords do not match', 'err');
    return;
  }
  try {
    await api('/change-password', {
      method: 'POST',
      body: JSON.stringify({ old: $('pw-old').value, new: $('pw-new').value }),
    });
    toast('🔑 Password updated', 'ok');
    $('password-form').reset();
  } catch (err) { toast(err.message, 'err'); }
});

/* ---------- Modals close ---------- */
document.querySelectorAll('[data-close]').forEach(b =>
  b.addEventListener('click', () => $(b.dataset.close).classList.add('hidden')));
