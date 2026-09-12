# Verdict engine v3 — replaces numeric 0-10 scoring with one-of-five verdicts.
#   Every data point is judged forecast-first (beats forecast -> bullish, misses
#   forecast -> bearish, matches -> neutral; fallback actual-vs-previous when no
#   forecast exists). Only RELEASED data shapes verdicts; for a pending data
#   point the most recent released reading is used (config/verdict_rules.json).
# Outputs: data/bias/currencies.json, data/bias/instruments.json,
#          data/bias/pairs.json, data/setups/top.json, data/analysis/pairs.json
import os
import sys
import json
import re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_scorecard, load_config, log, DATA_DIR, now_iso  # noqa: E402
from scoring.score import norm_num, decide, match_data_point, _weeks_old, _decay  # noqa: E402

VERDICTS = ["Very Bearish", "Bearish", "Neutral", "Bullish", "Very Bullish"]


def _verdict_band(bshare, bshare_signed):
    """Map (bullish share, net share) to one of five verdicts.
    bshare: bullish weight share of released total. net = (bull-bear)/total."""
    if bshare_signed >= 0.55:
        return "Very Bullish"
    if 0.20 <= bshare_signed < 0.55:
        return "Bullish"
    if -0.20 < bshare_signed < 0.20:
        return "Neutral"
    if -0.55 < bshare_signed <= -0.20:
        return "Bearish"
    return "Very Bearish"


def data_point_verdict(rec):
    """Forecast-first verdict for one released reading.
    rec: {actual, previous, forecast, direction}.
    Forecast present: beats forecast = bullish, misses = bearish, matches = neutral
    (respecting the data point's directional semantics, e.g. unemployment).
    No forecast: falls back to actual-vs-previous (unchanged = neutral)."""
    direction = rec.get("direction", "higher_is_bullish")
    actual = norm_num(rec.get("actual"))
    if actual is None:
        return "neutral"
    forecast = norm_num(rec.get("forecast"))
    if forecast is not None:
        if direction == "lower_is_bullish":
            return "bullish" if actual < forecast else ("bearish" if actual > forecast else "neutral")
        return "bullish" if actual > forecast else ("bearish" if actual < forecast else "neutral")
    previous = norm_num(rec.get("previous"))
    if previous is None:
        return "neutral"
    sign = decide(rec.get("actual"), rec.get("previous"), direction)  # already direction-aware
    return "bullish" if sign > 0 else ("bearish" if sign < 0 else "neutral")


def _all_events():
    out = load_json(os.path.join(DATA_DIR, "calendar", "events_current.json"), default=[])
    out += load_json(os.path.join(DATA_DIR, "calendar", "year_events.json"), default=[])
    out += load_json(os.path.join(DATA_DIR, "calendar", "fred_events.json"), default=[])
    return out


def build_releases():
    """Latest RELEASED reading per (currency, scorecard dataPoint).
    Pending data points simply don't appear; their prior release is retained."""
    sc = load_scorecard()
    releases = {}
    for ev in _all_events():
        country = ev.get("country")
        actual = ev.get("actual")
        if country not in sc["currencies"] or not actual:
            continue
        dp = match_data_point(sc, country, ev.get("title"))
        if not dp:
            continue
        dkey = f"{country}|{dp['id']}"
        date_cur = ev.get("date_utc") or ev.get("period", "")
        prev = releases.get(dkey)
        if prev is None or (prev.get("period") or "") < date_cur:
            releases[dkey] = {
                "country": country,
                "dataPointId": dp["id"],
                "dataPoint": dp["name"],
                "weight": dp["weight"],
                "direction": dp["direction"],
                "period": date_cur,
                "title": ev.get("title", ""),
                "actual": str(actual),
                "previous": str(ev.get("previous") or ""),
                "forecast": str(ev.get("forecast") or ""),
            }
    return releases
