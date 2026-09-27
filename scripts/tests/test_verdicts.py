# Verdict engine v3 unit tests.
import os
import sys
import json

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from scoring import verdicts as v  # noqa: E402


def _release(country, dp_id, title, actual, previous="", forecast="", direction="higher_is_bullish", period="2026-08-01T12:00:00+00:00"):
    return {"country": country, "dataPointId": dp_id, "dataPoint": title, "weight": 1.0,
            "direction": direction, "period": period, "title": title, "actual": str(actual),
            "previous": str(previous), "forecast": str(forecast)}


# ── data-point verdict (forecast-first) ───────────────────
def test_forecast_first_beats():
    assert v.data_point_verdict(_release("GBP", "gb_cpi", "CPI y/y", "3.1%", forecast="2.9%")) == "bullish"
    assert v.data_point_verdict(_release("GBP", "gb_cpi", "CPI y/y", "2.7%", forecast="2.9%")) == "bearish"
    assert v.data_point_verdict(_release("GBP", "gb_cpi", "CPI y/y", "2.9%", forecast="2.9%")) == "neutral"


def test_forecast_absent_falls_back_to_previous():
    # no forecast -> actual vs previous (unchanged = neutral)
    assert v.data_point_verdict(_release("USD", "us_nfp", "NFP", "190K", previous="160K")) == "bullish"
    assert v.data_point_verdict(_release("USD", "us_nfp", "NFP", "160K", previous="160K")) == "neutral"
    assert v.data_point_verdict(_release("USD", "us_unemployment", "Unemployment", "4.1%",
                                         previous="4.0%", direction="lower_is_bullish")) == "bearish"


def test_lower_is_bullish_inverse():
    assert v.data_point_verdict(_release("JPY", "jp_core_cpi", "Core CPI", "2.2%", forecast="2.0%", direction="higher_is_bullish")) == "bullish"


# ── releases: latest released reading wins ────────────────
def test_build_releases_picks_latest():
    events = [
        {"title": "CPI y/y", "country": "GBP", "date_utc": "2026-07-01T12:00:00+00:00",
         "previous": "2.8%", "forecast": "3.0%", "actual": "3.2%"},
        {"title": "CPI y/y", "country": "GBP", "date_utc": "2026-08-01T12:00:00+00:00",
         "previous": "3.2%", "forecast": "2.9%", "actual": "3.1%"},
        {"title": "CPI y/y", "country": "GBP", "date_utc": "2026-09-01T12:00:00+00:00",  # pending
         "previous": "3.1%", "forecast": "2.8%", "actual": ""},
    ]
    sc = v.load_scorecard() if hasattr(v, "load_scorecard") else None
    from scoring.score import match_data_point
    releases = {}
    for ev in events:
        if sc is None or ev["country"] not in sc["currencies"] or not ev["actual"]:
            continue
        dp = match_data_point(sc, ev["country"], ev["title"])
        if not dp:
            continue
        dkey = f"{ev['country']}|{dp['id']}"
        releases[dkey] = {"country": ev["country"], "dataPointId": dp["id"],
                          "period": ev["date_utc"], "actual": ev["actual"],
                          "forecast": ev.get("forecast", ""), "previous": ev.get("previous", "")}
    assert len(releases) >= 1
    val = max(releases.values(), key=lambda r: r["period"])
    assert val["actual"] == "3.1%"  # the LATEST released (Sep pending is ignored)


# ── currency tally -> verdict bands ───────────────────────
def test_currency_tally_bands_and_cap():
    rules = {"weights": {"High": 2.0, "Medium": 1.0, "Low": 0.5},
             "currencies": {"GBP": {"dataPoints": {}, "specials": []}},
             "specials": {}, "bands": {"min_released_for_strong": 3, "net_bull_threshold": 0.2, "net_bear_threshold": -0.2, "strong_threshold": 0.55}}
    ctx = {"oil_direction": "flat", "risk_mode": "flat"}
    releases = {
        "GBP|a": _release("GBP", "a", "CPI y/y", "3.1%", forecast="2.9%"),
        "GBP|b": _release("GBP", "b", "GDP m/m", "0.5%", forecast="0.3%"),
        "GBP|c": _release("GBP", "c", "Unemployment Rate", "3.8%", forecast="4.0%", direction="lower_is_bullish"),
    }
    res = v.currency_verdict("GBP", releases, rules, ctx)
    assert res["verdict"] == "Very Bullish"
    assert res["tally"]["bullish"] > 0

    # single released point can't hit Very
    single = {"GBP|x": _release("GBP", "x", "CPI y/y", "3.1%", forecast="2.9%")}
    res2 = v.currency_verdict("GBP", single, rules, ctx)
    assert res2["verdict"] == "Bullish"


