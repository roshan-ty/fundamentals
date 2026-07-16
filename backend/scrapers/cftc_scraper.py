"""
Pipeline B: CFTC Commitments of Traders (CoT) — Download legacy ZIP archives,
parse CSV, extract non-commercial positions, compute net speculative positions
and 52-week percentile ranks.
"""

import os
import io
import logging
import zipfile
from datetime import datetime, date, timezone
from typing import Optional

import pandas as pd
import numpy as np
import requests

from backend.models.schemas import CftcPosition, CftcData

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

CFTC_BASE_URL = "https://www.cftc.gov/files/dea/history/deahist{year}.zip"

# Market names as they appear in the CFTC legacy format
TARGET_MARKETS: dict[str, str] = {
    "EURO CURRENCY":                "EUR",
    "BRITISH POUND STERLING":       "GBP",
    "JAPANESE YEN":                 "JPY",
    "CANADIAN DOLLAR":              "CAD",
    "SWISS FRANC":                  "CHF",
    "AUSTRALIAN DOLLAR":            "AUD",
    "GOLD":                         "XAU",
    "SILVER":                       "XAG",
    "CRUDE OIL, LIGHT SWEET":       "WTI",
    "S&P 500 STOCK INDEX":          "SP500",
    "NASDAQ-100 STOCK INDEX MINI":  "NAS100",
}

# Column names in the legacy CFTC CSV
COL_MARKET = "Market_and_Exchange_Names"
COL_DATE = "Report_Date_as_MM_DD_YYYY"
COL_NONCOMM_LONG = "Non_Commercial_Positions_Long_All"
COL_NONCOMM_SHORT = "Non_Commercial_Positions_Short_All"


# ── Main scraper ──────────────────────────────────────────────────────────────

def _download_zip(year: int) -> Optional[bytes]:
    """Download the CFTC legacy ZIP for the given year."""
    url = CFTC_BASE_URL.format(year=year)
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        logger.info("CFTC: Downloaded %s (%d bytes)", url, len(resp.content))
        return resp.content
    except requests.RequestException as e:
        logger.warning("CFTC: Failed to download %s: %s", url, e)
        return None


