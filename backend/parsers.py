#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Data Parsers
Extracts 30 global macroeconomic data points across 8+ data sources.
All functions return structured dicts for the scoring engine.

Data Point Index:
  1-6, 11, 12, 20-22, 29: Economic Indicators & Labor (FMP + Finnhub)
  7-10, 23, 24: PMIs & Inflation Trends (AlphaVantage + FRED)
  13-19, 25: Central Bank & Policy Rates (FRED + FMP + BS4)
  26, 28: CFTC Institutional Positioning (CFTC.gov ZIP → Pandas)
  27: Retail Sentiment (DailyFX/Oanda BS4 scraping)
  30: Seasonality (yfinance 15-year monthly closes)
"""

import os
import io
import re
import json
import zipfile
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import yfinance as yf

logger = logging.getLogger(__name__)

# ── API Key Configuration ──────────────────────────────────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
EODHD_API_KEY = os.environ.get("EODHD_API_KEY", "")
NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY", "")

# ── Base URLs ──────────────────────────────────────────────────────────────────
FMP_BASE = "https://financialmodelingprep.com/api/v3"

# Browser-like headers to avoid 403 blocks
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# ── Constants ──────────────────────────────────────────────────────────────────
TARGET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
TARGET_CRYPTO = ["BTC", "ETH", "SOL", "XRP"]

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: FRED Macro Series (Points 7-10, 13-16, 23-24)
# ═══════════════════════════════════════════════════════════════════════════════

FRED_SERIES = {
    "GDPC1":    {"name": "Real GDP", "unit": "Billions USD"},
    "CPILFESL": {"name": "Core CPI", "unit": "Index 1982-1984=100"},
    "PCEPILFE": {"name": "Core PCE", "unit": "Index 2017=100"},
    "UNRATE":   {"name": "Unemployment Rate", "unit": "Percent"},
    "FEDFUNDS": {"name": "Fed Funds Rate", "unit": "Percent"},
    "DFII10":   {"name": "10Y TIPS Yield", "unit": "Percent"},
    "T10YIE":   {"name": "10Y Breakeven Inflation", "unit": "Percent"},
    "M2SL":     {"name": "M2 Money Supply", "unit": "Billions USD"},
    "INDPRO":   {"name": "Industrial Production", "unit": "Index 2017=100"},
    "CPIAUCSL": {"name": "Headline CPI", "unit": "Index 1982-1984=100"},
    "PPIACO":   {"name": "PPI All Commodities", "unit": "Index 1982=100"},
    "PAYEMS":   {"name": "Nonfarm Payrolls", "unit": "Thousands"},
    "DGS10":    {"name": "10Y Treasury Yield", "unit": "Percent"},
    "DGS2":     {"name": "2Y Treasury Yield", "unit": "Percent"},
}


def fetch_fred_series() -> dict[str, list[dict]]:
    """Fetch all configured FRED series. Returns {series_id: [observations]}."""
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set. Skipping FRED data.")
        return {}

    base_url = "https://api.stlouisfed.org/fred/series/observations"
    results: dict[str, list[dict]] = {}

    for series_id, meta in FRED_SERIES.items():
        try:
            params = {
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 120,
            }
            resp = requests.get(base_url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            observations = data.get("observations", [])

            parsed = []
            for obs in observations:
                val_str = obs.get("value", ".")
                if val_str in (".", "", None):
                    continue
                try:
                    val = float(val_str)
                except (ValueError, TypeError):
                    continue
                parsed.append({
                    "date": obs.get("date", ""),
                    "value": val,
                    "unit": meta["unit"],
                })

            results[series_id] = parsed
            logger.info("FRED: %s → %d observations", series_id, len(parsed))

        except requests.RequestException as e:
            logger.warning("FRED: Failed %s: %s", series_id, e)
            continue

    return results


def get_latest_fred(results: dict[str, list[dict]], series_id: str) -> Optional[float]:
    """Get the most recent value for a FRED series."""
    obs = results.get(series_id, [])
    return obs[0]["value"] if obs else None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Economic Calendar — Forex Factory JSON Feed (Points 1-6, 11, 12, 20-22, 29)
# ═══════════════════════════════════════════════════════════════════════════════

# Country code mapping from Forex Factory country names to our currency codes
FF_COUNTRY_MAP: dict[str, str] = {
    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "JPY": "JPY",
    "AUD": "AUD", "CAD": "CAD", "CHF": "CHF", "NZD": "NZD",
    "CNY": "CNY", "HKD": "HKD", "SGD": "SGD", "MXN": "MXN",
    "NOK": "NOK", "SEK": "SEK", "TRY": "TRY", "ZAR": "ZAR",
    "INR": "INR", "BRL": "BRL", "RUB": "RUB", "KRW": "KRW",
}

# High-impact event keywords to track for our 30 fundamental data points
HIGH_IMPACT_KEYWORDS = [
    "CPI", "GDP", "NFP", "PPI", "UNEMPLOYMENT", "FED", "BOE", "ECB",
    "INTEREST RATE", "INFLATION", "RETAIL SALES", "PMI", "MANUFACTURING",
    "SERVICES", "EMPLOYMENT CHANGE", "JOBLESS CLAIMS", "TRADE BALANCE",
    "INDUSTRIAL PRODUCTION", "CONSUMER CONFIDENCE", "BUILDING PERMITS",
    "HOUSING STARTS", "PCE", "WAGE", "EARNINGS", "GDP",
]


def fetch_forex_factory_calendar() -> list[dict]:
    """
    Fetch economic calendar events from Forex Factory's public JSON feed.
    URL: https://www.forexfactory.com/ff_calendar_thisweek.json
    Returns a list of normalized event dicts.
    """
    try:
        url = "https://www.forexfactory.com/ff_calendar_thisweek.json"
        # Use XHR-style browser headers to avoid Cloudflare 403 blocks
        ff_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.forexfactory.com/",
            "X-Requested-With": "XMLHttpRequest",
        }
        resp = requests.get(url, headers=ff_headers, timeout=30)
        resp.raise_for_status()
        raw_events = resp.json()

        if not isinstance(raw_events, list):
            logger.warning("Forex Factory: Unexpected response format (not a list).")
            return []

        events: list[dict] = []
        for ev in raw_events:
            try:
                # Extract fields from Forex Factory JSON structure
                title = ev.get("title", "") or ""
                country = ev.get("country", "") or ""
                date_str = ev.get("date", "") or ""
                forecast_raw = ev.get("forecast", "")
                previous_raw = ev.get("previous", "")
                actual_raw = ev.get("actual", "")
                impact = ev.get("impact", "low")

                # Map country to currency code
                currency = FF_COUNTRY_MAP.get(country.upper(), "")

                # Skip if no currency mapping or no event title
                if not currency or not title:
                    continue

                # Parse numeric values
                forecast = _safe_float(forecast_raw)
                previous = _safe_float(previous_raw)
                actual = _safe_float(actual_raw)

                # Normalize date: Forex Factory uses ISO format with timezone
                # e.g. "2026-07-18T12:30:00-04:00"
                event_date = date_str
                if event_date and "T" in event_date:
                    # Keep the full ISO string, frontend will format
                    pass

                events.append({
                    "source": "ForexFactory",
                    "date": event_date,
                    "currency": currency,
                    "event": title[:120],
                    "forecast": forecast,
                    "actual": actual,
                    "previous": previous,
                    "impact": impact.lower(),
                })

            except (KeyError, ValueError, TypeError) as e:
                logger.debug("Forex Factory: Skipping event row: %s", e)
                continue

        logger.info(
            "Forex Factory Calendar: %d events fetched (%d total raw).",
            len(events), len(raw_events),
        )
        return events

    except requests.RequestException as e:
        logger.warning("Forex Factory Calendar failed: %s", e)
        return []
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.warning("Forex Factory Calendar parse failed: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: AlphaVantage Economic Indicators (Points 7-10, 23, 24)
# ═══════════════════════════════════════════════════════════════════════════════

AV_BASE = "https://www.alphavantage.co/query"


def fetch_av_economic_indicator(function: str) -> Optional[dict]:
    """Fetch an economic indicator from AlphaVantage."""
    if not ALPHAVANTAGE_API_KEY:
        return None
    try:
        params = {
            "function": function,
            "apikey": ALPHAVANTAGE_API_KEY,
        }
        resp = requests.get(AV_BASE, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("AlphaVantage %s failed: %s", function, e)
        return None


def fetch_av_real_gdp() -> Optional[float]:
    """Fetch latest real GDP from AlphaVantage."""
    data = fetch_av_economic_indicator("REAL_GDP")
    if not data:
        return None
    try:
        for key in data:
            if "data" in key.lower():
                return float(data[key][-1]["value"])
    except (KeyError, IndexError, ValueError):
        pass
    return None


def fetch_av_cpi() -> Optional[float]:
    """Fetch latest CPI from AlphaVantage."""
    data = fetch_av_economic_indicator("CPI")
    if not data:
        return None
    try:
        for key in data:
            if "data" in key.lower():
                return float(data[key][-1]["value"])
    except (KeyError, IndexError, ValueError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: CFTC Commitments of Traders (Points 26, 28)
# ═══════════════════════════════════════════════════════════════════════════════

# CFTC data sources (probed in order):
#   CoT archive (newer format):     https://www.cftc.gov/files/dea/history/deacot{year}.zip
#   Legacy ZIP format:               https://www.cftc.gov/files/dea/history/deahist{year}.zip
#   Disaggregated TXT:               https://www.cftc.gov/dea/newtypes/deam{yy}.txt
CFTC_COT_URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
CFTC_DEAM_URL = "https://www.cftc.gov/dea/newtypes/deam{yy}.txt"
CFTC_BASE_URL = "https://www.cftc.gov/files/dea/history/deahist{year}.zip"

CFTC_TARGET_MARKETS: dict[str, str] = {
    "EURO CURRENCY":                "EUR",
    "BRITISH POUND STERLING":       "GBP",
    "JAPANESE YEN":                 "JPY",
    "CANADIAN DOLLAR":              "CAD",
    "SWISS FRANC":                  "CHF",
    "AUSTRALIAN DOLLAR":            "AUD",
    "MEXICAN PESO":                 "MXN",
    "NEW ZEALAND DOLLAR":           "NZD",
    "GOLD":                         "XAU",
    "SILVER":                       "XAG",
    "CRUDE OIL, LIGHT SWEET":       "WTI",
    "S&P 500 STOCK INDEX":          "SP500",
    "NASDAQ-100 STOCK INDEX MINI":  "NAS100",
    "E-MINI S&P 500":               "ES",
    "U.S. TREASURY BOND":           "USB",
    "10 YEAR U.S. TREASURY NOTE":   "UST10Y",
}

# Legacy report column names (used in deacot zips)
CFTC_COL_MARKET = "Market_and_Exchange_Names"
CFTC_COL_DATE = "Report_Date_as_MM_DD_YYYY"

# Disaggregated / TFF column names (used in com/fin zips)
CFTC_COL_ASST_MANAGER_LONG = "Asset_Mgr_Positions_Long_All"
CFTC_COL_ASST_MANAGER_SHORT = "Asset_Mgr_Positions_Short_All"
CFTC_COL_LEV_FUNDS_LONG = "Lev_Money_Positions_Long_All"
CFTC_COL_LEV_FUNDS_SHORT = "Lev_Money_Positions_Short_All"
CFTC_COL_NONCOMM_LONG = "Non_Commercial_Positions_Long_All"
CFTC_COL_NONCOMM_SHORT = "Non_Commercial_Positions_Short_All"

# Legacy report column names (used in deacot zips)
# deacot files use spaces and hyphens instead of underscores
CFTC_LEGACY_NONCOMM_LONG = "Noncommercial Positions-Long (All)"
CFTC_LEGACY_NONCOMM_SHORT = "Noncommercial Positions-Short (All)"
CFTC_LEGACY_COMM_LONG = "Commercial Positions-Long (All)"
CFTC_LEGACY_COMM_SHORT = "Commercial Positions-Short (All)"

# Column name aliases: maps multiple possible names to our standard keys
CFTC_COLUMN_ALIASES = {
    "noncomm_long": [
        "Non_Commercial_Positions_Long_All",
        "Noncommercial Positions-Long (All)",
        "Non Commercial Positions-Long (All)",
    ],
    "noncomm_short": [
        "Non_Commercial_Positions_Short_All",
        "Noncommercial Positions-Short (All)",
        "Non Commercial Positions-Short (All)",
    ],
    "asset_mgr_long": [
        "Asset_Mgr_Positions_Long_All",
        "Asset Manager Positions-Long (All)",
    ],
    "asset_mgr_short": [
        "Asset_Mgr_Positions_Short_All",
        "Asset Manager Positions-Short (All)",
    ],
    "lev_funds_long": [
        "Lev_Money_Positions_Long_All",
        "Leveraged Funds Positions-Long (All)",
    ],
    "lev_funds_short": [
        "Lev_Money_Positions_Short_All",
        "Leveraged Funds Positions-Short (All)",
    ],
}


def _resolve_cftc_column(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    """Find the first column name from aliases that exists in the DataFrame."""
    for alias in aliases:
        if alias in df.columns:
            return alias
    return None


def _download_cftc_zip(year: int) -> Optional[bytes]:
    """Download CFTC legacy ZIP for a given year."""
    url = CFTC_BASE_URL.format(year=year)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        logger.info("CFTC: Downloaded %s (%d bytes)", url, len(resp.content))
        return resp.content
    except requests.RequestException as e:
        logger.warning("CFTC: Failed %s: %s", url, e)
        return None


def _parse_cftc_zip(content: bytes) -> pd.DataFrame:
    """Extract CSV from CFTC ZIP archive into a DataFrame."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            csv_files = [n for n in zf.namelist() if n.endswith((".csv", ".txt"))]
            if not csv_files:
                logger.error("CFTC: No CSV/TXT in ZIP.")
                return pd.DataFrame()
            with zf.open(csv_files[0]) as f:
                raw = f.read()
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                return pd.read_csv(io.StringIO(text), low_memory=False)
    except Exception as e:
        logger.error("CFTC: ZIP parse failed: %s", e)
        return pd.DataFrame()


