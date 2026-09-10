# Narrative engine — turns the real data behind each pair into a readable,
# fully data-driven fundamental analysis. Every statement is generated from
# collected actuals, forecast/previous, COT positioning and yields.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.utils import load_json, save_json, load_symbols, load_scorecard, log, DATA_DIR, now_iso

NAME = {
    "USD": "U.S. Dollar", "EUR": "Euro", "GBP": "British Pound", "JPY": "Japanese Yen",
    "CHF": "Swiss Franc", "CAD": "Canadian Dollar", "AUD": "Australian Dollar",
    "NZD": "New Zealand Dollar", "CNY": "Chinese Yuan", "MXN": "Mexican Peso", "BRL": "Brazilian Real",
}


def _describe(score):
    if score is None:
        return "No Score", "insufficient data to score"
    if score <= 2:
        return "Very Bearish", "extremely negative data flow"
    if score <= 4:
        return "Bearish", "consistently negative data flow"
    if score < 6:
        return "Neutral", "balanced or unchanged data flow"
    if score <= 7:
        return "Bullish", "consistently positive data flow"
    return "Very Bullish", "extremely positive data flow"


def _driver_lines(detail, cur):
    lines = []
    for d in detail:
        if not d.get("sign"):
            continue
        direction_word = "strengthens" if d["sign"] > 0 else "weakens"
        lines.append(
            f"- {d['event']}: actual {d['actual']} vs previous {d['previous']} "
            f"({d['verdict']}, weight {d['weight']:+}) — {direction_word} {cur}."
        )
    return lines
def analyze_pair(symbol, pair, currencies, instruments, cot, sc):
    cls = pair.get("class")
    score = pair.get("score")
    bias_type = pair.get("biasType", "direct")
    parts = []
    if cls == "fx":
        base, quote = pair.get("base_score"), pair.get("quote_score")
        bc = pair.get("symbol")[:3]
        qc = pair.get("symbol")[3:]
        parts.append(f"<h3>{pair['symbol']} — {NAME.get(bc, bc)} vs {NAME.get(qc, qc)}</h3>")
        b_desc = _describe(base)[1]
        q_desc = _describe(quote)[1]
        parts.append(f"The {NAME.get(bc, bc)} (base) carries a bias of {base} / 10 ({b_desc}); "
                     f"the {NAME.get(qc, qc)} (quote) carries {quote} / 10 ({q_desc}).")
        if base is not None and quote is not None:
            delta = round((base or 5) - (quote or 5), 2)
            if delta > 0.6:
                parts.append(f"A positive base-minus-quote spread (+{delta}) tilts the pair bullish: base strength outweighs quote strength.")
            elif delta < -0.6:
                parts.append(f"A negative base-minus-quote spread ({delta}) tilts the pair bearish: quote strength outweighs base strength.")
            else:
                parts.append("A narrow base-minus-quote spread leaves the pair roughly neutral.")
        for code in (bc, qc):
            c = cot.get(code)
            if c:
                t = c.get("tilt", {}).get("tilt", 0)
                w = c.get("latest_week")
                parts.append(f"COT positioning ({w}): non-commercial net exposure for {code} "
                             f"{'expanded — consistent with ' + ('strength' if t > 0 else 'weakness') if t else 'flat.'}")
    elif cls in ("metals", "energy"):
        parts.append(f"<h3>{pair.get('name')} ({pair['symbol']})</h3>")
        parts.append(f"Bias {score} / 10 ({_describe(score)[0]}). Metals and energy score inversely to the U.S. Dollar "
                     f"with a COT positioning component: USD bias {pair.get('base_score')} / 10.")
        c = cot.get(pair["symbol"])
        if c:
            t = c.get("tilt", {}).get("tilt", 0)
            parts.append(f"COT ({c.get('latest_week')}): non-commercial net tilt {'long' if t > 0 else ('short' if t < 0 else 'flat')} — "
                         f"{'supporting' if (t > 0) == (score and score > 5) else 'counter'} the current price bias.")
    else:
        parts.append(f"<h3>{pair.get('name')} ({pair['symbol']})</h3>")
        parts.append(f"This instrument has no economic calendar or COT basis; its bias is a derived sentiment proxy at "
                     f"{score} / 10 ({_describe(score)[0]}), driven by U.S. dollar pressure and real-yield conditions.")

    ys = load_json(os.path.join(DATA_DIR, "macro", "fred.json"), default={})
    d10 = ys.get("DGS10", {}).get("points")
    d2 = ys.get("DGS2", {}).get("points")
    rr = ys.get("DFII10", {}).get("points")
    if d10 and d2:
        y10, y2 = d10[-1]["value"], d2[-1]["value"]
        parts.append(f"Yield context (confirmation only): 10Y {y10}%, 2Y {y2}%, curve {'steep' if y10 - y2 > 0.5 else 'flat'}.")
        if rr:
            parts.append(f"Real 10Y yield {rr[-1]['value']}% — " +
                         ("supportive of risk assets if pressured" if rr[-1]['value'] < 2 else "an ongoing headwind for risk assets."))

    detail = currencies.get("detail", {})
    if cls == "fx" and pair.get("base_score") is not None:
        base_code = pair["symbol"][:3]
        dlines = _driver_lines(detail.get(base_code, []), base_code)
        if dlines:
            parts.append(f"<h4>Drivers — {NAME.get(base_code, base_code)}</h4>" + "\n".join(dlines))

    narrative = "\n".join(parts)
    return {
        "symbol": pair["symbol"],
        "score": score,
        "band": pair.get("band"),
        "biasType": bias_type,
        "summary": f"{pair['symbol']} is {pair.get('direction', 'No Score').lower()} with a bias of {score}/10.",
        "narrative_html": narrative,
        "updated": now_iso(),
    }


def collect():
    currencies = load_json(os.path.join(DATA_DIR, "bias", "currencies.json"), default={})
    pairs = load_json(os.path.join(DATA_DIR, "bias", "pairs.json"), default={}).get("pairs", [])
    cot = load_json(os.path.join(DATA_DIR, "cftc", "cot_bias.json"), default={}).get("instruments", {})
    sc = load_scorecard()
    analyses = {}
    for pair in pairs:
        if pair.get("score") is None:
            continue
        analyses[pair["symbol"]] = analyze_pair(pair["symbol"], pair, currencies, {}, cot, sc)
    save_json(os.path.join(DATA_DIR, "analysis", "pairs.json"), {
        "meta": {"updated": now_iso(), "note": "Data-driven narratives"},
        "analyses": analyses,
    })
    log(f"Narratives: {len(analyses)} pairs")
    return analyses


if __name__ == "__main__":
    import json
    print(json.dumps(collect(), indent=1)[:2500])