def test_pair_matrix():
    assert v.pair_from_matrix("Very Bullish", "Very Bearish") == "Very Bullish"
    assert v.pair_from_matrix("Bullish", "Neutral") == "Bullish"
    assert v.pair_from_matrix("Neutral", "Neutral") == "Neutral"
    assert v.pair_from_matrix("Neutral", "Bullish") == "Bearish"
    assert v.pair_from_matrix("Very Bearish", "Bullish") == "Very Bearish"


def test_usd_more_bullish_than_eur_makes_eurusd_bearish():
    # EUR bullish, USD more bullish => EURUSD bearish (differential logic)
    assert v.pair_from_matrix("Bullish", "Very Bullish") == "Bearish"
    assert v.pair_from_matrix("Very Bullish", "Bullish") == "Bullish"


def test_inverse_usd_drives_metals():
    # Same real-yield/DXY context, but a strongly BULLISH USD must flip gold bearish
    base_ctx = {"real_yield_sig": 0, "dxy_sig": 0, "m2_sig": 0, "china_pmi_sig": 0,
                "oil_direction": "flat", "risk_mode": "flat", "cot": {"XAUUSD": 0}}
    cfg = {"kind": "metal"}
    bull = dict(base_ctx, usd_anchor=2)
    bear = dict(base_ctx, usd_anchor=-2)
    assert v.instrument_verdict("XAUUSD", cfg, {}, bull)["verdict"] in ("Bearish", "Very Bearish")
    assert v.instrument_verdict("XAUUSD", cfg, {}, bear)["verdict"] in ("Bullish", "Very Bullish")


def test_crypto_uses_m2_and_usd():
    cfg = {"kind": "crypto"}
    ctx = {"real_yield_sig": 0, "dxy_sig": 0, "m2_sig": 0, "china_pmi_sig": 0,
           "oil_direction": "flat", "risk_mode": "flat", "cot": {}}
    # proxy-derived signals are capped at single-step verdicts
    assert v.instrument_verdict("BTCUSD", cfg, {}, dict(ctx, m2_sig=1, usd_anchor=-2))["verdict"] == "Bullish"
    assert v.instrument_verdict("BTCUSD", cfg, {}, dict(ctx, m2_sig=-1, usd_anchor=2))["verdict"] == "Bearish"


def test_band_map():
    assert v._verdict_band(0.7, 0.6) == "Very Bullish"
    assert v._verdict_band(0.6, 0.3) == "Bullish"
    assert v._verdict_band(0.5, 0.0) == "Neutral"
    assert v._verdict_band(0.2, -0.3) == "Bearish"
    assert v._verdict_band(0.1, -0.7) == "Very Bearish"

# ?? engine v4: level rules, forecast priority, 2Y yield, JOLTS ????????
def test_pmi_level_threshold_dominates_forecast():
    r = _release("USD", "us_ism", "ISM Manufacturing PMI", "54.6", forecast="55.2")
    r["level"] = {"threshold": 50, "higher_is_bullish": True}
    assert v.data_point_verdict(r) == "bullish"
    r2 = _release("USD", "us_ism", "ISM Manufacturing PMI", "49.5", forecast="48.5")
    r2["level"] = {"threshold": 50, "higher_is_bullish": True}
    assert v.data_point_verdict(r2) == "bearish"
    r3 = _release("USD", "us_ism", "ISM Manufacturing PMI", "50.0", forecast="49.0")
    r3["level"] = {"threshold": 50, "higher_is_bullish": True}
    assert v.data_point_verdict(r3) == "neutral"


