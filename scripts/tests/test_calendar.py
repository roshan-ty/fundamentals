# Unit tests: calendar fallback enrichment + scorer title normalization.
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from collectors.calendar_fallbacks import merge_calendars, _signature, _clean_value  # noqa: E402
from scoring.score import _normalize_title, _TITLE_MATCHERS, match_data_point, _events  # noqa: E402


def test_clean_value_strips_glyphs():
    assert _clean_value("\u201320.97B") == "-20.97B"
    assert _clean_value(" -2.5% ") == "-2.5%"


def test_signature_mom_family_equal():
    # FF "GDP m/m" and TE "GDP MoM JUL" must share a signature (both mom, core= gdp)
    s1 = _signature("GDP m/m")
    s2 = _signature("GDP MoM JUL")
    assert s1 == s2
    # different frequencies must NOT match (CPI m/m vs CPI y/y)
    s3 = _signature("CPI y/y")
    s4 = _signature("CPI m/m")
    assert s3 != s4


def test_merge_enriches_matching_event():
    primary = [{"title": "GDP m/m", "country": "GBP", "date_utc": "2026-09-11T10:00:00+00:00",
                "forecast": "0.2%", "previous": "0.3%", "actual": ""}]
    fb = [{"title": "GDP MoM JUL", "country": "GBP", "date_utc": "2026-09-11T10:00:00+00:00",
           "forecast": "", "previous": "0.3%", "actual": "0.4%", "source": "te"}]
    out = merge_calendars(primary, fb)
    # one event survives and carries the actual
    assert len(out) == 1
    assert out[0]["actual"] == "0.4%"
    assert out[0]["previous"] == "0.3%"


def test_normalize_title_variants():
    assert _normalize_title("GDP MoM JUL") == "gdp m/m jul"
    assert _normalize_title("GDP YoY JUL") == "gdp y/y jul"


def test_gbp_gdp_matches_after_normalization():
    sc = {"currencies": {"GBP": {"_index": {"gb_gdp": {"id": "gb_gdp", "weight": 1.0}}}}}
    dp = match_data_point(sc, "GBP", "GDP MoM JUL")
    assert dp is not None and dp["id"] == "gb_gdp"


def test_clean_value_keeps_negative_pct():
    assert _clean_value(" -2.5% ") == "-2.5%"
    assert _clean_value("-3.450B") == "-3.450B"