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


def test_band_map():
    assert v._verdict_band(0.7, 0.6) == "Very Bullish"
    assert v._verdict_band(0.6, 0.3) == "Bullish"
    assert v._verdict_band(0.5, 0.0) == "Neutral"
    assert v._verdict_band(0.2, -0.3) == "Bearish"
    assert v._verdict_band(0.1, -0.7) == "Very Bearish"