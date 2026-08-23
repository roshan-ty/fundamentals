#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals — Canonical Asset Configuration

This module is the SINGLE SOURCE OF TRUTH for the exact universe of
tradable assets. Any symbol not present in ALLOWED_ASSETS is STRIPPED
from all JSON generation pipelines and frontend views.

The asset universe is enforced in two layers:

  1. TRADING SYMBOLS  — the exact tickers used by brokers/feeds
     (e.g. "GOLD", "SILVER", "BTCUSD", "US100", "US500").

  2. ENGINE CODES     — the internal codes used by the scoring engine
     (e.g. "XAU", "XAG", "BTC", "NAS100", "SP500").

ASSET_CODE_MAP normalizes between the two layers so that the scoring
engine, parsers, news taggers, and frontend filters all reference the
exact same whitelist.

Synthetic or non-standard pairs (e.g. JPY/WTI, CAD/WTI, USD/NAS100,
JPY/NAS100) are excluded by construction: ALLOWED_PAIRS is generated
strictly from the symbols below.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# CANONICAL TRADED ASSET WHITELIST
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_ASSETS: dict[str, list[str]] = {
    # Commodities
    "COMMODITIES": ["BRENT", "COPPER", "OIL", "SILVER", "GOLD", "PALLADIUM", "PLATINUM"],

    # Crypto
    "CRYPTO": ["AVAXUSD", "BTCUSD", "ETHUSD", "LTCUSD", "SOLUSD", "SUIUSD", "XLMUSD", "XRPUSD"],

    # Forex Majors & Crosses
    "FOREX": [
        "AUDCAD", "AUDCHF", "AUDNZD", "AUDJPY", "CADCHF", "CADJPY", "CHFJPY",
        "EURAUD", "EURCAD", "EURCHF", "EURGBP", "EURHKD", "EURHUF", "EURJPY",
        "EURNOK", "EURNZD", "EURPLN", "EURSEK", "EURSGD", "EURTRY", "EURUSD", "EURZAR",
        "GBPAUD", "GBPCAD", "GBPCHF", "GBPHKD", "GBPHUF", "GBPJPY", "GBPNOK",
        "GBPNZD", "GBPPLN", "GBPSEK", "GBPTRY", "GBPUSD", "GBPZAR",
        "NZDCAD", "NZDCHF", "NZDJPY", "NZDSGD", "NZDUSD",
        "USDBRL", "USDCAD", "USDCHF", "USDCNY", "USDCZK", "USDDKK", "USDHUF",
        "USDJPY", "USDMXN", "USDNOK", "USDPLN", "USDSEK", "USDSGD",
    ],

    # Global Indices
    "INDICES": [
        "AUS200", "CH20", "ES35", "EU50", "FR40", "GB100", "GE40", "HK50", "JP225",
        "US100", "US30", "US500",
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# CURRENCY ASSIGNMENT — maps each currency symbol to its economic data key.
# KEY = currency / asset symbol, VALUE = economic region key used by parsers
# and the differential-scoring engine (e.g. "FED" for US, "ECB" for Eurozone).
# ═══════════════════════════════════════════════════════════════════════════════

CURRENCY_ASSIGNMENT: dict[str, str] = {
    # Forex Majors
    "USD": "FED",    # Federal Reserve / United States
    "EUR": "ECB",    # European Central Bank
    "GBP": "BOE",    # Bank of England
    "JPY": "BOJ",    # Bank of Japan
    "AUD": "RBA",    # Reserve Bank of Australia
    "CAD": "BOC",    # Bank of Canada
    "CHF": "SNB",    # Swiss National Bank
    "NZD": "RBNZ",   # Reserve Bank of New Zealand

    # Forex Crosses / Emerging & Secondary
    "HKD": "HKMA",   # Hong Kong Monetary Authority
    "HUF": "MNB",    # Hungarian National Bank
    "NOK": "NB",     # Norges Bank
    "PLN": "NBP",    # National Bank of Poland
    "SEK": "RIKSBANK",  # Sveriges Riksbank
    "SGD": "MAS",    # Monetary Authority of Singapore
    "TRY": "CBRT",   # Central Bank of Turkey
    "ZAR": "SARB",   # South African Reserve Bank
    "BRL": "BACEN",  # Central Bank of Brazil
    "CNY": "PBC",    # People's Bank of China
    "CZK": "CNB",    # Czech National Bank
    "DKK": "DN",     # Danmarks Nationalbank
    "MXN": "BANXICO" # Bank of Mexico
}

# ═══════════════════════════════════════════════════════════════════════════════
# ENGINE CODE NORMALIZATION
# Maps broker/feed trading symbols to the compact codes used internally by the
# scoring engine and parsers. Symbols not listed here retain their own name.
# ═══════════════════════════════════════════════════════════════════════════════

ASSET_CODE_MAP: dict[str, str] = {
    # Commodities → engine codes
    "BRENT":    "BRENT",
    "COPPER":   "COPPER",
    "OIL":      "WTI",
    "SILVER":   "XAG",
    "GOLD":     "XAU",
    "PALLADIUM": "PALLADIUM",
    "PLATINUM": "PLATINUM",

    # Crypto → engine codes
    "AVAXUSD":  "AVAX",
    "BTCUSD":   "BTC",
    "ETHUSD":   "ETH",
    "LTCUSD":   "LTC",
    "SOLUSD":   "SOL",
    "SUIUSD":   "SUI",
    "XLMUSD":   "XLM",
    "XRPUSD":   "XRP",

    # Global Indices → engine codes
    "AUS200":   "AUS200",
    "CH20":     "CH20",
    "ES35":     "ES35",
    "EU50":     "EU50",
    "FR40":     "FR40",
    "GB100":    "GB100",
    "GE40":     "GE40",
    "HK50":     "HK50",
    "JP225":    "JP225",
    "US100":    "NAS100",
    "US30":     "US30",
    "US500":    "SP500",
}

# ═══════════════════════════════════════════════════════════════════════════════
# DERIVED ENGINE LISTS
# ═══════════════════════════════════════════════════════════════════════════════

def _all_trading_symbols() -> list[str]:
    """Flatten ALLOWED_ASSETS into a single deduplicated symbol list."""
    seen: list[str] = []
    for asset_class in ("COMMODITIES", "CRYPTO", "FOREX", "INDICES"):
        for symbol in ALLOWED_ASSETS.get(asset_class, []):
            if symbol not in seen:
                seen.append(symbol)
    return seen


def _all_engine_codes() -> list[str]:
    """Map every allowed trading symbol to its engine code (deduplicated)."""
    seen: list[str] = []
    for symbol in _all_trading_symbols():
        code = ASSET_CODE_MAP.get(symbol, symbol)
        if code not in seen:
            seen.append(code)
    return seen


# Every allowed trading symbol, in stable class order
ALL_TRADING_SYMBOLS: list[str] = _all_trading_symbols()

# Every allowed engine base-asset code, deduplicated and stable
ALLOWED_BASE_ASSETS: list[str] = _all_engine_codes()

# Mapping from class name to engine codes for that class
ALLOWED_ENGINE_CLASSES: dict[str, list[str]] = {
    asset_class: [ASSET_CODE_MAP.get(s, s) for s in ALLOWED_ASSETS[asset_class]]
    for asset_class in ALLOWED_ASSETS
}

# All valid pairs (base_code, quote_code) derived strictly from the whitelist.
# Synthetic pairs (e.g. JPY/WTI, CAD/WTI, USD/NAS100, JPY/NAS100) are
# excluded by construction because they cross non-whitelisted symbols.
ALLOWED_PAIRS: list[tuple[str, str]] = [
    (base, quote)
    for base in ALLOWED_BASE_ASSETS
    for quote in ALLOWED_BASE_ASSETS
    if base != quote
]


def is_allowed(symbol: str) -> bool:
    """Return True if the trading symbol is in the canonical whitelist."""
    return symbol in _all_trading_symbols()


def is_allowed_code(code: str) -> bool:
    """Return True if the engine code belongs to an allowed asset."""
    return code in _all_engine_codes()


def is_allowed_pair(base: str, quote: str) -> bool:
    """Return True if (base, quote) is a valid whitelisted pair."""
    return is_allowed_code(base) and is_allowed_code(quote) and base != quote


def symbol_to_code(symbol: str) -> str:
    """Convert a trading symbol to its engine code."""
    return ASSET_CODE_MAP.get(symbol, symbol)


# ═══════════════════════════════════════════════════════════════════════════════
# DISTINCT CURRENCIES — derived from the whitelist FOREX pairs.
# Used by the scoring engine to compute country-level fundamental scores.
# ═══════════════════════════════════════════════════════════════════════════════

def _derive_currencies() -> list[str]:
    """Extract the distinct base/quote currencies from every whitelisted FX pair."""
    seen: list[str] = []
    for symbol in ALLOWED_ASSETS.get("FOREX", []):
        if len(symbol) == 6:  # e.g. AUDCAD → AUD, CAD
            for cc in (symbol[:3], symbol[3:]):
                if cc not in seen:
                    seen.append(cc)
    return seen


# Every distinct currency present in the whitelisted FOREX universe
DISTINCT_CURRENCIES: list[str] = _derive_currencies()

# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY PAIR SPECS — the exact pair universe derived from ALLOWED_ASSETS.
# Synthetic pairs (JPY/WTI, CAD/WTI, USD/NAS100, JPY/NAS100, ...) cannot
# appear because the spec is generated strictly from the whitelist.
# ═══════════════════════════════════════════════════════════════════════════════

# Home currency used to quote each whitelisted global index.
INDEX_HOME_CURRENCY: dict[str, str] = {
    "AUS200": "AUD",
    "CH20":   "CHF",
    "ES35":   "EUR",
    "EU50":   "EUR",
    "FR40":   "EUR",
    "GB100":  "GBP",
    "GE40":   "EUR",
    "HK50":   "HKD",
    "JP225":  "JPY",
    "US100":  "USD",
    "US30":   "USD",
    "US500":  "USD",
}

# Precious metals / industrial commodities (quoted in USD)
_COMMODITY_METALS = {"XAU", "XAG", "COPPER", "PALLADIUM", "PLATINUM"}
_COMMODITY_ENERGY = {"WTI", "BRENT"}


def allowed_pair_specs() -> list[dict]:
    """
    Build the exact display-pair list from the canonical whitelist.

    Returns a list of dicts:
        {"name", "base", "quote", "asset_class"}

    Rules:
      - FOREX 6-char symbols → base = first 3 codes, quote = last 3
      - CRYPTO "XXXUSD"      → base = engine code, quote = USD
      - COMMODITIES          → quoted in USD
      - INDICES              → quoted in their home currency
    """
    specs: list[dict] = []

    # Forex pairs
    for symbol in ALLOWED_ASSETS.get("FOREX", []):
        if len(symbol) == 6:
            base, quote = symbol[:3], symbol[3:]
            specs.append({
                "name": f"{base}/{quote}",
                "base": base,
                "quote": quote,
                "asset_class": "FX",
            })

    # Crypto pairs (XXXUSD → XXX/USD)
    for symbol in ALLOWED_ASSETS.get("CRYPTO", []):
        base = symbol_to_code(symbol)
        specs.append({
            "name": f"{base}/USD",
            "base": base,
            "quote": "USD",
            "asset_class": "CRYPTO",
        })

    # Commodities (quoted in USD)
    for symbol in ALLOWED_ASSETS.get("COMMODITIES", []):
        base = symbol_to_code(symbol)
        asset_class = ("METAL" if base in _COMMODITY_METALS
                       else "ENERGY" if base in _COMMODITY_ENERGY
                       else "COMMODITY")
        specs.append({
            "name": f"{base}/USD",
            "base": base,
            "quote": "USD",
            "asset_class": asset_class,
        })

    # Global indices (quoted in home currency)
    for symbol in ALLOWED_ASSETS.get("INDICES", []):
        base = symbol_to_code(symbol)
        quote = INDEX_HOME_CURRENCY.get(symbol, "USD")
        specs.append({
            "name": f"{base}/{quote}",
            "base": base,
            "quote": quote,
            "asset_class": "INDEX",
        })

    return specs


# The exact pair universe presented to the frontend / downstream tools
ALLOWED_DISPLAY_PAIRS: list[dict] = allowed_pair_specs()


# ═══════════════════════════════════════════════════════════════════════════════
# SELF-TEST / VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    counts = {cls: len(symbols) for cls, symbols in ALLOWED_ASSETS.items()}
    print(f"Canonical asset whitelist loaded successfully.")
    print(f"Classes: {', '.join(counts.keys())}")
    for cls, count in counts.items():
        print(f"  {cls}: {count} symbols")
    print(f"Total trading symbols: {len(ALL_TRADING_SYMBOLS)}")
    print(f"Total engine codes: {len(ALLOWED_BASE_ASSETS)}")
    print(f"Total allowed pairs: {len(ALLOWED_PAIRS)}")
    print(f"Currency assignments: {len(CURRENCY_ASSIGNMENT)}")

    # Sanity checks
    assert len(ALL_TRADING_SYMBOLS) == 80, f"Expected 80 symbols, got {len(ALL_TRADING_SYMBOLS)}"
    assert len(ALLOWED_ASSETS["COMMODITIES"]) == 7
    assert len(ALLOWED_ASSETS["CRYPTO"]) == 8
    assert len(ALLOWED_ASSETS["FOREX"]) == 53
    assert len(ALLOWED_ASSETS["INDICES"]) == 12
    assert len(DISTINCT_CURRENCIES) == 21, f"Expected 21 distinct currencies, got {len(DISTINCT_CURRENCIES)}"
    assert len(ALLOWED_DISPLAY_PAIRS) == 80, f"Expected 80 display pairs, got {len(ALLOWED_DISPLAY_PAIRS)}"
    assert "XAU" in ALLOWED_BASE_ASSETS
    assert "XAG" in ALLOWED_BASE_ASSETS
    assert "BTC" in ALLOWED_BASE_ASSETS
    assert "NAS100" in ALLOWED_BASE_ASSETS
    assert "SP500" in ALLOWED_BASE_ASSETS
    assert "WTI" in ALLOWED_BASE_ASSETS  # OIL → WTI engine code
    assert not is_allowed_pair("JPY", "WTI")
    assert not is_allowed_pair("CAD", "WTI")
    assert not is_allowed_pair("USD", "NAS100")
    assert not is_allowed_pair("JPY", "NAS100")
    assert not any("NAS100" in p["name"] and "USD" in p["name"] for p in ALLOWED_DISPLAY_PAIRS if p["base"] == "USD")
    print("\nAll assertions passed — whitelist is clean.")