def _tally_for_currency(currency, releases, rules):
    cfg = rules.get("currencies", {}).get(currency, {})
    tiers = cfg.get("dataPoints", {})
    weights = rules.get("weights", {})
    bull = bear = neut = 0.0
    drivers = []
    recs = []
    for key, rec in releases.items():
        if rec["country"] != currency:
            continue
        tier = tiers.get(rec["dataPointId"], "Medium")
        w = weights.get(tier, 1.0)
        verdict = data_point_verdict(rec)
        if verdict == "bullish":
            bull += w
        elif verdict == "bearish":
            bear += w
        else:
            neut += w
        drivers.append({
            "dataPoint": rec["dataPoint"],
            "title": rec.get("title", ""),
            "period": rec.get("period", ""),
            "actual": rec["actual"],
            "previous": rec.get("previous", ""),
            "forecast": rec.get("forecast", ""),
            "direction": rec.get("direction", ""),
            "verdict": verdict,
            "weight": w,
        })
        recs.append(rec)
    drivers.sort(key=lambda x: x.get("period") or "", reverse=True)
    return bull, bear, neut, drivers, recs


def _apply_specials(currency, base_band, bull, bear, releases, rules, context):
    """Adjust verdict band by special composites; returns (band, notes)."""
    notes = []
    band_idx = VERDICTS.index(base_band)
    cfg = rules.get("currencies", {}).get(currency, {})
    specials = cfg.get("specials", [])
    release_records = list(releases.values())
    for name in specials:
        spec = rules.get("specials", {}).get(name)
        if not spec:
            continue
        if name == "stagflation":
            inf = [k for k in release_records if k["dataPointId"] in spec.get("inflation", [])]
            growth = [k for k in release_records if k["dataPointId"] in spec.get("growth", [])]
            inf_bull = sum(1 for k in inf if data_point_verdict(k) == "bullish")
            growth_bear = sum(1 for k in growth if data_point_verdict(k) == "bearish")
            if inf_bull > 0 and growth_bear > 0:
                band_idx += -1  # stagflation risk pulls verdict down one step
                notes.append("stagflation risk: inflation beats while growth misses")
        elif name == "usd_3of4":
            pts = [k for k in release_records if k["dataPointId"] in spec.get("points", [])]
            beats = sum(1 for k in pts if data_point_verdict(k) == "bullish")
            misses = sum(1 for k in pts if data_point_verdict(k) == "bearish")
            if beats >= spec.get("min", 3) and band_idx < 3:
                band_idx += 1
                notes.append(f"{beats} of the high-impact monthly releases beat forecast (3-of-4 rule)")
            elif misses >= spec.get("min", 3) and band_idx > 1:
                band_idx -= 1
                notes.append(f"{misses} of the high-impact monthly releases missed forecast")
        elif name == "jpy_core_above2":
            for k in release_records:
                if k["dataPointId"] in spec.get("points", []):
                    val = norm_num(k.get("actual"))
                    if val is not None and val > spec.get("threshold", 2.0) and band_idx < 3:
                        band_idx += 1
                        notes.append("core CPI above 2% raises BoJ normalization odds")
        elif name == "china_demand":
            pts = [k for k in release_records if k["dataPointId"] in spec.get("points", [])]
            bull_cn = sum(1 for k in pts if data_point_verdict(k) == "bullish")
            bear_cn = sum(1 for k in pts if data_point_verdict(k) == "bearish")
            if bull_cn and not bear_cn and band_idx < 3:
                band_idx += 1
                notes.append("Chinese demand signals expansion (China-linked currencies)")
            elif bear_cn and not bull_cn and band_idx > 1:
                band_idx -= 1
                notes.append("Chinese demand signals slowdown")
        elif name == "oil_link":
            oil = context.get("oil_direction", "flat")
            if oil == "up" and band_idx < 3:
                band_idx += 1
                notes.append("crude oil trending up (commodity exporter)")
            elif oil == "down" and band_idx > 1:
                band_idx -= 1
                notes.append("crude oil trending down (commodity exporter)")
        elif name == "safe_haven":
            risk = context.get("risk_mode", "flat")
            if risk in ("risk_off", "high") and band_idx < 3:
                band_idx += 1
                notes.append("global risk-off supports safe-haven demand")
    band_idx = max(0, min(4, band_idx))
    return VERDICTS[band_idx], notes


