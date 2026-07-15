# Bulls & Bears fundamentals

A high-end, lightweight, data-dense **fundamental analysis screener** for FX, Indices, Metals, and Energy.  
Built with a serverless static architecture — runs 24/7 on GitHub Pages with automated data pipelines via GitHub Actions.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              GitHub Actions (CRON every 4h)             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  backend/main.py  (Python Orchestrator)          │   │
│  │  ├── fred_scraper.py    → FRED API               │   │
│  │  ├── cftc_scraper.py    → CFTC ZIP → pandas      │   │
│  │  ├── yield_scraper.py   → AlphaVantage + yfinance │   │
│  │  ├── calendar_scraper.py → EODHD API             │   │
│  │  ├── news_scraper.py    → Newsdata.io API        │   │
│  │  ├── macro_score.py     → GDP/UE → 0-10          │   │
│  │  ├── event_surprise.py  → Surprise Ratio → 0-10  │   │
│  │  ├── yield_score.py     → Yield vs MA50 → 0-10   │   │
│  │  ├── cftc_sentiment.py  → Percentile Rank → 0-10 │   │
│  │  ├── pair_math.py       → 200+ Pairs + Setups    │   │
│  │  └── json_exporter.py   → data/*.json             │   │
│  └──────────────────────────────────────────────────┘   │
│                         ↓                                │
│              Commits JSON to repository                  │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│   GitHub Pages (Static Hosting — Root Level)             │
│   ├── index.html   → Bootstrap 5 SPA Shell              │
│   ├── styles.css   → Light/Dark theme (pitch-black)     │
│   ├── charts.js    → Chart.js configurations            │
│   ├── app.js       → Tab SPA Controller + Data Fetcher  │
│   └── data/        → Auto-generated JSON databases      │
└─────────────────────────────────────────────────────────┘
```

## Features

### 6-Tab Single-Page Interface
1. **Home** — USD Fundamental Health Dashboard with NFP, GDP, CPI, Fed Funds Rate + Tradersyard CTA (code: ROSHAN)
2. **BIAS Grid** — Interactive table of 200+ currency pairs, metals, energy, and indices with click-to-expand breakdown
3. **Federal Reserve** — FRED historical charts (GDP, CPI, PCE, UNRATE, FEDFUNDS)
4. **CFTC CoT** — Speculative positioning with 52-week percentile ranks
5. **Trade Setups** — High-probability setups filtered for extreme bias scores (≥8.0 or ≤2.0)
6. **News Feed** — Scrolling global financial headlines (cosmetic only)

### Scoring Model (0–10 per currency)
| Component | Source | Logic |
|---|---|---|
| **Macro Score** | FRED (GDP + UE) | GDP↑ + UE↓ = 8–10; stagnant = 5; recession = 0–2 |
| **Event Surprise** | EODHD Calendar | Cumulative Surprise Ratio → 0–10 |
| **Yield Momentum** | 10Y vs 50-MA | Yields↑ = 8–10; flat = 5; yields↓ = 0–2 |
| **CFTC Sentiment** | 52W Percentile | 75–90% = 8–10; 40–60% = 5; <5% or >95% = capped |

**Overcrowded Trade Rule**: Percentile >95% or <5% → cap score near 5.

### Pair Calculation
- **FX**: `Combined Bias = 5 + (Base Avg − Quote Avg)` [clamped 0–10]
- **Gold/Silver**: `Metal Bias = 10 − USD Yield Score`
- **Crude Oil**: `Oil Bias = GDP Trend − (0.5 × USD Strength)`
- **Indices**: `Equity Bias = GDP Score − (0.7 × Bond Yield Score)`

### Scale Interpretation
| Score | Direction |
|---|---|
| 8.0–10.0 | Strongly Bullish (Look for Longs) |
| 6.0–7.9 | Bullish |
| 4.1–5.9 | Neutral |
| 2.1–4.0 | Bearish |
| 0.0–2.0 | Strongly Bearish (Look for Shorts) |

## Data Sources

| Pipeline | Source | Key Required |
|---|---|---|
| FRED Economic Data | `api.stlouisfed.org` | ✅ `FRED_API_KEY` |
| CFTC CoT | `cftc.gov` (ZIP download) | ❌ Free |
| US Treasury Yields | AlphaVantage | ✅ `ALPHAVANTAGE_API_KEY` |
| Global Bond Yields | Yahoo Finance (yfinance) | ❌ Free |
| Economic Calendar | EODHD | ✅ `EODHD_API_KEY` |
| News Feed | Newsdata.io | ✅ `NEWSDATA_API_KEY` |

## Local Setup

### Prerequisites
- Python 3.13+
- Node.js (optional, for frontend development)

### 1. Clone & Install
```bash
git clone <repo-url> bulls-and-bears
cd bulls-and-bears
pip install -r backend/requirements.txt
```

### 2. Environment Variables
```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
```

### 3. Run the Data Pipeline
```bash
python backend/main.py
```
This will fetch all data, compute scores, and export JSON files to `data/`.

### 4. Serve the Frontend
Open `index.html` in a browser, or use a local server:
```bash
python -m http.server 8000
# Open http://localhost:8000
```

### 5. Run Tests
```bash
python -m pytest backend/tests/ -v
```

## GitHub Actions Automation

### Data Pipeline (`data_pipeline.yml`)
- Trigger: Every 4 hours (`0 */4 * * *`) + Friday 21:00 UTC (`0 21 * * 5`)
- Runs `python backend/main.py` with API keys from GitHub Secrets
- Commits updated `data/*.json` back to the repository

### Pages Deployment (`deploy_pages.yml`)
- Trigger: Push to `main` branch (changes to root-level files)
- Deploys the entire repository root to GitHub Pages (serves `index.html` directly)

### Required Secrets
Add these to your GitHub repository → Settings → Secrets and variables → Actions:

| Secret | Description |
|---|---|
| `FRED_API_KEY` | FRED API key from `api.stlouisfed.org` |
| `ALPHAVANTAGE_API_KEY` | AlphaVantage API key |
| `EODHD_API_KEY` | EODHD API key for economic calendar |
| `NEWSDATA_API_KEY` | Newsdata.io API key for news feed |

> **Note:** Copy the actual key values from your `backend/.env` file (local) or your password manager. Do not commit real keys to the repository.

## Project Structure

```
fundamentals-app/
├── index.html                     # SPA shell (served from root by GitHub Pages)
├── styles.css                     # Bootstrap 5 + dark mode theme
├── app.js                         # Tab controller & data fetcher
├── charts.js                      # Chart.js configuration helpers
├── data/                          # Auto-generated JSON databases
├── assets/                        # Static assets (logos, etc.)
├── backend/
│   ├── main.py                    # Orchestrator
│   ├── requirements.txt           # Python dependencies
│   ├── .env.example               # API key template
│   ├── models/
│   │   └── schemas.py             # Typed dataclasses
│   ├── scrapers/
│   │   ├── fred_scraper.py        # FRED API pipeline
│   │   ├── cftc_scraper.py        # CFTC CoT ZIP parser
│   │   ├── yield_scraper.py       # AlphaVantage + yfinance
│   │   ├── calendar_scraper.py    # EODHD calendar
│   │   └── news_scraper.py        # Newsdata.io feed
│   ├── scoring/
│   │   ├── macro_score.py         # Structural Macro Score
│   │   ├── event_surprise.py      # Event Surprise Score
│   │   ├── yield_score.py         # Yield Momentum Score
│   │   ├── cftc_sentiment.py      # CFTC Sentiment Score
│   │   └── pair_math.py           # Cross-asset pair calculator
│   ├── exporters/
│   │   └── json_exporter.py       # JSON database writer
│   └── tests/
│       └── test_scoring.py        # Unit tests
├── .github/workflows/
│   ├── data_pipeline.yml          # Scheduled data pipeline
│   └── deploy_pages.yml           # GitHub Pages deployment
└── README.md
```

## Partner & CTA

**Tradersyard** is our partner (not a sponsor).  
Visit: [https://shop.tradersyard.com/ref/1486/](https://shop.tradersyard.com/ref/1486/)  
Use promo code **ROSHAN** for a special discount.

## License

Private — All rights reserved. Bulls & Bears fundamentals.
