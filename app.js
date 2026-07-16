/**
 * Bulls & Bears Fundamentals — Main SPA Controller
 * Handles tab routing, data loading, rendering, and dark mode.
 */

// ═══════════════════════════════════════════════════════════════════════════
// ── State ──────────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

const state = {
  fredData: null,
  cftcData: null,
  yieldData: null,
  calendarData: null,
  newsData: null,
  scoresData: null,
  pairsData: null,
  setupsData: null,
  usdBiasData: null,
  
  charts: [],
  currentFilter: '',
  isLoading: true,
  expandedRows: new Set(),
  loadErrors: [],
};

// ── Data Loading ──────────────────────────────────────────────────────────

async function loadAllData() {
  state.isLoading = true;
  state.loadErrors = [];
  showLoading(true);
  hideError();

  const dataFiles = [
    { key: 'fredData',      path: 'data/fred_historical.json' },
    { key: 'cftcData',      path: 'data/cftc_historical.json' },
    { key: 'yieldData',     path: 'data/yields.json' },
    { key: 'calendarData',  path: 'data/calendar_surprises.json' },
    { key: 'newsData',      path: 'data/news_feed.json' },
    { key: 'scoresData',    path: 'data/scores.json' },
    { key: 'pairsData',     path: 'data/pairs_bias.json' },
    { key: 'setupsData',    path: 'data/trade_setups.json' },
    { key: 'usdBiasData',   path: 'data/usd_bias.json' },
  ];

  const results = await Promise.allSettled(
    dataFiles.map(async ({ key, path }) => {
      const resp = await fetch(path);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${path}`);
      const json = await resp.json();
      state[key] = json;
    })
  );

  // Log any failures and show error banner
  results.forEach((result, i) => {
    if (result.status === 'rejected') {
      const errMsg = `Failed to load ${dataFiles[i].path}: ${result.reason}`;
      console.warn(errMsg);
      state.loadErrors.push(errMsg);
    }
  });

  if (state.loadErrors.length > 0) {
    showError(state.loadErrors[0]);
  }

  state.isLoading = false;
  showLoading(false);
  
  // Render all tabs
  renderHomeTab();
  renderBiasTab();
  renderFredTab();
  renderCftcTab();
  renderYieldsTab();
  renderSetupsTab();
  renderNewsTab();
  renderAITab();
}

function showLoading(show) {
  const spinner = document.getElementById('loading-spinner');
  if (spinner) spinner.style.display = show ? 'flex' : 'none';
}

function showError(message) {
  const banner = document.getElementById('error-banner');
  const details = document.getElementById('error-details');
  if (banner && details) {
    banner.classList.remove('d-none');
    details.textContent = message;
  }
}

function hideError() {
  const banner = document.getElementById('error-banner');
  if (banner) banner.classList.add('d-none');
}

// ═══════════════════════════════════════════════════════════════════════════
// ── Tab System ─────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function openTab(tabName) {
  // Update nav tabs
  document.querySelectorAll('.nav-link').forEach(el => {
    el.classList.remove('active');
  });
  const tabTrigger = document.querySelector(`[data-tab="${tabName}"]`);
  if (tabTrigger) tabTrigger.classList.add('active');

  // Update tab panes
  document.querySelectorAll('.tab-pane').forEach(el => {
    el.classList.remove('show', 'active');
  });
  const pane = document.getElementById(`tab-${tabName}`);
  if (pane) pane.classList.add('show', 'active');

  // Lazy render charts if coming to FRED/CFTC tabs
  if (tabName === 'fred' && state.fredData) {
    renderFredCharts();
  }
  if (tabName === 'cftc' && state.cftcData) {
    renderCftcCharts();
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ── Dark Mode ──────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function toggleDarkMode() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const icon = document.getElementById('mode-icon');
  if (isDark) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('theme', 'light');
    if (icon) icon.textContent = '🌙';
  } else {
    document.documentElement.setAttribute('data-theme', 'dark');
    localStorage.setItem('theme', 'dark');
    if (icon) icon.textContent = '☀️';
  }
  // Update chart themes
  const nonNullCharts = state.charts.filter(c => c !== null && c !== undefined);
  updateChartTheme(nonNullCharts);
}

function initTheme() {
  const saved = localStorage.getItem('theme');
  const icon = document.getElementById('mode-icon');
  if (saved === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    if (icon) icon.textContent = '☀️';
  } else {
    if (icon) icon.textContent = '🌙';
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 1: Home / Overview ────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderHomeTab() {
  const container = document.getElementById('tab-home');
  if (!container) return;

  const usd = state.usdBiasData || {};
  const scores = state.scoresData || {};
  const usdScore = scores['USD'] || {};
  const fred = state.fredData || {};

  // Latest FRED values
  const latestFred = {};
  if (fred.series) {
    fred.series.forEach(s => {
      if (!latestFred[s.series_id] || s.date > latestFred[s.series_id].date) {
        if (!latestFred[s.series_id]) latestFred[s.series_id] = {};
        latestFred[s.series_id] = { value: s.value, date: s.date, unit: s.unit };
      }
    });
  }

  // Determine last updated
  const lastUpdated = usd.updated_at || pairsDataUpdated() || 'N/A';
  const formattedDate = lastUpdated !== 'N/A' 
    ? new Date(lastUpdated).toLocaleString('en-US', { 
        year: 'numeric', month: 'short', day: 'numeric', 
        hour: '2-digit', minute: '2-digit' 
      })
    : 'N/A';

  container.innerHTML = `
    <div class="row mb-4">
      <div class="col-12">
        <div class="d-flex justify-content-between align-items-start">
          <div>
            <h1 class="gov-header" style="font-size: 1.8rem;">USD Fundamental Health Dashboard</h1>
            <p class="gov-subheader">Last updated: ${formattedDate}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Key Stats -->
    <div class="row g-3 mb-4">
      <div class="col-6 col-md-3">
        <div class="card stat-card">
          <div class="stat-value ${(latestFred['GDPC1']?.value || 0) > 20000 ? 'text-bullish' : 'text-bearish'}">
            ${latestFred['GDPC1'] ? '$' + (latestFred['GDPC1'].value / 1000).toFixed(1) + 'T' : '—'}
          </div>
          <div class="stat-label">GDP (Real)</div>
          <div class="stat-change ${(latestFred['GDPC1']?.value || 0) > 20000 ? 'text-bullish' : 'text-bearish'}">
            ${latestFred['GDPC1']?.date || ''}
          </div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card stat-card">
          <div class="stat-value ${(latestFred['CPILFESL']?.value || 300) < 320 ? 'text-bullish' : 'text-bearish'}">
            ${latestFred['CPILFESL'] ? latestFred['CPILFESL'].value.toFixed(1) : '—'}
          </div>
          <div class="stat-label">Core CPI</div>
          <div class="stat-change">${latestFred['CPILFESL']?.date || ''}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card stat-card">
          <div class="stat-value ${(latestFred['UNRATE']?.value || 5) < 5 ? 'text-bullish' : 'text-bearish'}">
            ${latestFred['UNRATE'] ? latestFred['UNRATE'].value.toFixed(1) + '%' : '—'}
          </div>
          <div class="stat-label">Unemployment Rate</div>
          <div class="stat-change">${latestFred['UNRATE']?.date || ''}</div>
        </div>
      </div>
      <div class="col-6 col-md-3">
        <div class="card stat-card">
          <div class="stat-value ${(latestFred['FEDFUNDS']?.value || 4) > 3 ? 'text-bullish' : 'text-bearish'}">
            ${latestFred['FEDFUNDS'] ? latestFred['FEDFUNDS'].value.toFixed(2) + '%' : '—'}
          </div>
          <div class="stat-label">Fed Funds Rate</div>
          <div class="stat-change">${latestFred['FEDFUNDS']?.date || ''}</div>
        </div>
      </div>
    </div>

    <div class="row g-4">
      <!-- USD Gauge -->
      <div class="col-md-5">
        <div class="card">
          <div class="card-header">USD Combined Bias Score</div>
          <div class="card-body">
            <div class="gauge-container">
              <canvas id="usd-gauge" height="220" style="max-width: 250px; margin: 0 auto;"></canvas>
              <div class="gauge-label mt-2">Overall USD Fundamental Score</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Score Breakdown -->
      <div class="col-md-7">
        <div class="card">
          <div class="card-header">Component Scores Breakdown</div>
          <div class="card-body p-3">
            ${renderScoreBreakdown(usdScore)}
          </div>
        </div>
      </div>
    </div>

    <!-- CTA Banner -->
    <div class="row mt-4">
      <div class="col-12">
        <div class="cta-banner">
          <h3>Trade with Confidence — Partner Offer</h3>
          <p class="mb-2">Get exclusive access to premium trading tools through our partner Tradersyard.</p>
          <div class="mb-3">
            <span class="discount-code">ROSHAN</span>
            <span class="ms-2">— Use code for special discount</span>
          </div>
          <a href="https://shop.tradersyard.com/ref/1486/" target="_blank" rel="noopener" class="cta-btn">
            Visit Tradersyard →
          </a>
        </div>
      </div>
    </div>
  `;

  // Draw gauge chart — destroy existing if present
  state.charts = state.charts.filter(c => {
    if (c && c.canvas && c.canvas.id === 'usd-gauge') {
      c.destroy();
      return false;
    }
    return true;
  });
  const avgScore = usd.average_score || usdScore.average_score || 5.0;
  const gaugeChart = createGaugeChart('usd-gauge', avgScore);
  if (gaugeChart) state.charts.push(gaugeChart);
}

function renderScoreBreakdown(scores) {
  const items = [
    { label: 'Macro Score (GDP/UE)', key: 'macro_score', value: scores.macro_score },
    { label: 'Event Surprise Score', key: 'event_surprise_score', value: scores.event_surprise_score },
    { label: 'Yield Momentum Score', key: 'yield_momentum_score', value: scores.yield_momentum_score },
    { label: 'CFTC Sentiment Score', key: 'cftc_sentiment_score', value: scores.cftc_sentiment_score },
  ];

  return items.map(item => {
    const val = item.value != null ? item.value : 5.0;
    const pct = (val / 10) * 100;
    let color;
    if (val >= 7) color = '#198754';
    else if (val >= 5) color = '#0d6efd';
    else if (val >= 3) color = '#ffc107';
    else color = '#dc3545';

    return `
      <div class="mb-3">
        <div class="d-flex justify-content-between mb-1">
          <span style="font-size: 0.85rem;">${item.label}</span>
          <span class="score-label" style="color: ${color};">${val.toFixed(1)}</span>
        </div>
        <div class="score-gauge">
          <div class="score-gauge-fill" style="width: ${pct}%; background-color: ${color};"></div>
        </div>
      </div>
    `;
  }).join('');
}

function pairsDataUpdated() {
  if (state.pairsData?.last_updated) return state.pairsData.last_updated;
  return null;
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 2: BIAS Grid ──────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderBiasTab() {
  const container = document.getElementById('tab-bias');
  if (!container) return;

  const pairs = state.pairsData?.pairs || [];
  const byClass = groupBy(pairs, 'asset_class');
  const classOrder = ['FX', 'METAL', 'ENERGY', 'INDEX'];

  let html = `
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="section-title mb-0">Asset Bias Overview (${pairs.length} pairs)</h5>
      <input type="text" class="filter-input" id="bias-filter" 
             placeholder="Filter by asset name..." oninput="filterBiasTable()">
    </div>
  `;

  classOrder.forEach(cls => {
    const items = byClass[cls] || [];
    if (items.length === 0) return;

    html += `
      <h6 class="mt-3 mb-2 text-uppercase" style="color: var(--text-muted); font-size: 0.75rem; letter-spacing: 1px;">
        ${cls === 'FX' ? 'Currency Pairs' : cls === 'METAL' ? 'Precious Metals' : cls === 'ENERGY' ? 'Energy' : 'Equity Indices'}
        <span class="ms-2 badge bg-secondary">${items.length}</span>
      </h6>
      <div class="table-responsive">
        <table class="table table-striped table-hover table-clickable bias-table" data-class="${cls}">
          <thead>
            <tr>
              <th>Name</th>
              <th class="text-center">Base Score</th>
              <th class="text-center">Quote Score</th>
              <th class="text-center">Combined Bias</th>
              <th class="text-center">Direction</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${items.map(p => renderBiasRow(p)).join('')}
          </tbody>
        </table>
      </div>
    `;
  });

  if (pairs.length === 0) {
    html += '<div class="text-center py-5 text-muted">No pair data available. Run the data pipeline first.</div>';
  }

  container.innerHTML = html;
  
  // Re-apply filter if one was active
  if (state.currentFilter) {
    const filterInput = document.getElementById('bias-filter');
    if (filterInput) {
      filterInput.value = state.currentFilter;
      filterBiasTable();
    }
  }
}

function renderBiasRow(pair) {
  const isExpanded = state.expandedRows.has(pair.name);
  const directionClass = pair.direction.includes('Bullish') ? 'text-bullish' 
    : pair.direction.includes('Bearish') ? 'text-bearish' : 'text-neutral';

  return `
    <tr class="bias-row" data-name="${pair.name}">
      <td><strong>${pair.name}</strong></td>
      <td class="text-center">${pair.base_score.toFixed(1)}</td>
      <td class="text-center">${pair.quote_score.toFixed(1)}</td>
      <td class="text-center fw-700 ${directionClass}">${pair.combined_bias.toFixed(1)}</td>
      <td class="text-center">
        <span class="badge ${pair.direction === 'Strongly Bullish' || pair.direction === 'Bullish' ? 'badge-bullish' : pair.direction === 'Strongly Bearish' || pair.direction === 'Bearish' ? 'badge-bearish' : 'badge-neutral'}">${pair.direction}</span>
      </td>
      <td class="text-center">
        <button class="btn btn-sm btn-outline-secondary" onclick="togglePairDetail('${pair.name}', this)">
          ${isExpanded ? '−' : '+'}
        </button>
      </td>
    </tr>
    <tr class="bias-detail-row ${isExpanded ? '' : 'd-none'}" data-detail="${pair.name}">
      <td colspan="6" class="p-0">
        <div class="p-3" style="background-color: var(--bg-secondary);">
          <div class="row g-2 mb-2">
            <div class="col-3 col-md-2 text-center">
              <div style="font-size: 0.7rem; color: var(--text-muted);">Base Score</div>
              <div class="fw-700">${pair.base_score.toFixed(1)}</div>
            </div>
            <div class="col-3 col-md-2 text-center">
              <div style="font-size: 0.7rem; color: var(--text-muted);">Quote Score</div>
              <div class="fw-700">${pair.quote_score.toFixed(1)}</div>
            </div>
            <div class="col-3 col-md-2 text-center">
              <div style="font-size: 0.7rem; color: var(--text-muted);">Combined Bias</div>
              <div class="fw-700">${pair.combined_bias.toFixed(1)}</div>
            </div>
            <div class="col-3 col-md-2 text-center">
              <div style="font-size: 0.7rem; color: var(--text-muted);">Direction</div>
              <div class="fw-700">${pair.direction}</div>
            </div>
          </div>
          <p class="mb-0" style="font-size: 0.8rem;">${pair.conclusion}</p>
        </div>
      </td>
    </tr>
  `;
}

window.togglePairDetail = function(name, btn) {
  const isExpanded = state.expandedRows.has(name);
  if (isExpanded) {
    state.expandedRows.delete(name);
  } else {
    state.expandedRows.add(name);
  }
  
  // Re-render the bias tab preserving filter state
  renderBiasTab();
};

window.filterBiasTable = function() {
  const input = document.getElementById('bias-filter');
  if (!input) return;
  state.currentFilter = input.value.toLowerCase();

  document.querySelectorAll('.bias-table tbody tr.bias-row').forEach(row => {
    const name = row.dataset.name?.toLowerCase() || '';
    const match = name.includes(state.currentFilter);
    row.style.display = match ? '' : 'none';
    
    // Also hide detail row
    const detail = document.querySelector(`tr.bias-detail-row[data-detail="${CSS.escape(row.dataset.name)}"]`);
    if (detail) {
      detail.style.display = match && !detail.classList.contains('d-none') ? '' : 'none';
    }
  });
};

function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key] || 'OTHER';
    if (!acc[k]) acc[k] = [];
    acc[k].push(item);
    return acc;
  }, {});
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 3: Federal Reserve (FRED) ─────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderFredTab() {
  const container = document.getElementById('tab-fred');
  if (!container) return;

  const fred = state.fredData;
  
  container.innerHTML = `
    <h5 class="section-title">Federal Reserve Economic Data (FRED)</h5>
    <p class="gov-subheader mb-3">Historical macro-economic series fetched directly from the Federal Reserve Bank of St. Louis.</p>
    
    <div class="row g-3">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">Real GDP (GDPC1)</div>
          <div class="card-body p-2">
            <canvas id="fred-gdpc1" height="220"></canvas>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">Core CPI (CPILFESL)</div>
          <div class="card-body p-2">
            <canvas id="fred-cpilfesl" height="220"></canvas>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">Core PCE (PCEPILFE)</div>
          <div class="card-body p-2">
            <canvas id="fred-pcepilfe" height="220"></canvas>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header">Unemployment Rate (UNRATE)</div>
          <div class="card-body p-2">
            <canvas id="fred-unrate" height="220"></canvas>
          </div>
        </div>
      </div>
      <div class="col-12">
        <div class="card">
          <div class="card-header">Federal Funds Effective Rate (FEDFUNDS)</div>
          <div class="card-body p-2">
            <canvas id="fedfunds-chart" height="220"></canvas>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderFredCharts() {
  const fred = state.fredData;
  if (!fred || !fred.series) return;

  // Destroy existing FRED charts first
  const fredCanvasIds = ['fred-gdpc1', 'fred-cpilfesl', 'fred-pcepilfe', 'fred-unrate', 'fedfunds-chart'];
  state.charts = state.charts.filter(c => {
    if (c && c.canvas && fredCanvasIds.includes(c.canvas.id)) {
      c.destroy();
      return false;
    }
    return true;
  });

  const charts = [
    createFredChart('fred-gdpc1', 'GDPC1', fred, 'Real GDP (Billions $)'),
    createFredChart('fred-cpilfesl', 'CPILFESL', fred, 'Core CPI (Index)'),
    createFredChart('fred-pcepilfe', 'PCEPILFE', fred, 'Core PCE (Index)'),
    createFredChart('fred-unrate', 'UNRATE', fred, 'Unemployment Rate (%)'),
    createFredChart('fedfunds-chart', 'FEDFUNDS', fred, 'Fed Funds Rate (%)'),
  ];
  
  charts.forEach(c => {
    if (c) state.charts.push(c);
  });
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 4: CFTC CoT ──────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderCftcTab() {
  const container = document.getElementById('tab-cftc');
  if (!container) return;

  const cftc = state.cftcData;
  const positions = cftc?.positions || [];

  container.innerHTML = `
    <h5 class="section-title">CFTC Commitments of Traders (CoT)</h5>
    <p class="gov-subheader mb-3">Weekly speculative positioning data with 52-week percentile ranks.</p>

    <div class="card mb-3">
      <div class="card-header">Speculative Net Positions & Percentile Ranks</div>
      <div class="card-body p-2">
        <canvas id="cftc-chart" height="300"></canvas>
      </div>
    </div>

    <div class="table-responsive">
      <table class="table table-striped table-hover">
        <thead>
          <tr>
            <th>Market</th>
            <th class="text-end">Report Date</th>
            <th class="text-end">Non-Commercial Long</th>
            <th class="text-end">Non-Commercial Short</th>
            <th class="text-end">Net Speculative</th>
            <th class="text-end">Weekly Change</th>
            <th class="text-end">52W Percentile</th>
            <th class="text-center">Signal</th>
          </tr>
        </thead>
        <tbody>
          ${positions.length === 0 
            ? '<tr><td colspan="8" class="text-center text-muted">No CFTC data available.</td></tr>'
            : positions.map(p => {
                const signal = p.percentile_52w >= 75 ? 'Bullish' 
                  : p.percentile_52w <= 25 ? 'Bearish' : 'Neutral';
                const signalClass = signal === 'Bullish' ? 'text-bullish' 
                  : signal === 'Bearish' ? 'text-bearish' : 'text-neutral';
                return `
                  <tr>
                    <td><strong>${p.market}</strong></td>
                    <td class="text-end">${p.report_date}</td>
                    <td class="text-end">${p.noncomm_long.toLocaleString()}</td>
                    <td class="text-end">${p.noncomm_short.toLocaleString()}</td>
                    <td class="text-end fw-700 ${p.net_speculative >= 0 ? 'text-bullish' : 'text-bearish'}">${p.net_speculative.toLocaleString()}</td>
                    <td class="text-end ${p.weekly_change >= 0 ? 'text-bullish' : 'text-bearish'}">${p.weekly_change.toLocaleString()}</td>
                    <td class="text-end fw-700">${p.percentile_52w.toFixed(1)}%</td>
                    <td class="text-center ${signalClass} fw-700">${signal}</td>
                  </tr>
                `;
              }).join('')
          }
        </tbody>
      </table>
    </div>
  `;
}

function renderCftcCharts() {
  const cftc = state.cftcData;
  if (!cftc?.positions?.length) return;

  // Destroy existing CFTC chart
  state.charts = state.charts.filter(c => {
    if (c && c.canvas && c.canvas.id === 'cftc-chart') {
      c.destroy();
      return false;
    }
    return true;
  });

  const chart = createCftcChart('cftc-chart', cftc);
  if (chart) state.charts.push(chart);
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 5: Bond Yields ──────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderYieldsTab() {
  const container = document.getElementById('tab-yields');
  if (!container) return;

  const yieldData = state.yieldData;
  const entries = yieldData?.entries || [];

  let html = `
    <h5 class="section-title">Global Bond Yields & 50-Day Moving Averages</h5>
    <p class="gov-subheader mb-3">Government bond yields from major economies with trend analysis.</p>
  `;

  if (entries.length === 0) {
    html += '<div class="text-center py-5 text-muted">No yield data available. Run the data pipeline to fetch bond yields.</div>';
  } else {
    html += `
      <div class="card mb-3">
        <div class="card-header">Yield Comparison</div>
        <div class="card-body p-2">
          <canvas id="yield-chart" height="300"></canvas>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table table-striped table-hover">
          <thead>
            <tr>
              <th>Instrument</th>
              <th class="text-end">Date</th>
              <th class="text-end">Current Yield</th>
              <th class="text-end">50-Day MA</th>
              <th class="text-center">Trend</th>
            </tr>
          </thead>
          <tbody>
            ${entries.map(e => {
              const trend = e.yield_ma50 != null && e.yield_value > e.yield_ma50 ? 'Rising ↑' 
                : e.yield_ma50 != null && e.yield_value < e.yield_ma50 ? 'Falling ↓' : 'Flat →';
              const trendClass = trend.includes('Rising') ? 'text-bullish' 
                : trend.includes('Falling') ? 'text-bearish' : 'text-neutral';
              return `
                <tr>
                  <td><strong>${e.instrument}</strong></td>
                  <td class="text-end">${e.date}</td>
                  <td class="text-end fw-700">${e.yield_value.toFixed(2)}%</td>
                  <td class="text-end">${e.yield_ma50 != null ? e.yield_ma50.toFixed(2) + '%' : '—'}</td>
                  <td class="text-center ${trendClass} fw-700">${trend}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  container.innerHTML = html;

  // Draw yield chart
  if (entries.length > 0) {
    // Destroy existing yield chart
    state.charts = state.charts.filter(c => {
      if (c && c.canvas && c.canvas.id === 'yield-chart') {
        c.destroy();
        return false;
      }
      return true;
    });
    const chart = createYieldChart('yield-chart', yieldData);
    if (chart) state.charts.push(chart);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 6: Trade Setups ──────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderSetupsTab() {
  const container = document.getElementById('tab-setups');
  if (!container) return;

  const setups = state.setupsData?.setups || [];

  let html = `
    <h5 class="section-title">High-Probability Trade Setups</h5>
    <p class="gov-subheader mb-3">Assets with extreme fundamental bias scores. Combined bias ≥ 8.0 (Strongly Bullish) or ≤ 2.0 (Strongly Bearish).</p>
  `;

  if (setups.length === 0) {
    html += '<div class="text-center py-5 text-muted">No extreme setups currently. Run the data pipeline to generate fresh scores.</div>';
  } else {
    html += `
      <div class="table-responsive">
        <table class="table table-hover">
          <thead>
            <tr>
              <th>Asset</th>
              <th class="text-center">Direction</th>
              <th class="text-center">Combined Bias</th>
              <th>Fundamental Consensus</th>
            </tr>
          </thead>
          <tbody>
            ${setups.map(s => {
              const isLong = s.direction === 'LONG';
              return `
                <tr>
                  <td><strong>${s.asset_name}</strong></td>
                  <td class="text-center">
                    <span class="badge ${isLong ? 'badge-bullish' : 'badge-bearish'}" style="${isLong ? 'color: #000;' : 'color: #fff;'}">
                      ${isLong ? '▲ LONG' : '▼ SHORT'}
                    </span>
                  </td>
                  <td class="text-center fw-700 ${isLong ? 'text-bullish' : 'text-bearish'}">
                    ${s.combined_bias.toFixed(1)}
                  </td>
                  <td style="font-size: 0.85rem;">${s.fundamental_consensus}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>
    `;
  }

  container.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 6: News Feed ─────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderNewsTab() {
  const container = document.getElementById('tab-news');
  if (!container) return;

  const articles = state.newsData?.articles || [];

  let html = `
    <h5 class="section-title">Global Financial Markets News Feed</h5>
    <p class="gov-subheader mb-3">Latest headlines from financial markets worldwide.</p>
  `;

  if (articles.length === 0) {
    html += '<div class="text-center py-5 text-muted">No news articles available. Run the data pipeline to fetch the latest headlines.</div>';
  } else {
    html += `<div class="list-group">`;
    articles.forEach(a => {
      const pubDate = a.published_at 
        ? new Date(a.published_at).toLocaleString('en-US', { 
            year: 'numeric', month: 'short', day: 'numeric',
            hour: '2-digit', minute: '2-digit' 
          })
        : '';
      html += `
        <div class="news-item">
          <div class="news-title">
            <a href="${a.link}" target="_blank" rel="noopener" 
               style="color: var(--accent-blue); text-decoration: none;">
              ${a.title}
            </a>
          </div>
          <div class="d-flex justify-content-between">
            <span class="news-source">${a.source}</span>
            <span class="news-date">${pubDate}</span>
          </div>
          ${a.description ? `<div class="mt-1" style="font-size: 0.8rem; color: var(--text-secondary);">${a.description}</div>` : ''}
        </div>
      `;
    });
    html += `</div>`;
  }

  container.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
// ── TAB 7: AI Analysis ───────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

function renderAITab() {
  const container = document.getElementById('tab-ai');
  if (!container) return;

  const scores = state.scoresData || {};
  const pairs = state.pairsData?.pairs || [];
  const cftc = state.cftcData?.positions || [];
  const usd = state.usdBiasData || {};

  // Build macro synthesis
  const usdScore = scores['USD'] || {};
  const usdAvg = usd.average_score || usdScore.average_score || 5.0;
  
  // Count bullish vs bearish pairs
  let bullishCount = 0, bearishCount = 0, neutralCount = 0;
  pairs.forEach(p => {
    if (p.combined_bias >= 6) bullishCount++;
    else if (p.combined_bias <= 4) bearishCount++;
    else neutralCount++;
  });

  // CFTC sentiment overview
  let cftcBullish = 0, cftcBearish = 0, cftcNeutral = 0;
  cftc.forEach(p => {
    if (p.percentile_52w >= 60) cftcBullish++;
    else if (p.percentile_52w <= 40) cftcBearish++;
    else cftcNeutral++;
  });

  // Generate synthesis text
  const usdBiasText = usdAvg >= 7 ? 'Bullish' : usdAvg >= 5 ? 'Slightly Bullish' : usdAvg >= 3 ? 'Slightly Bearish' : 'Bearish';
  const marketBiasText = bullishCount > bearishCount + neutralCount ? 'broadly bullish' : bearishCount > bullishCount + neutralCount ? 'broadly bearish' : 'mixed/neutral';
  const cftcText = cftcBullish > cftcBearish ? 'speculators are net long overall' : cftcBearish > cftcBullish ? 'speculators are net short overall' : 'speculative positioning is mixed';

  // Generate directional calls
  const topLongs = pairs.filter(p => p.combined_bias >= 7.5).slice(0, 5);
  const topShorts = pairs.filter(p => p.combined_bias <= 2.5).slice(0, 5);

  let html = `
    <h5 class="section-title">AI Macro Synthesis</h5>
    <p class="gov-subheader mb-3">Compiled fundamental analysis of the current macroeconomic environment.</p>

    <!-- Status Card -->
    <div class="card mb-4">
      <div class="card-header">Market Overview</div>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-md-3 col-6">
            <div class="stat-card card">
              <div class="stat-value">${pairs.length}</div>
              <div class="stat-label">Total Assets Tracked</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="stat-card card">
              <div class="stat-value text-bullish">${bullishCount}</div>
              <div class="stat-label">Bullish Signals</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="stat-card card">
              <div class="stat-value text-bearish">${bearishCount}</div>
              <div class="stat-label">Bearish Signals</div>
            </div>
          </div>
          <div class="col-md-3 col-6">
            <div class="stat-card card">
              <div class="stat-value">${Math.round(usdAvg * 10) / 10}</div>
              <div class="stat-label">USD Score</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Synthesis -->
    <div class="card mb-4">
      <div class="card-header">Fundamental Synthesis</div>
      <div class="card-body">
        <p style="font-size: 0.9rem; line-height: 1.7;">
          The US Dollar is currently <strong>${usdBiasText}</strong> with a composite fundamental score of 
          <strong>${usdAvg.toFixed(1)}/10</strong>. The broader market is <strong>${marketBiasText}</strong>, 
          with ${bullishCount} bullish signals vs ${bearishCount} bearish signals across ${pairs.length} tracked assets.
        </p>
        <p style="font-size: 0.9rem; line-height: 1.7;">
          CFTC Commitment of Traders data shows ${cftcText}. 
          ${cftcBullish >= 4 ? 'Strong speculative long positioning suggests crowded trades in several markets.' : ''}
          ${cftcBearish >= 4 ? 'Elevated short positioning indicates potential contrarian reversal risks.' : ''}
        </p>
        ${usdAvg >= 7 ? '<p style="font-size: 0.9rem; line-height: 1.7;">A strong USD score suggests favoring short EUR/USD, GBP/USD and long USD/JPY setups in alignment with dollar strength.</p>' : ''}
        ${usdAvg <= 4 ? '<p style="font-size: 0.9rem; line-height: 1.7;">A weak USD score suggests favoring long EUR/USD, GBP/USD and short USD/JPY setups in alignment with dollar weakness.</p>' : ''}
      </div>
    </div>

    <!-- Top Directional Calls -->
    <div class="row g-3">
      ${topLongs.length > 0 ? `
      <div class="col-md-6">
        <div class="card">
          <div class="card-header text-bullish">▲ Top Long Setups</div>
          <div class="card-body p-2">
            <table class="table table-sm">
              <thead>
                <tr><th>Asset</th><th class="text-end">Score</th></tr>
              </thead>
              <tbody>
                ${topLongs.map(p => `<tr><td>${p.name}</td><td class="text-end fw-700 text-bullish">${p.combined_bias.toFixed(1)}</td></tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>` : ''}
      ${topShorts.length > 0 ? `
      <div class="col-md-6">
        <div class="card">
          <div class="card-header text-bearish">▼ Top Short Setups</div>
          <div class="card-body p-2">
            <table class="table table-sm">
              <thead>
                <tr><th>Asset</th><th class="text-end">Score</th></tr>
              </thead>
              <tbody>
                ${topShorts.map(p => `<tr><td>${p.name}</td><td class="text-end fw-700 text-bearish">${p.combined_bias.toFixed(1)}</td></tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>` : ''}
    </div>
  `;

  container.innerHTML = html;
}

// ═══════════════════════════════════════════════════════════════════════════
// ── Initialization ─────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', function() {
  // Initialize theme
  initTheme();

  // Open first tab by default
  openTab('home');

  // Load all data
  loadAllData();
});