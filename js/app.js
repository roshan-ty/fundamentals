/* Bulls & Bears Fundamentals — application
 * Static front-end over the data/ JSON database produced by the pipelines.
 * Renders: Home, Data, Bias, CFTC, Historical, Analysis, Top Setups.
 */
"use strict";

const DATA_BASE = "data/";
let CACHE = {};

async function loadJSON(path, fallback) {
  if (CACHE[path]) return CACHE[path];
  try {
    const r = await fetch(DATA_BASE + path, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    CACHE[path] = await r.json();
  } catch (e) {
    CACHE[path] = fallback || {};
  }
  return CACHE[path];
}

/* ── helpers ─────────────────────────────────────────────── */
function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}
function fmt(x, d) {
  if (x === null || x === undefined || x === "") return "—";
  const n = typeof x === "string" ? parseFloat(x) : x;
  if (Number.isNaN(n)) return x;
  return n.toLocaleString("en-US", { maximumFractionDigits: d || 2 });
}
function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
function parseNum(x) {
  if (x === null || x === undefined) return 0;
  const n = parseFloat(String(x).replace(/,/g, ""));
  return Number.isNaN(n) ? 0 : n;
}
function bandClass(band) {
  const b = String(band || "").toLowerCase();
  if (b.includes("bull")) return "pos";
  if (b.includes("bear")) return "neg";
  return "dim";
}
function scoreBadge(score, band) {
  if (score === null || score === undefined || score === "") {
    return `<span class="badge dim">No Score</span>`;
  }
  const cls = bandClass(band);
  const txt = fmt(score) + "/10 · " + (band || "No Score");
  return `<span class="badge ${cls}">${esc(txt)}</span>`;
}

/* ── clock / theme ───────────────────────────────────────── */
function tickClock() {
  const d = new Date();
  document.getElementById("clock").textContent = d.toUTCString().slice(17, 25) + " UTC";
}
function setupThemeToggle() {
  const b = document.getElementById("themeToggle");
  const root = document.documentElement;
  b.addEventListener("click", () => {
    const t = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", t);
    try { localStorage.setItem("bbf-theme", t); } catch (e) {}
    setTimeout(() => { redrawCharts(); }, 80);
  });
  try {
    const t = localStorage.getItem("bbf-theme");
    if (t) root.setAttribute("data-theme", t);
  } catch (e) {}
}
/* ── tab system ──────────────────────────────────────────── */
const TABS = [
  { id: "home", label: "Home" },
  { id: "data", label: "Data" },
  { id: "calendar", label: "Calendar" },
  { id: "bias", label: "Bias" },
  { id: "cftc", label: "CFTC" },
  { id: "historical", label: "Historical Data" },
  { id: "analysis", label: "Analysis" },
  { id: "setups", label: "Top Setups" },
];
let ACTIVE = "home";
let CHARTS = [];

function renderTabs() {
  const nav = document.getElementById("tabs");
  nav.innerHTML = "";
  TABS.forEach((t) => {
    const b = el("button", t.id === ACTIVE ? "active" : "", t.label);
    b.onclick = () => switchTab(t.id);
    nav.appendChild(b);
  });
}
async function switchTab(id) {
  ACTIVE = id;
  renderTabs();
  window.history.replaceState(null, "", "#" + id);
  await dispatch(id);
}
async function dispatch(id) {
  const view = document.getElementById("view");
  view.innerHTML = "";
  view.appendChild(el("div", "dim", "Loading…"));
  try {
    await TABS_VIEWS[id](view);
  } catch (e) {
    view.innerHTML = `<div class="panel"><h3>Error</h3><div>${esc(e.message)}</div></div>`;
  }
  const l = view.querySelector(".dim:first-child");
  if (l && l.textContent === "Loading…") l.remove();
}

/* ── charts ──────────────────────────────────────────────── */
function redrawCharts() {
  CHARTS.forEach((c) => c.refresh && c.refresh());
}
function palette() {
  const dark = document.documentElement.getAttribute("data-theme") !== "light";
  return {
    bg: dark ? "#0a0a0c" : "#ffffff",
    grid: dark ? "#1e2026" : "#d8dadd",
    text: dark ? "#9aa0a8" : "#464a52",
    up: dark ? "#26a063" : "#1e7f3f",
    down: dark ? "#e04f4f" : "#b3261e",
    gold: dark ? "#d4af37" : "#b8860b",
  };
}
function mkChart(elId, option) {
  const chart = echarts.init(document.getElementById(elId), null, { renderer: "svg" });
  chart.setOption(option);
  CHARTS.push(chart);
  return chart;
}
function lineOption(title, cats, series) {
  const p = palette();
  return {
    backgroundColor: "transparent",
    title: { text: title, left: "left", textStyle: { color: p.text, fontSize: 12 } },
    tooltip: { trigger: "axis" },
    legend: { top: 24, textStyle: { color: p.text } },
    grid: { left: 52, right: 18, top: 48, bottom: 28 },
    xAxis: { type: "category", data: cats, axisLabel: { color: p.text, hideOverlap: true } },
    yAxis: { type: "value", axisLabel: { color: p.text, formatter: (v) => fmt(v, 2) }, splitLine: { lineStyle: { color: p.grid } } },
    series,
  };
}
function gaugeOption(value) {
  const p = palette();
  const color = value >= 6 ? p.up : (value <= 4 ? p.down : p.gold);
  return {
    backgroundColor: "transparent",
    series: [{
      type: "gauge",
      radius: "88%",
      startAngle: 210, endAngle: -30,
      min: 0, max: 10,
      progress: { show: true, width: 12, itemStyle: { color } },
      axisLine: { lineStyle: { width: 12, color: [[1, p.grid]] } },
      axisLabel: { show: false },
      pointer: { show: false },
      title: { offsetCenter: [0, "80%"], color: p.text, fontSize: 11 },
      detail: { valueAnimation: true, offsetCenter: [0, "48%"], formatter: "{value}", color, fontSize: 26, fontWeight: 700 },
      data: [{ value: Math.round(value * 100) / 100, name: bandName(value) }],
    }],
  };
}
function bandName(score) {
  if (score === null || score === undefined) return "No Score";
  if (score <= 2) return "Very Bearish";
  if (score <= 4) return "Bearish";
  if (score < 6) return "Neutral";
  if (score <= 7) return "Bullish";
  return "Very Bullish";
}

/* ── views registry (defined in views.js) ───────────────── */
const TABS_VIEWS = {};

window.BBF = { switchTab, dispatch, TABS_VIEWS, loadJSON, el, fmt, esc, parseNum, scoreBadge, bandName, mkChart, lineOption, gaugeOption, palette, bandClass, setupThemeToggle, tickClock };