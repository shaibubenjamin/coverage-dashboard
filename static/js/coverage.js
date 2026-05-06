/* ═══════════════════════════════════════════════════════════════════
   SARMAAN II Coverage Dashboard — coverage.js
   ═══════════════════════════════════════════════════════════════════ */

/* ── Auth guard ─────────────────────────────────────────────────── */
const TOKEN = localStorage.getItem('access_token');
if (!TOKEN) { window.location = '/'; }

document.getElementById('userName').textContent =
  localStorage.getItem('user_name') || 'User';

/* ── API helper ─────────────────────────────────────────────────── */
async function api(url, opts = {}) {
  const res = await fetch(url, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) { localStorage.clear(); window.location = '/'; return; }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function logout() {
  localStorage.clear();
  window.location = '/';
}

/* ── Alert banner ────────────────────────────────────────────────── */
function showAlert(msg, type = 'info') {
  const el = document.getElementById('alertBanner');
  el.className = `alert-banner alert-${type}`;
  el.textContent = msg;
  el.style.display = 'block';
  if (type !== 'err') setTimeout(() => { el.style.display = 'none'; }, 5000);
}

function hideAlert() {
  document.getElementById('alertBanner').style.display = 'none';
}

/* ── Status dot ─────────────────────────────────────────────────── */
function setStatus(state, text) {
  const dot  = document.getElementById('statusDot');
  const span = document.getElementById('statusText');
  dot.className  = `status-dot status-${state}`;
  span.textContent = text;
}

/* ── Tab switching ──────────────────────────────────────────────── */
let _activeTab = 'demographics';
const _tabLoaded = {};

document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', () => {
    const tab = link.dataset.tab;
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    _activeTab = tab;
    if (!_tabLoaded[tab]) { loadTab(tab); _tabLoaded[tab] = true; }
  });
});

function loadTab(tab) {
  if (tab === 'demographics') loadDemographics();
  else if (tab === 'completeness') loadCompleteness();
  else if (tab === 'quality')      loadQuality();
  else if (tab === 'geospatial')   loadGeospatial();
  else if (tab === 'validators')   loadValidators(1);
}

/* ── Sync ────────────────────────────────────────────────────────── */
let _pollTimer = null;

async function syncData() {
  const btn   = document.getElementById('syncBtn');
  const icon  = document.getElementById('syncIcon');
  const label = document.getElementById('syncBtnLabel');
  btn.disabled = true;
  icon.className  = 'bi bi-arrow-repeat spinning';
  label.textContent = 'Syncing…';
  document.getElementById('loadingOverlay').style.display = 'flex';
  setStatus('syncing', 'Syncing…');
  hideAlert();
  try {
    await api('/api/coverage/sync', { method: 'POST' });
    pollSyncStatus();
  } catch (e) {
    showAlert(e.message, 'err');
    resetSyncBtn();
  }
}

function pollSyncStatus() {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = setInterval(async () => {
    try {
      const st = await api('/api/coverage/status');
      if (!st.syncing) {
        clearInterval(_pollTimer);
        document.getElementById('loadingOverlay').style.display = 'none';
        resetSyncBtn();
        if (st.error) {
          setStatus('error', 'Sync failed');
          showAlert('Sync error: ' + st.error, 'err');
        } else {
          setStatus('ok', 'Data loaded');
          document.getElementById('lastSyncedLabel').textContent =
            'Last sync: ' + (st.last_synced || 'unknown');
          Object.keys(_tabLoaded).forEach(k => delete _tabLoaded[k]);
          loadTab(_activeTab);
          showAlert(`Sync complete — ${st.rows.household} household records loaded.`, 'ok');
        }
      }
    } catch {}
  }, 2000);
}

function resetSyncBtn() {
  const btn  = document.getElementById('syncBtn');
  const icon = document.getElementById('syncIcon');
  const lbl  = document.getElementById('syncBtnLabel');
  btn.disabled     = false;
  icon.className   = 'bi bi-arrow-repeat';
  lbl.textContent  = 'Sync Data';
}

/* ─────────────────────────────────────────────────────────────────
   CHART INSTANCES (destroy before recreating)
─────────────────────────────────────────────────────────────────── */
const _charts = {};
function mkChart(id, config) {
  if (_charts[id]) _charts[id].destroy();
  const ctx = document.getElementById(id);
  if (!ctx) return;
  _charts[id] = new Chart(ctx, config);
}

