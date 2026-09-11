# Unit tests for the scoring engine.
# Proves the golden rule (actual vs previous; unchanged = 0) and the EUR/USD
# multi-scenario behavior specified by the trader.
import json
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from scoring.score import norm_num, decide, score_currencies  # noqa: E402
from scoring import score as score_module  # noqa: E402


def _seed_events(tmp, events):
    cal = os.path.join(tmp, "calendar")
    os.makedirs(cal, exist_ok=True)
    with open(os.path.join(cal, "events_current.json"), "w", encoding="utf-8") as fh:
        json.dump(events, fh)
    with open(os.path.join(cal, "fred_events.json"), "w", encoding="utf-8") as fh:
        json.dump([], fh)


def _score_with(events, tmp_path, monkeypatch):
    _seed_events(str(tmp_path), events)
    monkeypatch.setattr(score_module, "DATA_DIR", str(tmp_path))
    return score_currencies()


# ── number parsing ─────────────────────────────────────────
def test_norm_num_plain():
    assert norm_num("3.4") == 3.4
    assert norm_num("3.4%") == 3.4
    assert norm_num("-1.4M") == -1_400_000
    assert norm_num("2.48T") == 2_480_000_000_000
    assert norm_num("805B") == 805_000_000_000
    assert norm_num("0.2%") == 0.2
    assert norm_num(None) is None
    assert norm_num("") is None


# ── golden rule ────────────────────────────────────────────
def test_decide_unchanged_is_zero():
    assert decide("2.4%", "2.4%", "higher_is_bullish") == 0
    assert decide("2.4%", "2.4%", "lower_is_bullish") == 0


def test_decide_higher_is_bullish():
    assert decide("2.6%", "2.4%", "higher_is_bullish") == 1
    assert decide("2.2%", "2.4%", "higher_is_bullish") == -1


def test_decide_lower_is_bullish():
    assert decide("3.9%", "4.1%", "lower_is_bullish") == 1
    assert decide("4.2%", "4.1%", "lower_is_bullish") == -1


def test_decide_needs_previous():
    assert decide("3.0%", None, "higher_is_bullish") == 0
    assert decide(None, "3.0%", "higher_is_bullish") == 0


# ── scenario: EUR more bullish than USD => EURUSD bullish ──
EUR_BULLISH_EVENTS = [
    # EUR data points (all higher than previous → bullish)
    {"title": "German IFO Business Climate", "country": "EUR", "impact": "Medium",
     "date_utc": "2026-08-01T10:00:00+00:00", "forecast": "89.0", "previous": "88.0", "actual": "90.0"},
    {"title": "CPI Flash Estimate y/y", "country": "EUR", "impact": "High",
     "date_utc": "2026-08-01T10:30:00+00:00", "forecast": "2.5%", "previous": "2.3%", "actual": "2.6%"},
    {"title": "Revised GDP q/q", "country": "EUR", "impact": "High",
     "date_utc": "2026-08-01T11:00:00+00:00", "forecast": "0.4%", "previous": "0.3%", "actual": "0.5%"},
    # USD data points (NFP lower than previous → bearish)
    {"title": "Non-Farm Employment Change", "country": "USD", "impact": "High",
     "date_utc": "2026-08-01T12:30:00+00:00", "forecast": "170K", "previous": "180K", "actual": "150K"},
]


def test_eur_more_bullish_than_usd_tilts_eurusd_bullish(tmp_path, monkeypatch):
    res = _score_with(EUR_BULLISH_EVENTS, tmp_path, monkeypatch)
    eur = res["EUR"]
    usd = res["USD"]
    # v2: EUR clearly bullish, USD mildly bearish (thin data can't saturate to 0)
    assert eur["score"] > 6
    assert eur["score"] > usd["score"]
    assert 4 <= usd["score"] < 5
    # pair = 5 + (EUR-5) - (USD-5) must be > 5 → bullish
    eurusd = 5.0 + (eur["score"] - 5.0) - (usd["score"] - 5.0)
    assert eurusd > 5.2
    assert eur["top_drivers"][0]["verdict"] == "bullish"
    assert usd["top_drivers"][0]["verdict"] == "bearish"


# ── scenario: USD more bullish than EUR => EURUSD bearish ──
USD_BULLISH_EVENTS = [
    {"title": "Non-Farm Employment Change", "country": "USD", "impact": "High",
     "date_utc": "2026-08-01T12:30:00+00:00", "forecast": "170K", "previous": "160K", "actual": "190K"},
    {"title": "CPI m/m", "country": "USD", "impact": "High",
     "date_utc": "2026-08-01T12:30:00+00:00", "forecast": "0.3%", "previous": "0.2%", "actual": "0.4%"},
    {"title": "German IFO Business Climate", "country": "EUR", "impact": "Medium",
     "date_utc": "2026-08-01T10:00:00+00:00", "forecast": "89.0", "previous": "88.0", "actual": "86.0"},
]


