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
# SECTION 2: Economic Calendar — DailyFX API (Points 1-6, 11, 12, 20-22, 29)
# ═══════════════════════════════════════════════════════════════════════════════

# Currency code mapping (DailyFX uses standard ISO codes)
DAILYFX_CURRENCY_MAP: dict[str, str] = {
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


def fetch_dailyfx_calendar() -> list[dict]:
    """
    Fetch economic calendar events from DailyFX's public API endpoint.
    URL: https://content.dailyfx.com/api/v1/calendar
    This API is openly accessible (no Cloudflare blocks) and returns
    structured JSON with forecast, actual, previous, and impact data.
    Returns a list of normalized event dicts.
    """
    try:
        url = "https://content.dailyfx.com/api/v1/calendar"
        now = datetime.utcnow()
        # Current week start (Monday) to 7 days ahead
        start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%dT00:00:00Z")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%dT23:59:59Z")
        params = {"start": start, "end": end}
        headers = {
            "User-Agent": BROWSER_HEADERS["User-Agent"],
            "Accept": "application/json",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        events: list[dict] = []
        # DailyFX returns an array of event objects, or wrapped in a key
        raw_events = data if isinstance(data, list) else data.get("calendar", data.get("events", []))

        for item in raw_events:
            try:
                title = item.get("title") or item.get("event") or item.get("name", "")
                currency = item.get("currency", "")
                date_str = item.get("dateTime") or item.get("date", "")
                impact = item.get("impact", "low") or "low"
                forecast = item.get("forecast")
                actual = item.get("actual")
                previous = item.get("previous")

                if not title or not currency:
                    continue

                # Normalize currency code
                currency = currency.strip().upper()
                if currency not in DAILYFX_CURRENCY_MAP:
                    continue

                # Parse date to ISO format
                event_date = date_str
                if date_str:
                    try:
                        # Try ISO format first
                        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        event_date = parsed.isoformat()
                    except (ValueError, TypeError):
                        try:
                            parsed = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
                            event_date = parsed.isoformat()
                        except (ValueError, TypeError):
                            pass  # Keep raw string

                events.append({
                    "source": "DailyFX",
                    "date": event_date,
                    "currency": currency,
                    "event": str(title)[:120],
                    "forecast": _safe_float(forecast),
                    "actual": _safe_float(actual),
                    "previous": _safe_float(previous),
                    "impact": impact.lower(),
                })

            except (KeyError, ValueError, TypeError, AttributeError) as e:
                logger.debug("DailyFX Calendar: Skipping event row: %s", e)
                continue

        logger.info(
            "DailyFX Calendar: %d events fetched.",
            len(events),
        )
        return events

    except requests.RequestException as e:
        logger.warning("DailyFX Calendar failed: %s", e)
        return []
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        logger.warning("DailyFX Calendar parse failed: %s", e)
        return []


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, returning None if not possible."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.strip().replace(",", "").replace("%", "").replace("$", "").replace("€", "").replace("£", "")
        if val in ("", "-", "N/A", ".", "--"):
            return None
        try:
            return float(val)
        except ValueError:
            return None
    return None


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
    "EURO FX":                      "EUR",
    "BRITISH POUND":                "GBP",
    "JAPANESE YEN":                 "JPY",
    "CANADIAN DOLLAR":              "CAD",
    "SWISS FRANC":                  "CHF",
    "AUSTRALIAN DOLLAR":            "AUD",
    "MEXICAN PESO":                 "MXN",
    "NZ DOLLAR":                    "NZD",
    "GOLD":                         "XAU",
    "SILVER":                       "XAG",
    "WTI CRUDE OIL":                "WTI",
    "E-MINI S&P 500":               "SP500",
    "NASDAQ-100":                   "NAS100",
    "U.S. TREASURY BOND":           "USB",
    "10 YEAR U.S. TREASURY NOTE":   "UST10Y",
}

# Column name aliases for the Market column (deacot uses spaces, legacy uses underscores)
# Deacot format: 'Market and Exchange Names'
# Legacy format: 'Market_and_Exchange_Names'
CFTC_MARKET_COL_ALIASES = [
    "Market_and_Exchange_Names",
    "Market and Exchange Names",
]