const PALETTE = ['#2196F3','#4CAF50','#FF9800','#9C27B0','#F44336',
                  '#00BCD4','#FF5722','#3F51B5','#8BC34A','#FFC107'];

/* ═══════════════════════════════════════════════════════════════════
   TAB 1 — DEMOGRAPHICS
═══════════════════════════════════════════════════════════════════ */
async function loadDemographics() {
  try {
    const d = await api('/api/coverage/demographics');
    renderKPIRow1(d);
    renderKPIRow2(d);
    renderKPIRow3(d);
  } catch (e) {
    if (e.message.includes('503') || e.message.includes('not loaded')) {
      showSyncRequired('kpiRow1');
    } else showAlert(e.message, 'err');
    return;
  }

  // Charts & tables in parallel
  try { await loadDailyChart(); }      catch {}
  try { await loadLGAChart(); }        catch {}
  try { await loadRATable(); }         catch {}
  try { await loadSettlementTable(); } catch {}
  try { await loadCDDPie(); }          catch {}
}

function showSyncRequired(container) {
  const el = document.getElementById(container);
  if (el) el.innerHTML = `<div style="grid-column:1/-1;padding:32px;text-align:center;color:#64748b;background:#fff;border-radius:12px;border:1px solid #e2e8f0">
    <i class="bi bi-arrow-repeat" style="font-size:32px;display:block;margin-bottom:12px;color:#94a3b8"></i>
    No data loaded. Click <strong>Sync Data</strong> to pull from KoboToolbox.
  </div>`;
}

/* ── KPI Row 1: HH Submissions ─────────────────────────────────── */
function renderKPIRow1(d) {
  const pct = d.pct_of_planned;
  document.getElementById('kpiRow1').innerHTML = `
    ${kpiCard('Total Submissions', fmtN(d.total_submissions),
        `Planned: ${fmtN(d.planned_total)}`, pct,
        'Planned 1,700 households', '#2196F3')}
    ${kpiCard('Total Children', fmtN(d.total_children),
        'Currently in households', null, '', '#8b5cf6')}
    ${kpiCard('Total Eligible', fmtN(d.total_eligible),
        `${d.pct_eligible}% of all children`, d.pct_eligible,
        'Children aged 1–59 months', '#06b6d4')}
  `;
}

/* ── KPI Row 2: Child Coverage ─────────────────────────────────── */
function renderKPIRow2(d) {
  document.getElementById('kpiRow2').innerHTML = `
    ${kpiCard('Offered AZM', fmtN(d.offered_azm),
        `${d.pct_offered}% of eligible`, d.pct_offered,
        'Children offered azithromycin', '#4CAF50')}
    ${kpiCard('Not Offered AZM', fmtN(d.not_offered_azm),
        `${d.pct_not_offered}% of eligible`, null,
        'Children not offered AZM', '#F44336')}
    ${kpiCard('Swallowed AZM', fmtN(d.swallowed_azm),
        `${d.pct_swallowed}% of offered`, d.pct_swallowed,
        'Children who swallowed', '#22c55e')}
    ${kpiCard("Didn't Swallow", fmtN(d.didnt_swallow),
        `Of ${fmtN(d.offered_azm)} offered`, null,
        'AZM offered but not swallowed', '#f59e0b')}
    ${kpiCard('HH w/ Vaccine Card', fmtN(d.hh_vaccine_card),
        `${d.pct_vaccine_card}% of submissions`, d.pct_vaccine_card,
        'Households with vaccination card', '#3F51B5')}
  `;
}

/* ── KPI Row 3: Geographic Reach ───────────────────────────────── */
function renderKPIRow3(d) {
  document.getElementById('kpiRow3').innerHTML = `
    ${kpiCard('LGAs Reached', fmtN(d.lgas_reached),
        d.planned_lgas ? `of ${d.planned_lgas} planned` : 'LGAs visited',
        d.planned_lgas ? d.lgas_reached / d.planned_lgas * 100 : null,
        'Local Government Areas', '#FF9800')}
    ${kpiCard('Wards Reached', fmtN(d.wards_reached),
        d.planned_wards ? `of ${d.planned_wards} planned` : 'Wards visited',
        d.planned_wards ? d.wards_reached / d.planned_wards * 100 : null,
        'Wards covered', '#FF5722')}
    ${kpiCard('Communities Reached', fmtN(d.communities_reached),
        d.planned_communities ? `of ${d.planned_communities} planned` : 'Communities visited',
        d.planned_communities ? d.communities_reached / d.planned_communities * 100 : null,
        'Settlements / communities', '#009688')}
  `;
}