def currency_verdict(currency, releases, rules, context):
    bull, bear, neut, drivers, recs = _tally_for_currency(currency, releases, rules)
    total = bull + bear + neut
    if total <= 0:
        return {
            "verdict": "Neutral",
            "tally": {"bullish": 0, "bearish": 0, "neutral": 0},
            "released_points": len(recs), "drivers": drivers, "notes": ["no released data yet"],
        }
    bull_share = bull / total
    net_share = (bull - bear) / total
    band = _verdict_band(bull_share, net_share)
    band, notes = _apply_specials(currency, band, bull, bear, releases, rules, context)
    # Single-point guard: a lone release cannot reach "Very".
    if len(recs) < rules.get("bands", {}).get("min_released_for_strong", 3):
        if band in ("Very Bullish", "Very Bearish"):
            band = "Bullish" if band == "Very Bullish" else "Bearish"
            notes.append("limited release evidence; cap at single-step verdict")
    return {
        "verdict": band,
        "tally": {"bullish": round(bull, 1), "bearish": round(bear, 1), "neutral": round(neut, 1)},
        "released_points": len(recs),
        "drivers": drivers,
        "notes": notes,
    }
# ── market context (real yields, DXY level, quotes, M2, COT) ───────────────
def build_context(releases):
    ctx = {"real_yield_sig": 0, "dxy_sig": 0, "m2_sig": 0, "china_pmi_sig": 0,
           "oil_direction": "flat", "risk_mode": "flat", "cot": {}}
    fred = load_json(os.path.join(DATA_DIR, "macro", "fred.json"), default={})

    def latest(series):
        pts = fred.get(series, {}).get("points", [])
        return pts[-1]["value"] if pts else None

    def year_ago(series, months=12):
        pts = fred.get(series, {}).get("points", [])
        if not pts:
            return None
        target = None
        for p in reversed(pts):
            try:
                y, m = int(p["date"][:4]), int(p["date"][5:7])
            except Exception:
                continue
            now_y, now_m = int(pts[-1]["date"][:4]), int(pts[-1]["date"][5:7])
            diff = (now_y - y) * 12 + (now_m - m)
            if diff >= months:
                target = p["value"]
                break
        return target if target is not None else pts[0]["value"]

    ry = latest("DFII10")
    ry_old = year_ago("DFII10", 6)
    if ry is not None and ry_old is not None:
        ctx["real_yield_sig"] = -1 if ry < ry_old - 0.15 else (1 if ry > ry_old + 0.15 else 0)

    m2 = latest("M2SL")
    m2_old = year_ago("M2SL", 12)
    if m2 is not None and m2_old is not None:
        ctx["m2_sig"] = 1 if m2 > m2_old else (-1 if m2 < m2_old else 0)

    # Approximate DXY level from live FX quotes (real ICE-style weights)
    q = load_json(os.path.join(DATA_DIR, "quotes", "latest.json"), default={})

    def price(sym):
        entry = q.get(sym)
        return entry.get("price") if entry and entry.get("price") else None

    eur = price("EURUSD"); jpy = price("USDJPY"); gbp = price("GBPUSD")
    cad = price("USDCAD"); sek = price("USDSEK"); chf = price("USDCHF")
    if eur:
        dxy = 50.14348112 * (1.0 / eur) ** 1.0  # level proxy when others missing
        if jpy and gbp and cad and sek and chf:
            try:
                dxy = 50.14348112 * (eur ** -0.576) * (jpy ** 0.136) * (gbp ** -0.119) * (cad ** 0.091) * (sek ** 0.042) * (chf ** 0.036)
            except Exception:
                pass
        ctx["dxy_sig"] = -1 if dxy <= 100 else (1 if dxy >= 106 else 0)
        ctx["dxy_level"] = round(dxy, 2)

    # China manufacturing PMI (latest released reading)
    for key, rec in releases.items():
        if rec["country"] == "CNY" and rec.get("dataPointId") == "cn_pmi":
            v = data_point_verdict(rec)
            ctx["china_pmi_sig"] = 1 if v == "bullish" else (-1 if v == "bearish" else 0)
            break

    # Risk mode from real yields + DXY (confirmation-style context for safe-haven)
    if ctx.get("dxy_sig") == 1 and ctx["real_yield_sig"] == 1:
        ctx["risk_mode"] = "high"
    elif ctx.get("dxy_sig") == -1 and ctx["real_yield_sig"] == -1:
        ctx["risk_mode"] = "low"

    xau = price("XAUUSD")
    ctx["gold_level"] = xau
    cot = load_json(os.path.join(DATA_DIR, "cftc", "cot_bias.json"), default={}).get("instruments", {})
    for sym, ins in cot.items():
        tilt = (ins.get("tilt") or {}).get("tilt", 0)
        ctx["cot"][sym] = float(tilt or 0)
    return ctx