# Column name aliases for the Date column
# Deacot format: 'As of Date in Form YYYY-MM-DD'
# Legacy format: 'Report_Date_as_MM_DD_YYYY'
CFTC_DATE_COL_ALIASES = [
    "Report_Date_as_MM_DD_YYYY",
    "As of Date in Form YYYY-MM-DD",
    "As of Date in Form YYMMDD",
]

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
                return pd.read_csv(io.StringIO(text), low_memory=False, dtype=str)
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

    # Resolve market and date columns using aliases
    market_col = _resolve_cftc_column(df, CFTC_MARKET_COL_ALIASES)
    date_col = _resolve_cftc_column(df, CFTC_DATE_COL_ALIASES)

    if not market_col or not date_col:
        logger.warning("CFTC: Missing market/date columns. Available: %s", list(df.columns))
        return result

    # Reset index to avoid issues with auto-parsed datetime index
    df = df.reset_index(drop=True)

    # Defensively ensure market column is string type for text processing
    df[market_col] = df[market_col].astype(str).str.strip()

    # Debug: log sample market names to understand the actual format
    sample_markets = df[market_col].dropna().unique()[:10]
    logger.info("CFTC: Sample market names from file: %s", sample_markets)

    # Filter to target markets using a single combined case-insensitive regex
    # This handles suffixes like "EURO FX - CHICAGO MERCANTILE EXCHANGE"
    market_pattern = '|'.join(re.escape(m) for m in CFTC_TARGET_MARKETS.keys())
    mask = df[market_col].str.contains(market_pattern, case=False, na=False, regex=True)
    df_filtered = df[mask].copy().reset_index(drop=True)

    if df_filtered.empty:
        logger.warning("CFTC: No target markets found in data. All sample markets: %s", sample_markets)
        return result

    # Force date column to string first to prevent DatetimeArray type clashes
    df_filtered.loc[:, date_col] = df_filtered[date_col].astype(str)

    # Ensure date column is datetime - convert at the start before filtering
    if not pd.api.types.is_datetime64_any_dtype(df_filtered[date_col]):
        df_filtered.loc[:, date_col] = pd.to_datetime(
            df_filtered[date_col], errors="coerce"
        )
    df_filtered = df_filtered.dropna(subset=[date_col])

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

    df_filtered = df_filtered.sort_values([market_col, date_col])

    for market_name, short_code in CFTC_TARGET_MARKETS.items():
        market_df = df_filtered[
            df_filtered[market_col].astype(str).str.strip().str.contains(
                market_name, case=False, na=False, regex=False
            )
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

        # Use resolved date_col name for entry
        report_date_val = latest[date_col]
        if hasattr(report_date_val, 'strftime'):
            report_date_str = report_date_val.strftime("%Y-%m-%d")
        else:
            report_date_str = str(report_date_val)[:10]
        entry = {
            "report_date": report_date_str,
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
            if result:
                logger.info("CFTC: Using %d markets from %s source (stopping chain).", len(result), source_name)
                return result
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

# Fallback central bank rates when API is unavailable (updated periodically)
# These are approximate current policy rates as of July 2026
FALLBACK_CENTRAL_BANK_RATES: dict[str, float] = {
    "EUR": 4.25,   # ECB
    "GBP": 5.25,   # Bank of England
    "JPY": 0.50,   # Bank of Japan
    "AUD": 4.35,   # Reserve Bank of Australia
    "CAD": 5.00,   # Bank of Canada
    "CHF": 1.75,   # Swiss National Bank
    "NZD": 5.50,   # Reserve Bank of New Zealand
}


def fetch_central_bank_rates() -> dict[str, float]:
    """
    Fetch official benchmark interest rates for major central banks.
    Uses FRED for Fed Funds, plus FMP for other central banks.
    Falls back to hardcoded approximate rates if API fails.
    Returns {currency_code: rate_percent}.
    """
    rates: dict[str, float] = {}

    # Fed Funds Rate from FRED (always reliable)
    fred_data = fetch_fred_series()
    fed_rate = get_latest_fred(fred_data, "FEDFUNDS")
    if fed_rate is not None:
        rates["USD"] = fed_rate
    else:
        rates["USD"] = 5.50  # Fallback if FRED fails

    # Other central bank rates from FMP — bail out cleanly if key is missing
    api_succeeded = False
    if not FMP_API_KEY:
        logger.info("Central bank rates: FMP_API_KEY not set, skipping FMP extraction.")
    else:
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
                                api_succeeded = True
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            logger.warning("Central bank rates API failed: %s", e)

    # Fallback to hardcoded rates for any missing currencies
    if not api_succeeded:
        logger.info("Central bank rates: Using fallback rates (API unavailable)")
        for currency, rate in FALLBACK_CENTRAL_BANK_RATES.items():
            if currency not in rates:
                rates[currency] = rate
    else:
        # Fill in any gaps the API didn't cover
        for currency, rate in FALLBACK_CENTRAL_BANK_RATES.items():
            if currency not in rates:
                rates[currency] = rate
                logger.info("Central bank rates: Filled %s with fallback %.2f", currency, rate)

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
        "^TNX":  "US10Y",   # US 10-Year Treasury Note yield
        "^TYX":  "US30Y",   # US 30-Year Treasury Bond yield (replaces delisted ^GD10)
        "^IRX":  "US13W",   # US 13-Week Treasury Bill (short end of curve)
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

    # Economic Calendar — DailyFX API (Points 1-6, 11, 12, 20-22, 29)
    logger.info("\n[2/8] Economic Calendar (DailyFX)...")
    data["forex_factory_calendar"] = fetch_dailyfx_calendar()

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