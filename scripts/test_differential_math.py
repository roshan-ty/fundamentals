#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Currency Differential Scoring Verification

Codifies the Lesson A/B/C financial & mathematical matrix:

  Lesson A — Base vs Quote Currency Dynamics
    BASE/QUOTE pair. If BASE score rises relative to QUOTE => pair UP.
    If QUOTE score rises relative to BASE => pair DOWN.

  Lesson B — Direct vs Inverse USD Pairs
    Inverse USD (XXX/USD: EURUSD, GBPUSD, AUDUSD, XAU/USD, XAG/USD, BTCUSD):
        Score_XXX/USD = 11.0 - Score_USD
    Direct USD (USD/XXX: USDJPY, USDCAD, USDCHF):
        Score_USD/XXX = Score_USD

  Lesson C — Non-USD Cross Pairs (EURGBP, GBPJPY, AUDCAD)
    Cross Score = 5.0 + (Score_BASE - Score_QUOTE), clamped to [1.0, 10.0]

Run:
    python scripts/test_differential_math.py

Exit code 0 = all formula assertions pass.
"""

import math

# ── Pure math functions matching backend/scorer.py semantics ──────────────────

def pair_bias(base_score: float, quote_score: float) -> float:
    """Lesson C: Cross Score = 5.0 + (S_BASE - S_QUOTE), clamped [1, 10]."""
    return max(1.0, min(10.0, 5.0 + (base_score - quote_score)))


def inverse_usd_score(usd_score: float) -> float:
    """Lesson B: Score_XXX/USD = 11.0 - S_USD (XAU, XAG, EUR, GBP, AUD, ...)."""
    return max(1.0, min(10.0, 11.0 - usd_score))


def direct_usd_score(usd_score: float) -> float:
    """Lesson B: Score_USD/XXX = S_USD (JPY, CAD, CHF)."""
    return max(1.0, min(10.0, usd_score))


# ── Test suite ───────────────────────────────────────────────────────────

def _assert_close(actual: float, expected: float, label: str) -> None:
    if abs(actual - expected) > 1e-9:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")
    print(f"  [PASS] {label} = {actual}")


def test_lesson_a_direction() -> None:
    print("\n[Lesson A] Base/Quote Direction Dynamics")
    # BASE stronger than QUOTE => pair UP (Bullish)
    _assert_close(pair_bias(7.0, 4.0), 8.0, "S_BASE=7, S_QUOTE=4 -> Pair Bias")
    # QUOTE stronger than BASE => pair DOWN (Bearish)
    _assert_close(pair_bias(4.0, 7.0), 2.0, "S_BASE=4, S_QUOTE=7 -> Pair Bias")
    # Equal scores => neutral 5.0
    _assert_close(pair_bias(5.0, 5.0), 5.0, "S_BASE=5, S_QUOTE=5 -> Pair Bias")


def test_lesson_b_usd_pairs() -> None:
    print("\n[Lesson B]: Direct vs Inverse USD Pairs")
    weak_usd = 3.2
    strong_usd = 8.0

    # Weak USD => Bullish for XXX/USD
    _assert_close(inverse_usd_score(weak_usd), 11.0 - 3.2, "Weak USD -> XAU/EUR (inverse)")
    _assert_close(inverse_usd_score(strong_usd), 11.0 - 8.0, "Strong USD -> XAU/EUR (inverse)")

    # USD as base => bearish when USD weak, bullish when USD strong
    _assert_close(direct_usd_score(weak_usd), 3.2, "Weak USD -> USD/JPY (direct)")
    _assert_close(direct_usd_score(strong_usd), 8.0, "Strong USD -> USD/JPY (direct)")

    # Clamping
    _assert_close(inverse_usd_score(1.0), 10.0, "S_USD=1 -> inverse clamp at 10")
    _assert_close(inverse_usd_score(10.0), 1.0, "S_USD=10 -> inverse clamp at 1")


def test_lesson_c_cross_pairs() -> None:
    print("\n[Lesson C]: Non-USD Cross Pair Differential")
    # Task example: Eurozone 7.0 (bullish), UK 4.0 (bearish) -> EURGBP = 8.0 (Strongly Bullish)
    _assert_close(pair_bias(7.0, 4.0), 8.0, "EURGBP example (7.0 - 4.0)")
    # GBPJPY: UK 6.0 vs Japan 3.0 -> GBPJPY = 8.0
    _assert_close(pair_bias(6.0, 3.0), 8.0, "GBPJPY example (6.0 - 3.0)")
    # AUDCAD: Australia 4.0 vs Canada 6.5 -> AUDCAD = 2.5 (Bearish)
    _assert_close(pair_bias(4.0, 6.5), 2.5, "AUDCAD example (4.0 - 6.5)")

    # Clamping to [1.0, 10.0]
    _assert_close(pair_bias(15.0, 3.0), 10.0, "Clamp high (diff=12)")
    _assert_close(pair_bias(3.0, 15.0), 1.0, "Clamp low (diff=-12)")


def test_cross_spillover_matrix() -> None:
    print("\n[Cross-Asset Spillover Matrix]: S_USD=3.2 Example")
    usd = 3.2
    for asset in ("XAU", "EUR", "GBP", "AUD", "BTC"):
        score = inverse_usd_score(usd)
        _assert_close(score, 7.8, f"{asset} inverse score (11.0 - 3.2)")
    for asset in ("JPY", "CAD", "CHF"):
        score = direct_usd_score(usd)
        _assert_close(score, 3.2, f"{asset} direct score (= S_USD)")


def main() -> int:
    print("=" * 60)
    print(" BULLS & BEARS FUNDAMENTALS — DIFFERENTIAL MATH VERIFICATION")
    print("=" * 60)
    test_lesson_a_direction()
    test_lesson_b_usd_pairs()
    test_lesson_c_cross_pairs()
    test_cross_spillover_matrix()
    print("\nAll differential math assertions passed — formulas verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())