# ── instrument verdicts (metals / energy / equity indices / crypto) ─────────
def _band_from_signal(net):
    if net >= 2:
        return "Very Bullish"
    if net >= 1:
        return "Bullish"
    if net <= -2:
        return "Very Bearish"
    if net <= -1:
        return "Bearish"
    return "Neutral"


def instrument_verdict(sym, cfg, releases, context):
    kind = cfg.get("kind", "metal")
    sig = 0
    notes = []
    cot = context.get("cot", {}).get(sym, 0)
    usd_anchor = context.get("usd_anchor", 0)  # -2..2 from USD currency verdict

    if kind in ("metal", "industrial"):
        sig -= context["real_yield_sig"]      # RISING real yields bearish metal
        sig += -1 * context.get("dxy_sig", 0)  # strong USD -> bearish metal
        sig += -usd_anchor                     # inverse-USD rule
        if kind == "industrial":
            sig += context["china_pmi_sig"]    # Chinese industry drives copper/pt/pd
            notes.append("industrial metal: China PMI contributes")
        if cot:
            sig += 1 if cot > 0 else (-1 if cot < 0 else 0)
            notes.append("positioning tilt contributes")
        if context["real_yield_sig"] != 0:
            notes.append("real-yield " + ("falling (supportive)" if context["real_yield_sig"] < 0 else "rising (headwind)"))
        if context.get("dxy_sig") != 0:
            notes.append("USD index " + ("weak (supportive)" if context["dxy_sig"] < 0 else "strong (headwind)"))
    elif kind == "energy":
        sig += context["china_pmi_sig"]
        sig += -usd_anchor
        if context["china_pmi_sig"] != 0:
            notes.append("industrial demand PMI " + ("expanding" if context["china_pmi_sig"] > 0 else "contracting"))
        if cot:
            sig += 1 if cot > 0 else (-1 if cot < 0 else 0)
            notes.append("positioning tilt contributes")
    elif kind == "index":
        sig -= context["real_yield_sig"]
        sig += -1 * context.get("dxy_sig", 0)
        sig += int(-0.5 * usd_anchor)
        if context["real_yield_sig"] != 0:
            notes.append("real-yield " + ("easing (risk-on)" if context["real_yield_sig"] < 0 else "rising (headwind)"))
    elif kind == "crypto":
        sig += context["m2_sig"]
        sig += -1 * context.get("dxy_sig", 0)
        sig += -usd_anchor
        if context["m2_sig"] != 0:
            notes.append("liquidity " + ("expanding" if context["m2_sig"] > 0 else "contracting"))
        if context.get("dxy_sig") != 0:
            notes.append("USD index " + ("weak (supportive)" if context["dxy_sig"] < 0 else "strong (headwind)"))
    if usd_anchor and kind in ("metal", "industrial", "energy", "crypto"):
        notes.append("USD " + ("strong — inverse headwind" if usd_anchor > 0 else "weak — inverse supportive"))
    band = _band_from_signal(sig)
    if kind in ("index", "crypto"):
        # proxy-derived instruments stay within single-step verdicts
        if band in ("Very Bullish", "Very Bearish"):
            band = "Bullish" if band == "Very Bullish" else "Bearish"
            notes.append("proxy-derived signal capped at single step")
    return {
        "verdict": band,
        "halo": f"signal {sig:+d}",
        "notes": notes,
        "cot_tilt": cot,
    }