def _download_cftc_deam(yy: str) -> Optional[pd.DataFrame]:
    """Download CFTC disaggregated (DEAM) TXT file for a given two-digit year."""
    url = CFTC_DEAM_URL.format(yy=yy)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        logger.info("CFTC: Downloaded %s (%d bytes)", url, len(resp.content))
        text = resp.text
        # DEAM files are pipe-delimited or tab-delimited
        # Try pipe first, then tab, then comma
        for sep in ['|', '\t', ',']:
            try:
                df = pd.read_csv(io.StringIO(text), sep=sep, low_memory=False)
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
        return pd.read_csv(io.StringIO(text), low_memory=False)
    except requests.RequestException as e:
        logger.warning("CFTC: Failed DEAM %s: %s", url, e)
        return None


def _process_cftc_dataframe(df: pd.DataFrame) -> dict[str, dict]:
    """Process a CFTC DataFrame into the standard result format."""
    result: dict[str, dict] = {}

    df.columns = df.columns.str.strip()

    # Check required columns exist
    required = [CFTC_COL_MARKET, CFTC_COL_DATE]
    if not all(c in df.columns for c in required):
        logger.warning("CFTC: Missing required columns. Available: %s", list(df.columns))
        return result

    # Filter to target markets
    market_names = list(CFTC_TARGET_MARKETS.keys())
    df_filtered = df[
        df[CFTC_COL_MARKET].str.strip().str.upper().isin(
            [m.upper() for m in market_names]
        )
    ].copy()

    if df_filtered.empty:
        logger.warning("CFTC: No target markets found in data.")
        return result

    # Parse dates
    df_filtered.loc[:, CFTC_COL_DATE] = pd.to_datetime(
        df_filtered[CFTC_COL_DATE], format="%m/%d/%Y", errors="coerce"
    )
    df_filtered = df_filtered.dropna(subset=[CFTC_COL_DATE])

    # Resolve column names using aliases (supports both legacy and disaggregated formats)
    noncomm_long_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["noncomm_long"])
    noncomm_short_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["noncomm_short"])
    asset_mgr_long_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["asset_mgr_long"])
    asset_mgr_short_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["asset_mgr_short"])
    lev_funds_long_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["lev_funds_long"])
    lev_funds_short_col = _resolve_cftc_column(df_filtered, CFTC_COLUMN_ALIASES["lev_funds_short"])

    # Convert numeric columns using resolved names
    resolved_cols = [c for c in [noncomm_long_col, noncomm_short_col,
                                  asset_mgr_long_col, asset_mgr_short_col,
                                  lev_funds_long_col, lev_funds_short_col] if c]
    for col in resolved_cols:
        df_filtered.loc[:, col] = (
            pd.to_numeric(df_filtered[col], errors="coerce").fillna(0).astype(float)
        )

    # Compute net speculative
    if noncomm_long_col and noncomm_short_col:
        df_filtered.loc[:, "net_spec"] = (
            df_filtered[noncomm_long_col] - df_filtered[noncomm_short_col]
        )
    elif asset_mgr_long_col and asset_mgr_short_col:
        df_filtered.loc[:, "net_spec"] = (
            df_filtered[asset_mgr_long_col] - df_filtered[asset_mgr_short_col]
        )
    else:
        logger.warning("CFTC: No position columns found for net_spec. Columns: %s", list(df_filtered.columns))
        return result

    df_filtered = df_filtered.sort_values([CFTC_COL_MARKET, CFTC_COL_DATE])

    for market_name, short_code in CFTC_TARGET_MARKETS.items():
        market_df = df_filtered[
            df_filtered[CFTC_COL_MARKET].str.strip().str.upper() == market_name.upper()
        ].copy()

        if market_df.empty:
            continue

        # Weekly change
        market_df["weekly_change"] = market_df["net_spec"].diff().fillna(0.0)

        # 52-week percentile
        window = min(52, len(market_df))
        if window > 1:
            market_df["percentile_52w"] = (
                market_df["net_spec"]
                .rolling(window=window, min_periods=1)
                .apply(
                    lambda x: (
                        (x.iloc[-1] - x.min()) / (x.max() - x.min()) * 100
                        if x.max() != x.min()
                        else 50.0
                    ),
                    raw=False,
                )
            )
        else:
            market_df["percentile_52w"] = 50.0

        latest = market_df.iloc[-1]

        entry = {
            "report_date": latest[CFTC_COL_DATE].strftime("%Y-%m-%d"),
            "noncomm_long": float(latest.get(noncomm_long_col, 0)) if noncomm_long_col else 0,
            "noncomm_short": float(latest.get(noncomm_short_col, 0)) if noncomm_short_col else 0,
            "net_speculative": float(latest["net_spec"]),
            "weekly_change": float(latest["weekly_change"]),
            "percentile_52w": round(float(latest["percentile_52w"]), 2),
        }

        if asset_mgr_long_col and asset_mgr_short_col:
            entry["asset_mgr_long"] = float(latest[asset_mgr_long_col])
            entry["asset_mgr_short"] = float(latest[asset_mgr_short_col])
        if lev_funds_long_col and lev_funds_short_col:
            entry["lev_funds_long"] = float(latest[lev_funds_long_col])
            entry["lev_funds_short"] = float(latest[lev_funds_short_col])

        result[short_code] = entry
        logger.info(
            "CFTC: %s — Net: %.0f, Pctl: %.1f%%",
            short_code, entry["net_speculative"], entry["percentile_52w"],
        )

    return result