def test_usd_more_bullish_than_eur_tilts_eurusd_bearish(tmp_path, monkeypatch):
    res = _score_with(USD_BULLISH_EVENTS, tmp_path, monkeypatch)
    eur = res["EUR"]
    usd = res["USD"]
    assert usd["score"] > eur["score"] + 0.5
    assert usd["score"] > 5.5
    assert eur["score"] < 5
    eurusd = 5.0 + (eur["score"] - 5.0) - (usd["score"] - 5.0)
    assert eurusd < 4.5


# ── scenario: unchanged data => neutral ────────────────────
FLAT_EVENTS = [
    {"title": "Unemployment Rate", "country": "USD", "impact": "High",
     "date_utc": "2026-08-01T12:30:00+00:00", "forecast": "4.1%", "previous": "4.1%", "actual": "4.1%"},
    {"title": "CPI Flash Estimate y/y", "country": "EUR", "impact": "High",
     "date_utc": "2026-08-01T10:30:00+00:00", "forecast": "2.5%", "previous": "2.5%", "actual": "2.5%"},
]


def test_no_change_is_neutral(tmp_path, monkeypatch):
    res = _score_with(FLAT_EVENTS, tmp_path, monkeypatch)
    # unchanged data must leave scores at 5.0 (exactly neutral)
    assert res["USD"]["score"] == 5.0
    assert res["EUR"]["score"] == 5.0
    assert res["USD"]["band"] == "Neutral"
    assert res["EUR"]["band"] == "Neutral"


# ── banding ────────────────────────────────────────────────
def test_band_bounds():
    from scoring.score import _band_for
    assert _band_for(1.5) == "Very Bearish"
    assert _band_for(3.5) == "Bearish"
    assert _band_for(5.0) == "Neutral"
    assert _band_for(6.5) == "Bullish"
    assert _band_for(9.0) == "Very Bullish"
# ── engine v2 unit tests ──────────────────────────────────
def test_european_decimal_parsing():
    from scoring.score import norm_num
    assert norm_num("2,5%") == 2.5          # European decimal
    assert norm_num("1.234,56") == 1234.56  # European thousands+decimal
    assert norm_num("1,234.56") == 1234.56  # US thousands
    assert norm_num("(1,2)") == -1.2        # parenthesized negative


def test_thin_data_cannot_saturate(tmp_path, monkeypatch):
    # ONE bullish NFP must NOT print USD=10 anymore (v2 conservative denominator)
    evs = [{"title": "Non-Farm Employment Change", "country": "USD", "impact": "High",
            "date_utc": "2026-08-01T12:30:00+00:00", "previous": "160K", "actual": "190K"}]
    res = _score_with(evs, tmp_path, monkeypatch)
    assert res["USD"]["score"] < 8
    assert res["USD"]["score"] > 5
    assert res["USD"]["coverage"] > 0
    assert res["USD"]["coverage"] < 100


def test_forecast_confirmation_modulates():
    from scoring.score import _forecast_factor, _weeks_old, _decay
    # beat previous AND beat forecast -> full weight
    assert _forecast_factor("200K", "170K", "higher_is_bullish", 1) == 1.0
    # beat previous but MISS forecast -> 0.7
    assert _forecast_factor("165K", "170K", "higher_is_bullish", 1) == 0.7
    # bearish: actual below forecast -> full (aligned), above -> 0.7
    assert _forecast_factor("160K", "170K", "higher_is_bullish", -1) == 1.0
    assert _forecast_factor("180K", "170K", "higher_is_bullish", -1) == 0.7
    # no forecast -> neutral factor
    assert _forecast_factor("200K", "", "higher_is_bullish", 1) == 1.0


def test_recency_decay_floor():
    from scoring.score import _decay
    assert _decay(0) == 1.0
    fresh = _decay(1)
    stale = _decay(30)
    assert fresh > stale
    assert stale >= 0.25  # floor respected


def test_exotic_currency_scores(tmp_path, monkeypatch):
    # MXN has a scorecard now -> an MXN CPI beat must move it off neutral
    evs = [{"title": "CPI y/y", "country": "MXN", "impact": "High",
            "date_utc": "2026-08-01T12:30:00+00:00", "previous": "4.5%", "actual": "5.1%"}]
    res = _score_with(evs, tmp_path, monkeypatch)
    assert res["MXN"]["score"] > 5
    assert res["USD"]["score"] == 5.0  # USD untouched by MXN event