# ── pairs: differential matrix + instrument-as-pair rows ───────────────────
_ANCHOR = {"Very Bearish": -2, "Bearish": -1, "Neutral": 0, "Bullish": 1, "Very Bullish": 2}


def pair_from_matrix(base_v, quote_v):
    diff = _ANCHOR.get(base_v, 0) - _ANCHOR.get(quote_v, 0)
    if diff >= 2:
        return "Very Bullish"
    if diff == 1:
        return "Bullish"
    if diff == 0:
        return "Neutral"
    if diff == -1:
        return "Bearish"
    return "Very Bearish"


def build_pairs(currencies, instruments, symbols, context):
    rows = []
    for cls in ("fx", "crypto", "metals", "energy", "indices"):
        for sym, meta in symbols.get(cls, {}).items():
            if cls == "fx":
                base, quote = meta["base"], meta["quote"]
                bv = currencies.get(base, {}).get("verdict")
                qv = currencies.get(quote, {}).get("verdict")
                if bv is None or qv is None:
                    verdict, drivers = "No Score", []
                else:
                    verdict = pair_from_matrix(bv, qv)
                    drivers = [f"{base}: {currencies[base]['verdict']}", f"{quote}: {currencies[quote]['verdict']}"]
                rows.append({"symbol": sym, "class": "fx", "verdict": verdict,
                             "base": base, "quote": quote, "base_verdict": bv, "quote_verdict": qv,
                             "drivers": drivers})
            else:
                iv = instruments.get(sym, {}).get("verdict") if sym in instruments else None
                rows.append({"symbol": sym, "class": cls, "verdict": iv or "No Score",
                             "base_verdict": iv, "quote_verdict": None, "drivers": []})
    return rows
# ── narratives ───────────────────────────────────────────────────────────────
def _driver_text(driver):
    line = f"{driver['dataPoint']}: actual {driver['actual']}"
    if driver.get("forecast"):
        line += f" vs forecast {driver['forecast']}"
    if driver.get("previous"):
        line += f" (previous {driver['previous']})"
    line += f" — {driver['verdict']}"
    return f"- {line}"


def build_narratives(currencies, instruments, pairs):
    narratives = {}
    for row in pairs:
        sym = row["symbol"]
        if row["class"] == "fx":
            b = row.get("base_verdict") or "Neutral"
            q = row.get("quote_verdict") or "Neutral"
            text = [f"The {row['base']} reads {b}, while the {row['quote']} reads {q}.",
                    f"Differentiating base-minus-quote yields a {row['verdict']} verdict for {sym}."]
            bd = currencies.get(row["base"], {}).get("drivers", [])[:2]
            for d in bd:
                text.append(_driver_text(d))
            narratives[sym] = {
                "symbol": sym, "verdict": row["verdict"], "summary": f"{sym}: {row['verdict']}",
                "narrative_html": "<h3>" + sym + "</h3><p>" + "</p><p>".join(text) + "</p>",
                "updated": now_iso(),
            }
        else:
            iv = instruments.get(sym, {})
            notes = " ".join(iv.get("notes", [])) or "market-context signals"
            narratives[sym] = {
                "symbol": sym, "verdict": iv.get("verdict", "Neutral"),
                "summary": f"{sym}: {iv.get('verdict')}",
                "narrative_html": f"<h3>{sym}</h3><p>{iv.get('verdict')} — {notes}</p>",
                "updated": now_iso(),
            }
    return narratives