def _download_cftc_cot(year: int) -> Optional[pd.DataFrame]:
    """Download CFTC CoT archive ZIP for a given year (deacot format)."""
    url = CFTC_COT_URL.format(year=year)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        logger.info("CFTC: Downloaded %s (%d bytes)", url, len(resp.content))
        return _parse_cftc_zip(resp.content)
    except requests.RequestException as e:
        logger.warning("CFTC: Failed CoT %s: %s", url, e)
        return None


def fetch_cftc_data() -> dict[str, dict]:
    """
    Download and parse CFTC data with robust fallback chain:
    1. Try current year CoT archive (deacot{year}.zip)
    2. Try previous year CoT archive
    3. Try current year DEAM (disaggregated) TXT
    4. Try previous year DEAM TXT
    5. Try current year legacy ZIP (deahist)
    6. Try previous year legacy ZIP
    Returns structured dict per market.
    """
    result: dict[str, dict] = {}
    current_year = datetime.now().year
    yy = str(current_year)[-2:]  # "26" for 2026
    prev_yy = str(current_year - 1)[-2:]

    # Fallback chain
    sources = [
        ("CoT current", lambda: _download_cftc_cot(current_year)),
        ("CoT previous", lambda: _download_cftc_cot(current_year - 1)),
        ("DEAM current", lambda: _download_cftc_deam(yy)),
        ("DEAM previous", lambda: _download_cftc_deam(prev_yy)),
        ("ZIP current", lambda: _parse_cftc_zip(_download_cftc_zip(current_year)) if _download_cftc_zip(current_year) else pd.DataFrame()),
        ("ZIP previous", lambda: _parse_cftc_zip(_download_cftc_zip(current_year - 1)) if _download_cftc_zip(current_year - 1) else pd.DataFrame()),
        ("ZIP 2025", lambda: _parse_cftc_zip(_download_cftc_zip(2025)) if _download_cftc_zip(2025) else pd.DataFrame()),
    ]

    for source_name, source_fn in sources:
        try:
            df = source_fn()
            if df is None or df.empty:
                logger.info("CFTC: %s source returned empty, trying next.", source_name)
                continue

            result = _process_cftc_dataframe(df)
            if len(result) >= 5:
                logger.info("CFTC: Using %d markets from %s source.", len(result), source_name)
                return result
            elif result:
                logger.info("CFTC: %d markets from %s, trying next for more.", len(result), source_name)
            else:
                logger.info("CFTC: %s had no target markets.", source_name)
        except Exception as e:
            logger.warning("CFTC: %s failed: %s", source_name, e)
            continue

    logger.warning("CFTC: All sources exhausted. Returning %d markets.", len(result))
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Retail Sentiment (Point 27) — DailyFX Scraper
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_retail_sentiment() -> dict[str, dict]:
    """
    Scrape retail sentiment data from DailyFX.
    Returns {currency: {"long_pct": float, "short_pct": float}}.
    """
    result: dict[str, dict] = {}
    try:
        url = "https://www.dailyfx.com/sentiment"
        # Use full browser headers to avoid Cloudflare 403 blocks
        dfx_headers = dict(BROWSER_HEADERS)
        dfx_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        dfx_headers["Referer"] = "https://www.dailyfx.com/"
        resp = requests.get(url, headers=dfx_headers, timeout=30)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Look for sentiment data in script tags or tables
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string and "sentiment" in script.string.lower():
                # Try to extract JSON-like data
                matches = re.findall(
                    r'\{[^}]*"currency"[^}]*"long"[^}]*\}',
                    script.string
                )
                for match in matches:
                    try:
                        data = json.loads(match)
                        curr = data.get("currency", "")
                        if curr in TARGET_CURRENCIES:
                            result[curr] = {
                                "long_pct": float(data.get("long", 50)),
                                "short_pct": float(data.get("short", 50)),
                            }
                    except (json.JSONDecodeError, ValueError):
                        continue

        logger.info("Retail Sentiment: %d currencies parsed", len(result))
    except Exception as e:
        logger.warning("Retail Sentiment scrape failed: %s", e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7: Seasonality (Point 30) — yfinance 15-year monthly closes
# ═══════════════════════════════════════════════════════════════════════════════

SEASONALITY_TICKERS = {
    "DX-Y.NYB": "USD",   # Dollar Index
    "EURUSD=X": "EUR",
    "GBPUSD=X": "GBP",
    "JPY=X":    "JPY",
    "AUDUSD=X": "AUD",
    "USDCAD=X": "CAD",
    "USDCHF=X": "CHF",
    "GC=F":     "XAU",   # Gold
    "CL=F":     "WTI",   # Crude Oil
    "^GSPC":    "SP500", # S&P 500
    "BTC-USD":  "BTC",
    "ETH-USD":  "ETH",
}


def fetch_seasonality() -> dict[str, float]:
    """
    Calculate historical % of positive monthly closes for the current month
    using 15 years of data. Returns {asset: score_1_to_10}.
    Score: % positive mapped to 1-10 scale (5 = 50%).
    """
    result: dict[str, float] = {}
    current_month = datetime.now().month

    for ticker, asset in SEASONALITY_TICKERS.items():
        try:
            data = yf.download(ticker, period="15y", interval="1mo",
                               progress=False, auto_adjust=True)
            if data.empty:
                continue

            # Filter to current month only
            monthly = data[data.index.month == current_month].copy()
            if len(monthly) < 3:
                continue

            # Calculate monthly returns - handle MultiIndex columns
            close_col = monthly["Close"] if isinstance(monthly["Close"], pd.Series) else monthly["Close"].iloc[:, 0]
            monthly_returns = close_col.pct_change() * 100
            positive_months = (monthly_returns > 0).sum()
            total_months = len(monthly_returns.dropna())

            if total_months == 0:
                continue

            pct_positive = positive_months / total_months * 100

            # Map to 1-10 score: 0% = 1, 50% = 5, 100% = 10
            score = 1.0 + (pct_positive / 100.0) * 9.0
            result[asset] = round(max(1.0, min(10.0, score)), 2)

            logger.info(
                "Seasonality: %s (%s) — %.0f%% positive → %.1f",
                asset, ticker, pct_positive, result[asset],
            )

        except Exception as e:
            logger.warning("Seasonality failed for %s: %s", ticker, e)
            continue

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8: Central Bank Policy Rates (Points 13-19, 25)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_central_bank_rates() -> dict[str, float]:
    """
    Fetch official benchmark interest rates for major central banks.
    Uses FRED for Fed Funds, plus FMP for other central banks.
    Returns {currency_code: rate_percent}.
    """
    rates: dict[str, float] = {}

    # Fed Funds Rate from FRED
    fred_data = fetch_fred_series()
    fed_rate = get_latest_fred(fred_data, "FEDFUNDS")
    if fed_rate is not None:
        rates["USD"] = fed_rate

    # Other central bank rates from FMP
    if FMP_API_KEY:
        try:
            url = f"{FMP_BASE}/central_bank_rates"
            params = {"apikey": FMP_API_KEY}
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                for entry in data:
                    country = entry.get("country", "").upper()
                    rate = entry.get("rate")
                    if rate is not None:
                        try:
                            rate_val = float(rate)
                            currency_map = {
                                "EUROPEAN UNION": "EUR",
                                "UNITED KINGDOM": "GBP",
                                "JAPAN": "JPY",
                                "AUSTRALIA": "AUD",
                                "CANADA": "CAD",
                                "SWITZERLAND": "CHF",
                                "NEW ZEALAND": "NZD",
                            }
                            curr = currency_map.get(country)
                            if curr:
                                rates[curr] = rate_val
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            logger.warning("Central bank rates fetch failed: %s", e)

    logger.info("Central Bank Rates: %s", rates)
    return rates


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9: Yield Curve Data (Points 13-19 supplement)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_yield_curve() -> dict[str, dict]:
    """
    Fetch global bond yields via yfinance.
    Returns {instrument: {"yield": float, "ma50": float}}.
    """
    yield_tickers = {
        "^TNX":  "US10Y",
        "^GD10": "DE10Y",
        "^UMG":  "GB10Y",
        "^YT10": "JP10Y",
    }
    result: dict[str, dict] = {}

    for ticker, instrument in yield_tickers.items():
        try:
            bond = yf.Ticker(ticker)
            hist = bond.history(period="3mo")
            if hist.empty:
                continue

            latest_yield = float(hist["Close"].iloc[-1])
            ma50 = (
                float(hist["Close"].rolling(window=50).mean().iloc[-1])
                if len(hist) >= 50 else None
            )

            result[instrument] = {
                "yield": round(latest_yield, 4),
                "ma50": round(ma50, 4) if ma50 else None,
            }
            logger.info("Yield: %s = %.4f (MA50: %s)", instrument, latest_yield,
                        f"{ma50:.4f}" if ma50 else "N/A")
        except Exception as e:
            logger.warning("Yield fetch failed for %s: %s", ticker, e)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER COLLECTOR: Gather all 30 data points into one structured dict
# ═══════════════════════════════════════════════════════════════════════════════

def collect_all_data() -> dict[str, Any]:
    """
    Execute all data parsers and return a unified data dictionary
    for the scoring engine.
    """
    logger.info("=" * 60)
    logger.info("COLLECTING ALL 30 DATA POINTS")
    logger.info("=" * 60)

    data: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # FRED Macro Series (Points 7-10, 13-16, 23-24)
    logger.info("\n[1/8] FRED Macro Series...")
    data["fred"] = fetch_fred_series()

    # Economic Calendar — Forex Factory JSON Feed (Points 1-6, 11, 12, 20-22, 29)
    logger.info("\n[2/8] Economic Calendar (Forex Factory)...")
    data["forex_factory_calendar"] = fetch_forex_factory_calendar()

    # AlphaVantage Indicators (Points 7-10, 23, 24)
    logger.info("\n[4/8] AlphaVantage Indicators...")
    data["av_gdp"] = fetch_av_real_gdp()
    data["av_cpi"] = fetch_av_cpi()

    # CFTC Institutional Positioning (Points 26, 28)
    logger.info("\n[5/8] CFTC CoT Data...")
    data["cftc"] = fetch_cftc_data()

    # Retail Sentiment (Point 27)
    logger.info("\n[6/8] Retail Sentiment...")
    data["retail_sentiment"] = fetch_retail_sentiment()

    # Seasonality (Point 30)
    logger.info("\n[7/8] Seasonality...")
    data["seasonality"] = fetch_seasonality()

    # Central Bank Rates & Yields (Points 13-19, 25)
    logger.info("\n[8/8] Central Bank Rates & Yields...")
    data["central_bank_rates"] = fetch_central_bank_rates()
    data["yield_curve"] = fetch_yield_curve()

    logger.info("\n" + "=" * 60)
    logger.info("DATA COLLECTION COMPLETE")
    logger.info("=" * 60)

    return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    collected = collect_all_data()
    print(f"\nCollected {len(collected)} data categories.")
    for key, val in collected.items():
        if isinstance(val, dict):
            print(f"  {key}: {len(val)} items")
        elif isinstance(val, list):
            print(f"  {key}: {len(val)} entries")
        else:
            print(f"  {key}: {val}")