def _parse_cftc_csv(content: bytes) -> pd.DataFrame:
    """
    Extract and parse the CSV file from the ZIP archive.
    The legacy ZIP contains a single .txt or .csv file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Find the first CSV/TXT file
            csv_files = [n for n in zf.namelist() if n.endswith((".csv", ".txt"))]
            if not csv_files:
                logger.error("CFTC: No CSV/TXT found in ZIP archive.")
                return pd.DataFrame()
            csv_name = csv_files[0]
            logger.info("CFTC: Extracting %s from archive", csv_name)
            with zf.open(csv_name) as f:
                # Read raw bytes, decode, parse
                raw = f.read()
                # Try UTF-8, fallback to latin-1
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                # Parse with pandas
                df = pd.read_csv(io.StringIO(text), low_memory=False)
                return df
    except (zipfile.BadZipFile, KeyError, Exception) as e:
        logger.error("CFTC: Failed to parse ZIP: %s", e)
        return pd.DataFrame()


def _filter_and_process(df: pd.DataFrame) -> list[CftcPosition]:
    """
    Filter for target markets, compute net speculative positions,
    and calculate 52-week percentile ranks.
    """
    if df.empty:
        return []

    # Normalize column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Check required columns exist
    required = [COL_MARKET, COL_DATE, COL_NONCOMM_LONG, COL_NONCOMM_SHORT]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logger.error("CFTC: Missing columns: %s. Available: %s", missing, list(df.columns))
        return []

    # Filter to target markets
    market_names = list(TARGET_MARKETS.keys())
    df_filtered = df[df[COL_MARKET].str.strip().str.upper().isin(
        [m.upper() for m in market_names]
    )].copy()

    if df_filtered.empty:
        logger.warning("CFTC: No target markets found in data.")
        return []

    # Parse date column
    df_filtered[COL_DATE] = pd.to_datetime(
        df_filtered[COL_DATE], format="%m/%d/%Y", errors="coerce"
    )
    df_filtered = df_filtered.dropna(subset=[COL_DATE])

    # Convert position columns to numeric
    for col in [COL_NONCOMM_LONG, COL_NONCOMM_SHORT]:
        df_filtered[col] = (
            pd.to_numeric(df_filtered[col], errors="coerce").fillna(0).astype(float)
        )

    # Compute net speculative position
    df_filtered["net_spec"] = (
        df_filtered[COL_NONCOMM_LONG] - df_filtered[COL_NONCOMM_SHORT]
    )

    # Sort by market and date
    df_filtered = df_filtered.sort_values([COL_MARKET, COL_DATE])

    # Compute weekly change and 52-week percentile per market
    positions: list[CftcPosition] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for market_name, short_code in TARGET_MARKETS.items():
        market_df = df_filtered[
            df_filtered[COL_MARKET].str.strip().str.upper() == market_name.upper()
        ].copy()

        if market_df.empty:
            continue

        # Weekly change
        market_df["weekly_change"] = market_df["net_spec"].diff().fillna(0.0)

        # 52-week percentile (rolling window of up to 52 weeks)
        # Use all available data if less than 52 weeks
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

        # Get the latest row
        latest = market_df.iloc[-1]

        positions.append(
            CftcPosition(
                market=short_code,
                report_date=latest[COL_DATE].strftime("%Y-%m-%d"),
                noncomm_long=float(latest[COL_NONCOMM_LONG]),
                noncomm_short=float(latest[COL_NONCOMM_SHORT]),
                net_speculative=float(latest["net_spec"]),
                weekly_change=float(latest["weekly_change"]),
                percentile_52w=round(float(latest["percentile_52w"]), 2),
                last_updated=now_iso,
            )
        )

        logger.info(
            "CFTC: %s — Net: %.0f, Percentile: %.1f%%",
            short_code,
            latest["net_spec"],
            latest["percentile_52w"],
        )

    return positions


def fetch_cftc_data() -> CftcData:
    """
    Main entry point: download current year's CFTC data, parse, and return.
    Falls back to previous year if current year fails, and tries the
    comprehensive 'deahist2025.zip' as a final fallback for 52-week history.
    """
    cftc_data = CftcData()
    cftc_data.last_updated = datetime.now(timezone.utc).isoformat()

    current_year = date.today().year
    # Try current year first, then previous, then explicit comprehensive fallback
    years_to_try = [current_year, current_year - 1]
    # Always add 2025 as comprehensive fallback (has full 52+ weeks of data)
    if 2025 not in years_to_try:
        years_to_try.append(2025)

    for year in years_to_try:
        zip_content = _download_zip(year)
        if zip_content is None:
            continue

        df = _parse_cftc_csv(zip_content)
        if df.empty:
            logger.warning("CFTC: Parsed empty DataFrame from %d archive.", year)
            continue

        positions = _filter_and_process(df)

        # Accept data only if we have at least 5 of the 11 target markets
        if len(positions) >= 5:
            cftc_data.positions = positions
            logger.info(
                "CFTC: Using %d markets from %d data (found %d total).",
                len(positions), year, len(positions),
            )
            return cftc_data
        elif positions:
            logger.warning(
                "CFTC: Only %d/%d markets found in %d — trying earlier archive.",
                len(positions), len(TARGET_MARKETS), year,
            )
        else:
            logger.warning("CFTC: No target markets found in %d archive.", year)

    logger.error("CFTC: Failed to fetch sufficient data for any year.")
    return cftc_data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = fetch_cftc_data()
    print(f"CFTC: {len(data.positions)} markets processed.")
    for p in data.positions:
        print(f"  {p.market}: Net={p.net_speculative:.0f}, Pctl={p.percentile_52w:.1f}%")