# ── setups ranking (verdict strength x evidence + recency) ─────────────────
def build_setups(pairs, currencies, top_n=12):
    ranked = []
    for row in pairs:
        if row["verdict"] == "No Score":
            continue
        importance = abs(_ANCHOR.get(row["verdict"], 0))
        if importance == 0:
            continue
        conf = 0.4
        if row["class"] == "fx":
            conf += 0.1 * min(6, currencies.get(row["base"], {}).get("released_points", 0))
            conf += 0.1 * min(6, currencies.get(row["quote"], {}).get("released_points", 0))
        conf = min(conf, 1.0)
        ranked.append({
            "symbol": row["symbol"],
            "name": row["symbol"],
            "verdict": row["verdict"],
            "direction": "Buy" if _ANCHOR.get(row["verdict"], 0) > 0 else ("Sell" if _ANCHOR.get(row["verdict"], 0) < 0 else "Hold"),
            "confidence": round(conf, 2),
            "importance": importance,
            "rationale": f"{row['verdict']}" + (f" — {' · '.join(row['drivers'])}" if row.get("drivers") else ""),
        })
    ranked.sort(key=lambda x: (x["importance"], x["confidence"]), reverse=True)
    return ranked[:top_n]


def collect():
    rules = load_config("verdict_rules.json")
    symbols = load_config("symbols.json")
    releases = build_releases()
    release_list = list(releases.values())
    save_json(os.path.join(DATA_DIR, "calendar", "releases.json"),
              {"updated": now_iso(), "releases": release_list})

    context = build_context(releases)
    # currency verdicts
    currency_out = {}
    for cur in rules.get("currencies", {}):
        currency_out[cur] = currency_verdict(cur, releases, rules, context)
    save_json(os.path.join(DATA_DIR, "bias", "currencies.json"), {
        "meta": {"updated": now_iso(), "method": "verdict v3 (forecast-first, released-only)"},
        "currencies": currency_out,
        "context": {k: v for k, v in context.items() if k != "cot"},
    })

    # instrument verdicts (inverse-USD rule driven by the USD currency verdict)
    usd_v = currency_out.get("USD", {}).get("verdict", "Neutral")
    context["usd_anchor"] = _ANCHOR.get(usd_v, 0)
    instrument_out = {}
    for sym, cfg in rules_targets(symbols).items():
        instrument_out[sym] = instrument_verdict(sym, cfg, releases, context)
    save_json(os.path.join(DATA_DIR, "bias", "instruments.json"), {
        "meta": {"updated": now_iso(), "method": "verdict v3"},
        "instruments": instrument_out,
    })

    pairs = build_pairs(currency_out, instrument_out, symbols, context)
    save_json(os.path.join(DATA_DIR, "bias", "pairs.json"), {
        "meta": {"updated": now_iso(), "total": len(pairs),
                 "scored": sum(1 for p in pairs if p["verdict"] != "No Score")},
        "pairs": pairs,
    })

    save_json(os.path.join(DATA_DIR, "setups", "top.json"), {
        "meta": {"updated": now_iso()},
        "setups": build_setups(pairs, currency_out, top_n=12),
    })

    narratives = build_narratives(currency_out, instrument_out, pairs)
    save_json(os.path.join(DATA_DIR, "analysis", "pairs.json"), {
        "meta": {"updated": now_iso(), "note": "Verdict-based narratives"},
        "analyses": narratives,
    })

    log("Verdicts: " + ", ".join(f"{c}={v['verdict']}" for c, v in currency_out.items()))
    log(f"Pairs: {len(pairs)} ({sum(1 for p in pairs if p['verdict'] != 'No Score')} scored)")
    return {"currencies": currency_out, "instruments": instrument_out}


def rules_targets(symbols):
    """Merge instrument targets (metals/energy + derived crypto/indices)."""
    out = {}
    for sym in symbols.get("metals", {}):
        out[sym] = {"kind": "metal"}
    for sym in symbols.get("energy", {}):
        out[sym] = {"kind": "energy"}
    for sym in symbols.get("indices", {}):
        out[sym] = {"kind": "index"}
    for sym in symbols.get("crypto", {}):
        out[sym] = {"kind": "crypto"}
    return out


if __name__ == "__main__":
    print(json.dumps(collect(), indent=1)[:2000])