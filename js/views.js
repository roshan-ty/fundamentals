/* Bulls & Bears Fundamentals — tab views.
 * Each view(root) renders its tab content into the #view element.
 * Reads only from data/ JSON (no external calls).
 */
"use strict";
(function () {
  const B = window.BBF;
  const { loadJSON, el, fmt, esc, parseNum, scoreBadge, bandName, mkChart, lineOption, gaugeOption } = B;

  /* ── HOME ─────────────────────────────────────────────── */
  async function viewHome(root) {
    const currencies = await loadJSON("bias/currencies.json", {});
    const instruments = await loadJSON("bias/instruments.json", {});
    const meta = await loadJSON("meta/last_update.json", {});
    const news = await loadJSON("news/feed.json", []);
    const quotes = await loadJSON("quotes/latest.json", {});

    const cur = currencies.currencies || {};
    const inst = instruments.instruments || {};

    const order = ["USD", "EUR", "GBP", "AUD", "NZD", "CAD", "JPY", "CHF", "CNY",
                   "XAUUSD", "XAGUSD", "OIL", "BRENT", "COPPER"];
    const cards = [];
    for (const code of order) {
      if (cur[code]) {
        const c = cur[code];
        cards.push({ code, name: code, score: c.score, band: c.band, type: "currency",
                     drivers: (c.top_drivers || []).slice(0, 3) });
      } else if (inst[code]) {
        const c = inst[code];
        cards.push({ code, name: c.name || code, score: c.score, band: c.band, type: c.biasType,
                     drivers: [] });
      }
    }

    const grid = el("div", "grid cards");
    for (const c of cards) {
      const card = el("div", "card");
      const tone = c.score >= 6 ? "pos" : (c.score <= 4 ? "neg" : "");
      card.innerHTML = `
        <div class="lbl">${esc(c.name)} · ${esc(c.type)}</div>
        <div class="big ${tone}">${fmt(c.score, 1)}<span class="dim">/10</span></div>
        <div>${scoreBadge(c.score, c.band)}</div>
        <div class="dim" style="font-size:11px">${c.drivers.slice(0, 2).map((d) => esc(d.event)).join(" · ") || "—"}</div>`;
      card.onclick = () => B.switchTab("data");
      grid.appendChild(card);
    }
    root.appendChild(el("h2", "panel-title", "Headline Bias"));
    root.appendChild(grid);

    const qKeys = Object.keys(quotes || {}).filter((k) => quotes[k] && quotes[k].price).slice(0, 14);
    const qPanel = el("div", "panel");
    qPanel.innerHTML = `<h3>Markets</h3><table class="data"><thead><tr><th>Instrument</th><th class="num">Last</th><th class="num">Updated (UTC)</th></tr></thead><tbody>` +
      qKeys.map((k) => `<tr><td>${esc(k)}</td><td class="num">${fmt(quotes[k].price, 4)}</td><td class="num dim">${esc((quotes[k].ts || "").slice(11, 19))}</td></tr>`).join("") +
      `</tbody></table>`;
    root.appendChild(qPanel);

    const nPanel = el("div", "panel");
    nPanel.innerHTML = `<h3>Markets &amp; World</h3>` + (Array.isArray(news) ? news.slice(0, 6).map((n) =>
      `<div class="news-item"><span class="hl">${esc(n.headline)}</span><div class="sn dim">${esc((n.snippet || "").slice(0, 140))}</div></div>`).join("") : `<div class="dim">No data.</div>`);
    root.appendChild(nPanel);

    let lastTxt = "";
    try { lastTxt = (meta.daily && meta.daily.updated) || (meta.scoring && meta.scoring.updated) || ""; } catch (e) {}
    document.getElementById("updatedLine").textContent = lastTxt ? "Updated " + lastTxt.replace("T", " ") + " UTC" : "";
  }
/* ── DATA (instruments deep dive) ─────────────────────── */
  let dataInstrument = "XAUUSD";
  async function viewData(root) {
    const currencies = await loadJSON("bias/currencies.json", {});
    const instruments = await loadJSON("bias/instruments.json", {});
    const cftc = await loadJSON("cftc/cot_legacy.json", {});
    const events = await loadJSON("calendar/events_current.json", []);
    const news = await loadJSON("news/feed.json", []);
    const yields = await loadJSON("macro/fred.json", {});

    const cur = currencies.currencies || {};
    const inst = instruments.instruments || {};
    const opts = Object.keys(cur);
    for (const k of Object.keys(inst)) opts.push(k);

    const selRow = el("div", "", `<label>Instrument</label> <select class="instr" id="dataSel">` +
      opts.map((o) => `<option value="${esc(o)}" ${o === dataInstrument ? "selected" : ""}>${o}</option>`).join("") +
      `</select>`);
    root.appendChild(selRow);
    document.getElementById("dataSel").onchange = function () {
      dataInstrument = this.value;
      B.dispatch("data");
    };

    const sym = dataInstrument;
    let score = null, band = "No Score", biasType = "direct";
    if (cur[sym]) {
      score = cur[sym].score; band = cur[sym].band; biasType = "currency";
    } else if (inst[sym]) {
      score = inst[sym].score; band = inst[sym].band; biasType = inst[sym].biasType || "direct";
    }

    const head = el("div", "grid cards");
    const c1 = el("div", "card");
    const tone = score >= 6 ? "pos" : (score <= 4 ? "neg" : "");
    c1.innerHTML = `<div class="lbl">${esc(sym)} · ${esc(biasType)}</div><div class="big ${tone}">${fmt(score, 1)}<span class="dim">/10</span></div><div>${scoreBadge(score, band)}</div>`;
    head.appendChild(c1);
    root.appendChild(head);

    // Calendar events affecting this instrument
    const evPanel = el("div", "panel");
    const relevant = (Array.isArray(events) ? events : []).filter((e) => e.country === sym || sym.startsWith(e.country));
    evPanel.innerHTML = `<h3>Economic Calendar — ${esc(sym)}</h3><table class="data"><thead><tr><th>Time (UTC)</th><th>Event</th><th>Impact</th><th class="num">Previous</th><th class="num">Forecast</th><th class="num">Actual</th></tr></thead><tbody>` +
      relevant.slice(0, 40).map((e) => `<tr><td class="num">${esc((e.date_utc || "").slice(5, 16))}</td>
        <td>${esc(e.title)}</td><td>${esc(e.impact || "")}</td>
        <td class="num">${esc(e.previous || "—")}</td><td class="num">${esc(e.forecast || "—")}</td>
        <td class="num ${e.actual ? "pos" : "dim"}">${esc(e.actual || "Pending")}</td></tr>`).join("") +
      `</tbody></table>`;
    root.appendChild(evPanel);

    // Scored drivers detail
    const curDetail = (currencies.detail || {})[sym] || [];
    if (curDetail.length) {
      const dp = el("div", "panel");
      dp.innerHTML = `<h3>Bias Scoring — ${esc(sym)}</h3><table class="data"><thead><tr><th>Data Point</th><th>Actual</th><th>Previous</th><th>Verdict</th><th class="num">Weight</th></tr></thead><tbody>` +
        curDetail.map((d) => `<tr><td>${esc(d.event)}</td><td class="num">${esc(d.actual)}</td><td class="num">${esc(d.previous)}</td>
          <td><span class="${d.verdict === "bullish" ? "pos" : (d.verdict === "bearish" ? "neg" : "dim")}">${esc(d.verdict)}</span></td>
          <td class="num">${d.weight}</td></tr>`).join("") + `</tbody></table>`;
      root.appendChild(dp);
    }

    // COT positioning for this instrument
    const cotMarkets = cftc.markets || {};
    if (cotMarkets[sym]) {
      const m = cotMarkets[sym];
      const latest = m.history[m.latest] || {};
      const cp = el("div", "panel");
      const net = parseNum(latest.noncomm_long) - parseNum(latest.noncomm_short);
      cp.innerHTML = `<h3>Positioning — ${esc(sym)} (report ${esc(m.latest || "")})</h3>
        <table class="data"><thead><tr><th class="num">Non-Comm Long</th><th class="num">Non-Comm Short</th><th class="num">Net</th><th class="num">Open Interest</th></tr></thead><tbody>
        <tr><td class="num">${fmt(latest.noncomm_long, 0)}</td><td class="num">${fmt(latest.noncomm_short, 0)}</td>
        <td class="num ${net >= 0 ? "pos" : "neg"}">${fmt(net, 0)}</td><td class="num">${fmt(latest.open_interest, 0)}</td></tr>
        </tbody></table>`;
      root.appendChild(cp);
    }

    // Yield context (confirmation, separate)
    const ySeries = ["DGS10", "DGS2", "DFII10", "DGS30"];
    const pts = ySeries.map((s) => ({ s, pts: (yields[s] || {}).points || [] }));
    if (pts.some((p) => p.pts.length)) {
      const src = pts.find((p) => p.pts.length).pts;
      const cats = src.map((p) => p.date).slice(-180);
      const series = pts.filter((p) => p.pts.length).map((p) => ({
        name: (yields[p.s] || {}).meta?.name || p.s,
        type: "line", showSymbol: false, data: p.pts.slice(-180).map((q) => q.value),
      }));
      const chartEl = el("div", "chart", `<div id="yieldChart" style="height:320px"></div>`);
      root.appendChild(chartEl);
      setTimeout(() => { try { mkChart("yieldChart", lineOption("Yields (confirmation only)", cats, series)); } catch (e) {} }, 60);
    }

    // News filtered to this instrument
    const newsPanel = el("div", "panel");
    const tagged = (Array.isArray(news) ? news : []).filter((n) => (n.tags || []).includes(sym));
    newsPanel.innerHTML = `<h3>News — ${esc(sym)}</h3>` +
      (tagged.slice(0, 8).map((n) => `<div class="news-item"><div class="hl">${esc(n.headline)}</div>
        <div class="sn dim">${esc((n.snippet || "").slice(0, 220))}</div>
        <div class="meta">${esc((n.published || "").slice(0, 16))}</div></div>`).join("") ||
       `<div class="dim">No headline currently tagged to this instrument.</div>`);
    root.appendChild(newsPanel);
  }
/* ── BIAS (pairs table) ───────────────────────────────── */
  async function viewBias(root) {
    const pairs = await loadJSON("bias/pairs.json", {});
    const list = pairs.pairs || [];
    const panel = el("div", "panel");
    const scored = list.filter((p) => p.score !== null).length;
    panel.innerHTML = `<h3>Pair Bias — ${esc(list.length)} instruments · ${scored} scored</h3>
      <input class="search" id="biasSearch" placeholder="Search pair…">
      <table class="data"><thead><tr><th>Symbol</th><th>Name</th><th class="num">Score</th><th>Band</th><th>Type</th><th>Read</th></tr></thead>
      <tbody id="biasBody"></tbody></table>`;
    root.appendChild(panel);
    const body = document.getElementById("biasBody");
    function render(filter) {
      const f = (filter || "").toLowerCase();
      const rows = list.filter((p) => !f || p.symbol.toLowerCase().includes(f) || (p.name || "").toLowerCase().includes(f));
      body.innerHTML = rows.map((p) => `<tr>
        <td><strong>${esc(p.symbol)}</strong></td><td>${esc(p.name || "")}</td>
        <td class="num ${p.score && p.score >= 6 ? "pos" : (p.score && p.score <= 4 ? "neg" : "")}">${fmt(p.score, 2)}</td>
        <td>${scoreBadge(p.score, p.band)}</td>
        <td class="dim">${esc(p.biasType || "")}</td>
        <td class="dim">${esc(p.direction || "")}${p.score === null ? " (data pending)" : ""}</td></tr>`).join("") || `<tr><td colspan="6" class="dim">No pairs.</td></tr>`;
    }
    render("");
    document.getElementById("biasSearch").oninput = function () { render(this.value); };
  }

  /* ── CFTC ─────────────────────────────────────────────── */
  async function viewCFTC(root) {
    const cot = await loadJSON("cftc/cot_legacy.json", {});
    const cotBias = await loadJSON("cftc/cot_bias.json", {});
    const markets = cot.markets || {};
    const instruments = cotBias.instruments || {};

    const panel = el("div", "panel");
    panel.innerHTML = `<h3>Commitments of Traders — Positioning</h3>
      <table class="data"><thead><tr><th>Instrument</th><th>Report Date</th><th class="num">Non-Comm Long</th><th class="num">Non-Comm Short</th><th class="num">Net</th><th class="num">Δ Net</th><th>Tilt</th></tr></thead><tbody>` +
      Object.keys(markets).map((k) => {
        const m = markets[k];
        const ins = instruments[k] || {};
        const t = ins.tilt || {};
        const latest = m.history[m.latest] || {};
        const net = (t.net !== null && t.net !== undefined) ? t.net : (parseNum(latest.noncomm_long) - parseNum(latest.noncomm_short));
        const delta = t.delta;
        return `<tr><td><strong>${esc(k)}</strong></td><td class="num">${esc(m.latest || "")}</td>
          <td class="num">${fmt(latest.noncomm_long, 0)}</td><td class="num">${fmt(latest.noncomm_short, 0)}</td>
          <td class="num ${net >= 0 ? "pos" : "neg"}">${fmt(net, 0)}</td>
          <td class="num ${(delta || 0) >= 0 ? "pos" : "neg"}">${fmt(delta, 0)}</td>
          <td>${(t.tilt || 0) > 0 ? '<span class="pos">Long expansion</span>' : ((t.tilt || 0) < 0 ? '<span class="neg">Long reduction</span>' : '<span class="dim">Flat</span>')}</td></tr>`;
      }).join("") + `</tbody></table>`;
    if (!Object.keys(markets).length) {
      panel.innerHTML += `<div class="dim">No COT data available.</div>`;
    }
    root.appendChild(panel);

    // Net positioning chart
    const chartKeys = Object.keys(markets).filter((k) => ["EUR", "GBP", "JPY", "XAUUSD", "XAGUSD", "OIL"].includes(k));
    if (chartKeys.length) {
      const uniq = [...new Set(chartKeys.flatMap((k) => Object.keys(markets[k].history)))].sort();
      const series = chartKeys.map((k) => {
        const h = markets[k].history;
        const vals = uniq.map((d) => (h[d] ? parseNum(h[d].noncomm_long) - parseNum(h[d].noncomm_short) : null));
        return { name: k, type: "line", showSymbol: false, connectNull: true, data: vals, smooth: true };
      });
      const el2 = document.createElement("div");
      el2.className = "chart";
      el2.innerHTML = `<div id="cotChart" style="height:420px"></div>`;
      root.appendChild(el2);
      setTimeout(() => { try { mkChart("cotChart", lineOption("Non-Commercial Net Positioning (contracts)", uniq, series)); } catch (e) {} }, 60);
    }
  }
/* ── HISTORICAL ───────────────────────────────────────── */
  let histSeries = "DGS10";
  async function viewHistorical(root) {
    const yields = await loadJSON("macro/fred.json", {});
    const selectable = Object.keys(yields || {}).filter((k) => (yields[k].points || []).length > 30);

    const row = el("div", "", `<label>Series</label> <select class="instr" id="histSel">` +
      selectable.map((s) => `<option value="${esc(s)}" ${s === histSeries ? "selected" : ""}>${esc(yields[s].meta?.name || s)}</option>`).join("") + `</select>`);
    root.appendChild(row);
    document.getElementById("histSel").onchange = function () { histSeries = this.value; B.dispatch("historical"); };

    const data = (yields[histSeries] || {});
    const pts = data.points || [];
    const cats = pts.map((p) => p.date);
    const vals = pts.map((p) => (p.value === null || p.value === undefined) ? null : parseNum(p.value));
    const panel = el("div", "panel");
    panel.innerHTML = `<h3>${esc(data.meta?.name || histSeries)} — ${esc(cats[0] || "—")} to ${esc(cats[cats.length - 1] || "—")}</h3>`;
    root.appendChild(panel);
    if (vals.length) {
      const chartEl = el("div", "chart tall", `<div id="histChart" style="height:440px"></div>`);
      root.appendChild(chartEl);
      setTimeout(() => {
        try {
          mkChart("histChart", lineOption(data.meta?.name || histSeries, cats, [{
            name: data.meta?.name || histSeries, type: "line", showSymbol: false, smooth: true,
            data: vals, lineStyle: { width: 1.4 },
          }]));
        } catch (e) {}
      }, 60);
    }
  }

  /* ── ANALYSIS ─────────────────────────────────────────── */
  let analysisSym = "EURUSD";
  async function viewAnalysis(root) {
    const analyses = await loadJSON("analysis/pairs.json", {});
    const pairs = analyses.analyses || {};
    const keys = Object.keys(pairs);
    const selRow = el("div", "", `<label>Pair</label> <select class="instr" id="analysisSel">` +
      keys.map((k) => `<option value="${esc(k)}" ${k === analysisSym ? "selected" : ""}>${esc(k)}</option>`).join("") + `</select>`);
    root.appendChild(selRow);
    document.getElementById("analysisSel").onchange = function () { analysisSym = this.value; B.dispatch("analysis"); };

    const a = pairs[analysisSym] || { summary: "No analysis available yet for this instrument." };
    const panel = el("div", "panel narrative");
    panel.innerHTML = `<h3>${esc(analysisSym)}</h3><div>${a.narrative_html || esc(a.summary)}</div>
      <div class="meta-line">${esc(a.updated || "")}</div>`;
    root.appendChild(panel);
  }

  /* ── TOP SETUPS ───────────────────────────────────────── */
  async function viewSetups(root) {
    const data = await loadJSON("setups/top.json", {});
    const list = data.setups || [];
    const panel = el("div", "panel");
    panel.innerHTML = `<h3>Top Setups</h3>
      <table class="data"><thead><tr><th>Rank</th><th>Symbol</th><th class="num">Score</th><th>Direction</th><th>Band</th><th class="num">Confidence</th><th>Type</th><th>Rationale</th></tr></thead><tbody>` +
      list.map((s, i) => `<tr><td class="num">${i + 1}</td><td><strong>${esc(s.symbol)}</strong></td>
        <td class="num ${s.score >= 6 ? "pos" : (s.score <= 4 ? "neg" : "")}">${fmt(s.score, 2)}</td>
        <td><span class="${s.direction === "Buy" ? "pos" : (s.direction === "Sell" ? "neg" : "dim")}">${esc(s.direction)}</span></td>
        <td>${scoreBadge(s.score, s.band)}</td>
        <td class="num">${fmt(s.confidence, 2)}</td>
        <td class="dim">${esc(s.biasType || "")}</td>
        <td class="dim">${esc((s.rationale || "").slice(0, 100))}</td></tr>`).join("") + `</tbody></table>`;
    if (!list.length) panel.innerHTML = `<h3>Top Setups</h3><div class="dim">No setups ranked yet.</div>`;
    root.appendChild(panel);
  }

  B.TABS_VIEWS["home"] = viewHome;
  B.TABS_VIEWS["data"] = viewData;
  B.TABS_VIEWS["bias"] = viewBias;
  B.TABS_VIEWS["cftc"] = viewCFTC;
  B.TABS_VIEWS["historical"] = viewHistorical;
  B.TABS_VIEWS["analysis"] = viewAnalysis;
  B.TABS_VIEWS["setups"] = viewSetups;
})();