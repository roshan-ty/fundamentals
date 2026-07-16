"""
Unit tests for the Bulls & Bears Fundamentals scoring engine.
Tests data models, scoring logic, and pair mathematics.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from backend.models.schemas import (
    FredData, FredSeries, CftcData, CftcPosition,
    YieldData, YieldEntry, CalendarData, CalendarEvent,
    CurrencyScores, PairBias, PairsData, TradeSetup,
    clamp, direction_label,
)
from backend.scoring.macro_score import compute_macro_score, _score_usd_macro
from backend.scoring.event_surprise import compute_event_surprise_score
from backend.scoring.yield_score import compute_yield_score
from backend.scoring.cftc_sentiment import compute_cftc_sentiment_score
from backend.scoring.pair_math import compute_pairs_bias, compute_trade_setups


# ═══════════════════════════════════════════════════════════════════════════
# ── Schema & Utility Tests ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestClamp:
    def test_clamp_within_range(self):
        assert clamp(5.0) == 5.0
        assert clamp(0.0) == 0.0
        assert clamp(10.0) == 10.0

    def test_clamp_below_minimum(self):
        assert clamp(-1.0) == 0.0
        assert clamp(-5.0) == 0.0

    def test_clamp_above_maximum(self):
        assert clamp(11.0) == 10.0
        assert clamp(15.0) == 10.0

    def test_clamp_custom_bounds(self):
        assert clamp(5.0, 2.0, 8.0) == 5.0
        assert clamp(1.0, 2.0, 8.0) == 2.0
        assert clamp(10.0, 2.0, 8.0) == 8.0


class TestDirectionLabel:
    def test_strongly_bullish(self):
        assert direction_label(9.0) == "Strongly Bullish"
        assert direction_label(8.0) == "Strongly Bullish"

    def test_bullish(self):
        assert direction_label(7.0) == "Bullish"
        assert direction_label(6.0) == "Bullish"

    def test_neutral(self):
        assert direction_label(5.0) == "Neutral"
        assert direction_label(4.5) == "Neutral"
        assert direction_label(4.1) == "Neutral"

    def test_bearish(self):
        assert direction_label(4.0) == "Bearish"
        assert direction_label(3.0) == "Bearish"
        assert direction_label(2.1) == "Bearish"

    def test_strongly_bearish(self):
        assert direction_label(2.0) == "Strongly Bearish"
        assert direction_label(0.0) == "Strongly Bearish"


class TestFredSeries:
    def test_create_fred_series(self):
        fs = FredSeries(series_id="GDPC1", series_name="GDP", date="2026-01-01", value=23000.0)
        assert fs.series_id == "GDPC1"
        assert fs.value == 23000.0

    def test_fred_data_container(self):
        fd = FredData()
        fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date="2026-01-01", value=4.0))
        assert len(fd.series) == 1


# ═══════════════════════════════════════════════════════════════════════════
# ── FRED Macro Score Tests ────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestMacroScore:
    @pytest.fixture
    def growing_economy_data(self):
        """GDP growing steadily, unemployment falling."""
        fd = FredData()
        for i, (q, val) in enumerate([("2025-01-01", 22000), ("2025-04-01", 22400),
                                       ("2025-07-01", 22700), ("2025-10-01", 22950),
                                       ("2026-01-01", 23200)]):
            fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date=q, value=val))
        for i, (d, val) in enumerate([("2025-10-01", 4.8), ("2026-01-01", 4.5),
                                       ("2026-04-01", 4.2), ("2026-07-01", 3.9)]):
            fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date=d, value=val))
        return fd

    @pytest.fixture
    def recession_data(self):
        """GDP contracting, unemployment spiking."""
        fd = FredData()
        for i, (q, val) in enumerate([("2025-01-01", 23000), ("2025-04-01", 22800),
                                       ("2025-07-01", 22500), ("2025-10-01", 22200),
                                       ("2026-01-01", 21800)]):
            fd.series.append(FredSeries(series_id="GDPC1", series_name="GDP", date=q, value=val))
        for i, (d, val) in enumerate([("2025-10-01", 5.5), ("2026-01-01", 5.8),
                                       ("2026-04-01", 6.2), ("2026-07-01", 6.8)]):
            fd.series.append(FredSeries(series_id="UNRATE", series_name="UNRATE", date=d, value=val))
        return fd

    def test_growing_economy_scores_high(self, growing_economy_data):
        scores = compute_macro_score(growing_economy_data)
        assert scores["USD"] >= 7.0, f"Growing economy should score high, got {scores['USD']}"

    def test_recession_scores_low(self, recession_data):
        scores = compute_macro_score(recession_data)
        assert scores["USD"] <= 4.0, f"Recession should score low, got {scores['USD']}"

    def test_empty_data_returns_neutral(self):
        fd = FredData()
        scores = compute_macro_score(fd)
        assert scores["USD"] == 5.0
        for c in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]:
            assert scores[c] == 5.0

    def test_non_usd_currencies_default(self, growing_economy_data):
        scores = compute_macro_score(growing_economy_data)
        for c in ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]:
            assert scores[c] == 5.0


# ═══════════════════════════════════════════════════════════════════════════
# ── Event Surprise Score Tests ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestEventSurpriseScore:
    @pytest.fixture
    def positive_surprises(self):
        cd = CalendarData()
        for name, actual, forecast in [
            ("CPI", 3.5, 3.0), ("NFP", 250, 200), ("GDP", 2.5, 2.2),
            ("Retail Sales", 0.8, 0.5), ("PMI", 52, 50),
        ]:
            cd.events.append(CalendarEvent(
                currency="USD", event_name=name, date="2026-07",
                actual=actual, forecast=forecast, previous=forecast,
                surprise_ratio=(actual - forecast) / abs(forecast),
            ))
        return cd

    @pytest.fixture
    def negative_surprises(self):
        cd = CalendarData()
        for name, actual, forecast in [
            ("CPI", 2.5, 3.0), ("NFP", 150, 200), ("GDP", 1.5, 2.2),
        ]:
            cd.events.append(CalendarEvent(
                currency="USD", event_name=name, date="2026-07",
                actual=actual, forecast=forecast, previous=forecast,
                surprise_ratio=(actual - forecast) / abs(forecast),
            ))
        return cd

    def test_positive_surprises_score_high(self, positive_surprises):
        scores = compute_event_surprise_score(positive_surprises)
        assert scores["USD"] >= 6.0, f"Positive surprises should score high, got {scores['USD']}"

    def test_negative_surprises_score_low(self, negative_surprises):
        scores = compute_event_surprise_score(negative_surprises)
        assert scores["USD"] <= 4.0, f"Negative surprises should score low, got {scores['USD']}"

    def test_empty_data_returns_neutral(self):
        cd = CalendarData()
        scores = compute_event_surprise_score(cd)
        for c in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF"]:
            assert scores[c] == 5.0

    def test_mixed_surprises_near_neutral(self):
        cd = CalendarData()
        cd.events.append(CalendarEvent(currency="USD", event_name="CPI", date="2026-07",
                                       actual=3.0, forecast=3.0, previous=2.8, surprise_ratio=0.0))
        cd.events.append(CalendarEvent(currency="USD", event_name="NFP", date="2026-07",
                                       actual=200, forecast=200, previous=190, surprise_ratio=0.0))
        scores = compute_event_surprise_score(cd)
        assert 4.0 <= scores["USD"] <= 6.0


# ═══════════════════════════════════════════════════════════════════════════
# ── Yield Score Tests ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestYieldScore:
    @pytest.fixture
    def rising_yields(self):
        yd = YieldData()
        yd.entries.append(YieldEntry(instrument="US10Y", date="2026-07-15", yield_value=4.8, yield_ma50=4.2))
        yd.entries.append(YieldEntry(instrument="DE10Y", date="2026-07-15", yield_value=2.8, yield_ma50=2.6))
        yd.entries.append(YieldEntry(instrument="GB10Y", date="2026-07-15", yield_value=4.5, yield_ma50=4.3))
        yd.entries.append(YieldEntry(instrument="JP10Y", date="2026-07-15", yield_value=1.4, yield_ma50=1.1))
        return yd

    @pytest.fixture
    def falling_yields(self):
        yd = YieldData()
        yd.entries.append(YieldEntry(instrument="US10Y", date="2026-07-15", yield_value=3.8, yield_ma50=4.2))
        yd.entries.append(YieldEntry(instrument="DE10Y", date="2026-07-15", yield_value=2.2, yield_ma50=2.6))
        return yd

    def test_rising_yields_score_high(self, rising_yields):
        scores = compute_yield_score(rising_yields)
        assert scores["USD"] >= 6.0
        assert scores["EUR"] >= 5.0

    def test_falling_yields_score_low(self, falling_yields):
        scores = compute_yield_score(falling_yields)
        assert scores["USD"] <= 4.0
        assert scores["EUR"] <= 4.0

    def test_missing_data_defaults(self):
        yd = YieldData()
        scores = compute_yield_score(yd)
        for c in ["USD", "EUR", "GBP", "JPY"]:
            assert scores[c] == 5.0

    def test_aud_cad_chf_default(self, rising_yields):
        scores = compute_yield_score(rising_yields)
        for c in ["AUD", "CAD", "CHF"]:
            assert scores[c] == 5.0


# ═══════════════════════════════════════════════════════════════════════════
# ── CFTC Sentiment Score Tests ────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestCftcSentimentScore:
    @pytest.fixture
    def cftc_data(self):
        cd = CftcData()
        cd.positions.append(CftcPosition(market="EUR", report_date="2026-07-14",
                                         noncomm_long=200000, noncomm_short=100000,
                                         net_speculative=100000, weekly_change=5000, percentile_52w=82.5))
        cd.positions.append(CftcPosition(market="JPY", report_date="2026-07-14",
                                         noncomm_long=30000, noncomm_short=80000,
                                         net_speculative=-50000, weekly_change=-3000, percentile_52w=15.0))
        return cd

    @pytest.fixture
    def overcrowded_long(self):
        cd = CftcData()
        cd.positions.append(CftcPosition(market="XAU", report_date="2026-07-14",
                                         noncomm_long=250000, noncomm_short=50000,
                                         net_speculative=200000, weekly_change=20000, percentile_52w=97.0))
        return cd

    @pytest.fixture
    def overcrowded_short(self):
        cd = CftcData()
        cd.positions.append(CftcPosition(market="GBP", report_date="2026-07-14",
                                         noncomm_long=20000, noncomm_short=180000,
                                         net_speculative=-160000, weekly_change=-20000, percentile_52w=2.0))
        return cd

    def test_bullish_position_scores_high(self, cftc_data):
        scores = compute_cftc_sentiment_score(cftc_data)
        assert scores["EUR"] >= 7.0

    def test_bearish_position_scores_low(self, cftc_data):
        scores = compute_cftc_sentiment_score(cftc_data)
        assert scores["JPY"] <= 3.0

    def test_overcrowded_long_capped(self, overcrowded_long):
        scores = compute_cftc_sentiment_score(overcrowded_long)
        # Overcrowded rule scales toward neutral but doesn't flatline — score should be reduced but not fully neutral
        assert scores["XAU"] <= 7.0, "Overcrowded long should be scaled down toward neutral"
        assert scores["XAU"] > 5.0, "Overcrowded long should retain some bullish signal"

    def test_overcrowded_short_capped(self, overcrowded_short):
        scores = compute_cftc_sentiment_score(overcrowded_short)
        assert scores["GBP"] <= 7.0, "Overcrowded short should be scaled down toward neutral"
        assert scores["GBP"] < 5.0, "Overcrowded short should retain some bearish signal"

    def test_empty_data_returns_neutral(self):
        cd = CftcData()
        scores = compute_cftc_sentiment_score(cd)
        for market in ["EUR", "GBP", "JPY", "CAD", "CHF", "AUD", "XAU", "XAG", "WTI", "SP500", "NAS100"]:
            assert scores.get(market) == 5.0


# ═══════════════════════════════════════════════════════════════════════════
# ── Pair Math & Trade Setups Tests ────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

class TestPairMath:
    @pytest.fixture
    def sample_currency_scores(self):
        return {
            "USD": CurrencyScores(currency="USD", macro_score=7.0, event_surprise_score=7.0,
                                   yield_momentum_score=7.0, cftc_sentiment_score=7.0, average_score=7.0),
            "EUR": CurrencyScores(currency="EUR", macro_score=4.0, event_surprise_score=5.0,
                                   yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=4.75),
            "GBP": CurrencyScores(currency="GBP", macro_score=5.0, event_surprise_score=6.0,
                                   yield_momentum_score=6.0, cftc_sentiment_score=6.0, average_score=5.75),
            "JPY": CurrencyScores(currency="JPY", macro_score=5.0, event_surprise_score=4.0,
                                   yield_momentum_score=4.0, cftc_sentiment_score=3.0, average_score=4.0),
            "AUD": CurrencyScores(currency="AUD", macro_score=5.0, event_surprise_score=5.0,
                                   yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
            "CAD": CurrencyScores(currency="CAD", macro_score=5.0, event_surprise_score=5.0,
                                   yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
            "CHF": CurrencyScores(currency="CHF", macro_score=5.0, event_surprise_score=5.0,
                                   yield_momentum_score=5.0, cftc_sentiment_score=5.0, average_score=5.0),
        }

    def test_fx_pair_count(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        fx_pairs = [p for p in pairs.pairs if p.asset_class == "FX"]
        # 7 currencies * 6 permutations = 42 FX pairs
        assert len(fx_pairs) == 42, f"Expected 42 FX pairs, got {len(fx_pairs)}"

    def test_strong_usd_bullish_pair(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        usd_jpy = next((p for p in pairs.pairs if p.name == "USD/JPY"), None)
        assert usd_jpy is not None
        # USD=7.0, JPY=4.0 → 5 + (7-4) = 8.0
        assert usd_jpy.combined_bias >= 7.0
        assert "Bullish" in usd_jpy.direction

    def test_weak_jpy_bearish_pair(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        jpy_usd = next((p for p in pairs.pairs if p.name == "JPY/USD"), None)
        assert jpy_usd is not None
        # JPY=4.0, USD=7.0 → 5 + (4-7) = 2.0
        assert jpy_usd.combined_bias <= 3.0
        assert "Bearish" in jpy_usd.direction

    def test_metal_bias_vs_usd_yield(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        gold = next((p for p in pairs.pairs if p.name == "XAU/USD"), None)
        assert gold is not None
        # Gold = 10 - USD Yield Score = 10 - 7 = 3.0
        assert gold.asset_class == "METAL"

    def test_total_pairs_count(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        # 42 FX + 2 Metals + 1 Energy + 3 Indices = 48
        assert len(pairs.pairs) == 48, f"Expected 48 total, got {len(pairs.pairs)}"

    def test_usd_jpy_pair_formula(self, sample_currency_scores):
        pairs = compute_pairs_bias(sample_currency_scores)
        usd_jpy = next((p for p in pairs.pairs if p.name == "USD/JPY"), None)
        expected = 5.0 + (7.0 - 4.0)
        assert abs(usd_jpy.combined_bias - expected) < 0.01


class TestTradeSetups:
    @pytest.fixture
    def pairs_with_extremes(self):
        pd = PairsData()
        pd.pairs.append(PairBias(asset_class="FX", name="USD/JPY",
                                  base_currency="USD", quote_currency="JPY",
                                  base_score=9.0, quote_score=2.0,
                                  combined_bias=9.0, direction="Strongly Bullish",
                                  conclusion="USD extremely strong"))
        pd.pairs.append(PairBias(asset_class="FX", name="JPY/USD",
                                  base_currency="JPY", quote_currency="USD",
                                  base_score=2.0, quote_score=9.0,
                                  combined_bias=1.0, direction="Strongly Bearish",
                                  conclusion="JPY extremely weak"))
        pd.pairs.append(PairBias(asset_class="FX", name="EUR/USD",
                                  base_currency="EUR", quote_currency="USD",
                                  base_score=5.0, quote_score=5.0,
                                  combined_bias=5.0, direction="Neutral",
                                  conclusion="Neutral"))
        return pd

    def test_extreme_pair_identified(self, pairs_with_extremes):
        setups = compute_trade_setups(pairs_with_extremes)
        names = [s.asset_name for s in setups.setups]
        assert "USD/JPY" in names
        assert "JPY/USD" in names

    def test_neutral_pair_excluded(self, pairs_with_extremes):
        setups = compute_trade_setups(pairs_with_extremes)
        names = [s.asset_name for s in setups.setups]
        assert "EUR/USD" not in names

    def test_setups_ordered_by_strength(self, pairs_with_extremes):
        setups = compute_trade_setups(pairs_with_extremes)
        # Most extreme first
        if len(setups.setups) >= 2:
            bias1 = abs(setups.setups[0].combined_bias - 5.0)
            bias2 = abs(setups.setups[1].combined_bias - 5.0)
            assert bias1 >= bias2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])