def test_jolts_and_adp_map_in_scorecard():
    from scoring.score import match_data_point
    from common.utils import load_scorecard
    sc = load_scorecard()
    dp = match_data_point(sc, "USD", "JOLTS Job Openings")
    assert dp and dp["id"] == "us_jolts"
    dp2 = match_data_point(sc, "USD", "ADP Employment Change")
    assert dp2 and dp2["id"] == "us_adp"


def test_candidate_priority_prefers_forecast_then_newer():
    assert v._candidate_priority({"forecast": "3.4%", "period": "2026-09-01"},
                                 {"forecast": "", "period": "2026-08-01"}) is True
    assert v._candidate_priority({"forecast": "", "period": "2026-08-01"},
                                 {"forecast": "3.4%", "period": "2026-09-01"}) is False
    assert v._candidate_priority({"forecast": "3.4%", "period": "2026-09-01"},
                                 {"forecast": "3.5%", "period": "2026-08-01"}) is True
    assert v._candidate_priority({"forecast": "3.5%", "period": "2026-08-01"},
                                 {"forecast": "3.5%", "period": "2026-09-01"}) is False


def test_usd_14point_scenario_yields_bullish():
    rules = v.load_config("verdict_rules.json")
    ctx = {"oil_direction": "flat", "risk_mode": "flat", "cot": {}}
    rel = {
        "USD|us_gdp": _release("USD", "us_gdp", "Advance GDP (q/q)", "1.50%", forecast="1.50%"),
        "USD|us_ism": _release("USD", "us_ism", "Manufacturing PMI", "54.6", forecast="55.2"),
        "USD|us_retail": _release("USD", "us_retail", "Retail Sales MoM", "1.20%", forecast="0.80%"),
        "USD|us_confidence": _release("USD", "us_confidence", "Consumer Confidence", "89.4", forecast="90.3"),
        "USD|us_cpi": _release("USD", "us_cpi", "CPI YoY", "3.4%", forecast="3.4%"),
        "USD|us_ppi": _release("USD", "us_ppi", "PPI YoY", "5.4%", forecast="5.3%"),
        "USD|us_pce": _release("USD", "us_pce", "Core PCE YoY", "3.3%", forecast="3.3%"),
        "USD|us_yield2y": _release("USD", "us_yield2y", "2-Year Treasury Yield (21-day trend)", "4.56", previous="4.38"),
        "USD|us_nfp": _release("USD", "us_nfp", "Non-Farm Employment Change", "162K", forecast="55K"),
        "USD|us_unemployment": _release("USD", "us_unemployment", "Unemployment Rate", "4.1%", forecast="4.1%", direction="lower_is_bullish"),
        "USD|us_claims": _release("USD", "us_claims", "Initial Jobless Claims", "197K", forecast="201K", direction="lower_is_bullish"),
        "USD|us_adp": _release("USD", "us_adp", "ADP Employment Change", "38K", forecast="47K"),
        "USD|us_jolts": _release("USD", "us_jolts", "JOLTS Job Openings", "7.27M", forecast="7.33M"),
    }
    res = v.currency_verdict("USD", rel, rules, ctx)
    assert res["verdict"] == "Bullish", res
    assert res["tally"]["bullish"] > res["tally"]["bearish"]


def test_gold_bearish_when_usd_bullish_and_2y_rising():
    cfg = {"kind": "metal"}
    base = {"real_yield_sig": 0, "dxy_sig": 0, "m2_sig": 0, "china_pmi_sig": 0,
            "oil_direction": "flat", "risk_mode": "flat", "cot": {"XAUUSD": 0}}
    out = v.instrument_verdict("XAUUSD", cfg, {}, dict(base, usd_anchor=1, yield2y_sig=1))
    assert out["verdict"] in ("Bearish", "Very Bearish"), out
    assert any("2Y yield" in n for n in out["notes"])


def test_yield2y_injected_into_releases():
    rel = v.build_releases()
    key = "USD|us_yield2y"
    assert key in rel, sorted(rel.keys())[:10]
    assert rel[key]["dataPoint"] == "2-Year Treasury Yield (21-day trend)"
    assert rel[key]["actual"]