function kpiCard(label, value, sub, pct, tooltip, color) {
  const pctN   = Math.min(Math.max(parseFloat(pct) || 0, 0), 100);
  const hasBar = pct !== null && pct !== undefined;
  const badge  = hasBar
    ? `<span class="kpi-badge ${pctN >= 80 ? 'good' : pctN >= 50 ? 'warn' : 'bad'}">${pctN.toFixed(1)}%</span>`
    : '';
  return `
    <div class="kpi-card" style="--kpi-color:${color}" title="${tooltip}">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value">${value}</div>
      <div class="kpi-sub">${sub}</div>
      ${badge}
      ${hasBar ? `<div class="kpi-progress"><div class="kpi-progress-fill" style="width:${pctN}%"></div></div>` : ''}
    </div>`;
}

/* ── Daily Submissions Chart ────────────────────────────────────── */
async function loadDailyChart() {
  const d = await api('/api/coverage/charts/daily');
  mkChart('dailyChart', {
    type: 'bar',
    data: {
      labels: d.labels,
      datasets: [{
        label: 'Households Visited',
        data: d.values,
        backgroundColor: '#2196F3',
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 11 } } },
        y: { beginAtZero: true, grid: { color: '#f0f0f0' }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

/* ── LGA Progress Chart ─────────────────────────────────────────── */
async function loadLGAChart() {
  const d = await api('/api/coverage/charts/lga-progress');
  const rows = d.rows || [];
  const labels  = rows.map(r => r.lga);
  const reached = rows.map(r => r.reached);
  const planned = rows.map(r => r.planned);
  mkChart('lgaChart', {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Reached', data: reached, backgroundColor: '#22c55e', borderRadius: 4 },
        { label: 'Planned', data: planned, backgroundColor: '#e2e8f0', borderRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { position: 'top', labels: { font: { size: 11 } } } },
      scales: {
        x: { beginAtZero: true, grid: { color: '#f0f0f0' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

/* ── RA Table ────────────────────────────────────────────────────── */
async function loadRATable() {
  const d = await api('/api/coverage/charts/ra-performance');
  const tbody = document.getElementById('raTableBody');
  if (!d.rows || d.rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">No data</td></tr>`;
    return;
  }
  tbody.innerHTML = d.rows.map((r, i) => `
    <tr>
      <td>${i + 1}</td>
      <td class="fw-600">${r.ra || '—'}</td>
      <td>${r.lga || '—'}</td>
      <td>${fmtN(r.submissions)}</td>
      <td>${r.pct.toFixed(1)}%</td>
    </tr>`).join('');
}

/* ── Settlement Table ────────────────────────────────────────────── */
let _settlementRows = [];

async function loadSettlementTable() {
  const d = await api('/api/coverage/charts/settlement-table');
  _settlementRows = d.rows || [];
  renderSettlementTable(_settlementRows);
}

function renderSettlementTable(rows) {
  const tbody = document.getElementById('settlementTableBody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="loading-cell">No data</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const pct = r.pct;
    const badge = pct == null
      ? `<span class="coverage-badge cov-none">No plan</span>`
      : pct >= 80
        ? `<span class="coverage-badge cov-high">${pct}%</span>`
        : pct >= 50
          ? `<span class="coverage-badge cov-mid">${pct}%</span>`
          : `<span class="coverage-badge cov-low">${pct}%</span>`;
    const status = pct == null ? '—'
      : pct >= 100 ? '<span style="color:#16a34a;font-weight:600">✓ Complete</span>'
      : pct >= 80  ? '<span style="color:#d97706">On Track</span>'
      : '<span style="color:#dc2626">Below Target</span>';
    return `
      <tr>
        <td>${r.lga || '—'}</td>
        <td>${r.ward || '—'}</td>
        <td>${r.settlement || '—'}</td>
        <td>${r.planned ? fmtN(r.planned) : '—'}</td>
        <td>${fmtN(r.reached)}</td>
        <td>${badge}</td>
        <td>${status}</td>
      </tr>`;
  }).join('');
}

function filterSettlement() {
  const q = document.getElementById('settlementSearch').value.toLowerCase();
  if (!q) { renderSettlementTable(_settlementRows); return; }
  renderSettlementTable(_settlementRows.filter(r =>
    (r.lga + r.ward + r.settlement).toLowerCase().includes(q)));
}

/* ── CDD Pie Chart ───────────────────────────────────────────────── */
async function loadCDDPie() {
  const d = await api('/api/coverage/charts/cdd-visitation');
  mkChart('cddPieChart', {
    type: 'doughnut',
    data: {
      labels: ['Visited (Yes)', 'Not Visited (No)'],
      datasets: [{
        data: [d.yes, d.no],
        backgroundColor: ['#22c55e', '#F44336'],
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 16 } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct   = total ? (ctx.parsed / total * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${fmtN(ctx.parsed)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

/* ── AZM Pie Chart (Swallowed vs Didn't Swallow) ─────────────────── */
function renderAZMPie(offered, swallowed) {
  const notSwallowed = Math.max(offered - swallowed, 0);
  mkChart('azmPieChart', {
    type: 'doughnut',
    data: {
      labels: ['Swallowed AZM', "Didn't Swallow"],
      datasets: [{
        data: [swallowed, notSwallowed],
        backgroundColor: ['#2196F3', '#f59e0b'],
        borderWidth: 2,
        borderColor: '#fff',
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { font: { size: 12 }, padding: 16 } },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct   = total ? (ctx.parsed / total * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${fmtN(ctx.parsed)} (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 2 — COMPLETENESS
═══════════════════════════════════════════════════════════════════ */
async function loadCompleteness() {
  try {
    const d = await api('/api/coverage/completeness');
    renderFieldCompleteness(d.fields);
    renderCompletenessLGA(d.by_lga);
  } catch (e) {
    showAlert(e.message, 'err');
  }
}

function renderFieldCompleteness(fields) {
  const el = document.getElementById('fieldCompleteness');
  el.innerHTML = Object.entries(fields).map(([name, pct]) => {
    const col = pct >= 90 ? '#22c55e' : pct >= 70 ? '#f59e0b' : '#ef4444';
    return `
      <div class="comp-row">
        <div class="comp-label">${name}</div>
        <div class="comp-bar-wrap">
          <div class="comp-bar" style="width:${pct}%;background:${col}"></div>
        </div>
        <div class="comp-pct">${pct}%</div>
      </div>`;
  }).join('');
}

function renderCompletenessLGA(rows) {
  const tbody = document.getElementById('completenessLGABody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="loading-cell">No data</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const col = r.gps_pct >= 90 ? 'text-success' : r.gps_pct >= 70 ? 'text-warning' : 'text-danger';
    return `
      <tr>
        <td class="fw-600">${r.lga}</td>
        <td>${fmtN(r.total)}</td>
        <td>${fmtN(r.gps_ok)}</td>
        <td class="${col} fw-600">${r.gps_pct}%</td>
      </tr>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 3 — QUALITY CHECKS
═══════════════════════════════════════════════════════════════════ */
async function loadQuality() {
  try {
    const q = await api('/api/coverage/quality');
    renderQualityKPIs(q);
  } catch (e) { showAlert(e.message, 'err'); return; }
  try {
    const qt = await api('/api/coverage/quality/table');
    renderQualityTable(qt.rows || []);
  } catch {}
}

function renderQualityKPIs(q) {
  const raDiff = q.actual_ras - q.planned_ras;
  const raLabel = raDiff === 0 ? 'Exactly planned'
    : raDiff > 0 ? `+${raDiff} above planned`
    : `${raDiff} below planned`;

  document.getElementById('qualityKPIRow').innerHTML = `
    ${qCard('Duplicate HH Heads', q.duplicate_hh, 'Records with duplicate unique_code',
        q.duplicate_hh === 0 ? 'good' : 'bad', '#F44336')}
    ${qCard('Stacked GPS Points', q.stacked_gps, 'Records with duplicate coordinates',
        q.stacked_gps === 0 ? 'good' : q.stacked_gps < 5 ? 'warn' : 'bad', '#FF9800')}
    ${qCard('Research Assistants', `${q.actual_ras} / ${q.planned_ras}`,
        raLabel,
        q.actual_ras === q.planned_ras ? 'good' : 'warn', '#2196F3')}
    ${qCard('Mock GPS Records', q.mock_gps, 'GPS precision < 2 metres',
        q.mock_gps === 0 ? 'good' : q.mock_gps < 5 ? 'warn' : 'bad', '#9C27B0')}
    ${qCard('Total Records', q.total_records, 'All household submissions', null, '#64748b')}
  `;
}

function qCard(label, value, sub, badgeClass, color) {
  const badge = badgeClass
    ? `<span class="kpi-badge ${badgeClass}">${badgeClass === 'good' ? '✓ OK' : badgeClass === 'warn' ? '⚠ Review' : '✗ Error'}</span>`
    : '';
  return `
    <div class="kpi-card" style="--kpi-color:${color}">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value">${typeof value === 'number' ? fmtN(value) : value}</div>
      <div class="kpi-sub">${sub}</div>
      ${badge}
    </div>`;
}

function renderQualityTable(rows) {
  const tbody = document.getElementById('qualityTableBody');
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="loading-cell">No errors detected</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const errClass = r.error_pct >= 10 ? 'text-danger fw-600'
      : r.error_pct >= 5 ? 'text-warning fw-600' : '';
    return `
      <tr>
        <td>${r.lga || '—'}</td>
        <td>${r.ward || '—'}</td>
        <td>${r.settlement || '—'}</td>
        <td>${r.ra || '—'}</td>
        <td>${r.total}</td>
        <td>${r.duplicates ? `<span class="text-danger fw-600">${r.duplicates}</span>` : '0'}</td>
        <td>${r.stacked_gps ? `<span class="text-warning fw-600">${r.stacked_gps}</span>` : '0'}</td>
        <td>${r.mock_gps ? `<span class="text-warning fw-600">${r.mock_gps}</span>` : '0'}</td>
        <td class="${errClass}">${r.error_pct}%</td>
      </tr>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 4 — GEOSPATIAL
═══════════════════════════════════════════════════════════════════ */
let _map = null;
let _allPoints = [];
let _markers = null;

async function loadGeospatial() {
  try {
    const d = await api('/api/coverage/geospatial');
    _allPoints = d.points || [];

    // Populate LGA filter
    const sel = document.getElementById('geoLGAFilter');
    const lgas = [...new Set(_allPoints.map(p => p.lga).filter(Boolean))].sort();
    lgas.forEach(l => {
      const o = document.createElement('option');
      o.value = l; o.textContent = l;
      sel.appendChild(o);
    });

    initMap();
    renderMapPoints(_allPoints);
  } catch (e) {
    showAlert(e.message, 'err');
  }
}

function initMap() {
  if (_map) return;
  _map = L.map('coverageMap', {
    center: [13.05, 5.2],
    zoom: 8,
  });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 18,
  }).addTo(_map);
}

function renderMapPoints(points) {
  if (_markers) { _map.removeLayer(_markers); }
  const lgas = [...new Set(points.map(p => p.lga).filter(Boolean))].sort();
  const colorMap = {};
  lgas.forEach((l, i) => { colorMap[l] = PALETTE[i % PALETTE.length]; });

  _markers = L.layerGroup();
  points.forEach(p => {
    const col = colorMap[p.lga] || '#2196F3';
    const marker = L.circleMarker([p.lat, p.lon], {
      radius: 5,
      fillColor: col,
      color: '#fff',
      weight: 1,
      fillOpacity: 0.8,
    });
    marker.bindPopup(`<strong>${p.lga || 'Unknown LGA'}</strong><br>
      Lat: ${p.lat.toFixed(5)}<br>Lon: ${p.lon.toFixed(5)}`);
    _markers.addLayer(marker);
  });
  _markers.addTo(_map);

  document.getElementById('mapPointCount').textContent = `${fmtN(points.length)} points`;
  if (points.length > 0) {
    const bounds = L.latLngBounds(points.map(p => [p.lat, p.lon]));
    _map.fitBounds(bounds, { padding: [24, 24] });
  }
}

function filterMapPoints() {
  const lga = document.getElementById('geoLGAFilter').value;
  const pts  = lga ? _allPoints.filter(p => p.lga === lga) : _allPoints;
  renderMapPoints(pts);
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 5 — VALIDATORS
═══════════════════════════════════════════════════════════════════ */
let _valPage    = 1;
let _valTotal   = 0;
const _PER_PAGE = 50;

async function loadValidators(page = 1) {
  _valPage = page;
  const lga = document.getElementById('valLGAFilter').value;
  try {
    const d = await api(`/api/coverage/validators?page=${page}&per_page=${_PER_PAGE}&lga=${encodeURIComponent(lga)}`);
    _valTotal = d.total;

    // Populate LGA filter once
    const sel = document.getElementById('valLGAFilter');
    if (sel.options.length <= 1 && d.lgas && d.lgas.length) {
      d.lgas.forEach(l => {
        const o = document.createElement('option');
        o.value = l; o.textContent = l;
        sel.appendChild(o);
      });
    }

    renderValidatorTable(d.records);
    renderValidatorPagination(d.total, page);
  } catch (e) { showAlert(e.message, 'err'); }
}

const _STATUS_OPTS = ['Not Started', 'Approved', 'Not Approached'];

function renderValidatorTable(records) {
  const tbody = document.getElementById('validatorTableBody');
  if (!records.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="loading-cell">No records</td></tr>`;
    return;
  }

  tbody.innerHTML = records.map((r, i) => {
    const status  = r.status || 'Not Started';
    const selCls  = status === 'Approved' ? 'approved'
      : status === 'Not Approached' ? 'not-approached' : 'not-started';
    const opts = _STATUS_OPTS.map(s =>
      `<option value="${s}" ${s === status ? 'selected' : ''}>${s}</option>`).join('');
    const rowIdx = (_valPage - 1) * _PER_PAGE + i;

    return `
      <tr>
        <td>${r.ra || '—'}</td>
        <td>${r.lga || '—'}</td>
        <td>${r.ward || '—'}</td>
        <td>${r.community || '—'}</td>
        <td class="fw-600">${r.head_name || '—'}</td>
        <td>${r.head_gender || '—'}</td>
        <td style="max-width:200px;font-size:12px">${r.children || '—'}</td>
        <td>
          <select class="val-status-select ${selCls}"
                  onchange="updateStatus(${rowIdx}, this)">
            ${opts}
          </select>
        </td>
      </tr>`;
  }).join('');
}

async function updateStatus(idx, sel) {
  const status = sel.value;
  sel.className = `val-status-select ${status === 'Approved' ? 'approved'
    : status === 'Not Approached' ? 'not-approached' : 'not-started'}`;
  try {
    await api('/api/coverage/validators/status', {
      method: 'PUT',
      body: JSON.stringify({ idx, status }),
    });
  } catch (e) {
    showAlert('Could not save status: ' + e.message, 'err');
  }
}

function renderValidatorPagination(total, page) {
  const totalPages = Math.ceil(total / _PER_PAGE);
  const info = document.getElementById('valPagInfo');
  const ctrl = document.getElementById('valPagControls');
  const start = (page - 1) * _PER_PAGE + 1;
  const end   = Math.min(page * _PER_PAGE, total);
  info.textContent = `Showing ${fmtN(start)}–${fmtN(end)} of ${fmtN(total)} records`;

  let btns = `<button class="pag-btn" onclick="loadValidators(${page - 1})"
    ${page <= 1 ? 'disabled' : ''}>&lsaquo; Prev</button>`;

  const maxBtns = 7;
  let startP = Math.max(1, page - 3);
  let endP   = Math.min(totalPages, startP + maxBtns - 1);
  startP = Math.max(1, endP - maxBtns + 1);

  for (let p = startP; p <= endP; p++) {
    btns += `<button class="pag-btn ${p === page ? 'active' : ''}"
      onclick="loadValidators(${p})">${p}</button>`;
  }
  btns += `<button class="pag-btn" onclick="loadValidators(${page + 1})"
    ${page >= totalPages ? 'disabled' : ''}>Next &rsaquo;</button>`;

  ctrl.innerHTML = btns;
}

/* ═══════════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════════ */
(async function init() {
  // Check sync status
  try {
    const st = await api('/api/coverage/status');
    if (st.syncing) {
      setStatus('syncing', 'Sync in progress…');
      pollSyncStatus();
    } else if (st.loaded) {
      setStatus('ok', 'Data loaded');
      document.getElementById('lastSyncedLabel').textContent =
        'Last sync: ' + (st.last_synced || 'unknown');
      loadDemographics();
      _tabLoaded['demographics'] = true;
    } else if (st.error) {
      setStatus('error', 'Last sync failed');
      showAlert('Previous sync failed: ' + st.error, 'err');
    }
  } catch {}
})();

/* ── Helpers ─────────────────────────────────────────────────────── */
function fmtN(n) {
  if (n == null || n === '') return '0';
  return Number(n).toLocaleString('en');
}
