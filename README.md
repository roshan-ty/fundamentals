# Bulls & Bears Fundamentals

**Advanced Macroeconomic Fundamental Screening Dashboard** — A $0-infrastructure, fully automated platform that processes 30+ global macroeconomic data points across 200+ multi-asset trading pairs (Forex, Commodities, Equity Indices, and Cryptocurrencies).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GITHUB ACTIONS (Daily)                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. parsers.py — Collect 30 data points from 8+ APIs  │  │
│  │  2. scorer.py — Compute 1-10 scores with tier weights │  │
│  │  3. ai_analyst.py — xAI macro summary generation      │  │
│  │  4. Export 5 JSON files to /public/data/              │  │
│  └───────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  git commit + push to gh-pages                        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              GITHUB PAGES (Static Hosting)                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  React + Tailwind SPA reads local JSON files          │  │
│  │  6 Tab Views: Home, Calendar, Fundamental, Bias,      │  │
│  │  CFTC, FRED                                           │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Scoring Framework

### Scale
- **1.0** — Strongly Bearish
- **5.0** — Strictly Neutral
- **10.0** — Strongly Bullish

### Expectation Scoring Matrix
```
D = Actual - Forecast
D > 0 (beat)  → 6.0 to 10.0
D < 0 (miss)  → 1.0 to 4.0
```

### Multi-Asset Correlation Logic
| Asset Class | Hot Inflation | Hot Growth |
|-------------|--------------|------------|
| Forex | Bullish (higher rates) | Bullish |
| Equities | Bearish (borrowing costs) | Bullish |
| Gold | Bullish (hard hedge) | Bullish |
| Crypto | Bearish (tight money) | Moderate Bullish |

### Tier Weights
| Tier | Multiplier | Events |
|------|-----------|--------|
| Tier 1 | ×3 | Interest Rate decisions, Core CPI, Core PCE, Employment Change, NFP |
| Tier 2 | ×2 | GDP, Headline CPI/PPI, PMIs, CFTC CoT |
| Tier 3 | ×1 | Retail Sentiment, Seasonality, Hourly Earnings |

### Cross-Pair Formula
```
Pair Bias = 5 + (Base Asset Score - Quote Asset Score)
Clamped to [1.0, 10.0]
```

## Data Sources (30 Points)

| Points | Category | Source |
|--------|----------|--------|
| 1-6, 11, 12, 20-22, 29 | Economic Indicators & Labor | FMP + Finnhub |
| 7-10, 23, 24 | PMIs & Inflation Trends | AlphaVantage + FRED |
| 13-19, 25 | Central Bank & Policy Rates | FRED + FMP + BeautifulSoup |
| 26, 28 | CFTC Institutional Positioning | CFTC.gov ZIP → Pandas |
| 27 | Retail Sentiment | DailyFX/Oanda BS4 |
| 30 | Seasonality | yfinance (15-year) |

## Base Assets Scored

**Forex:** USD, EUR, GBP, JPY, AUD, CAD, CHF, NZD  
**Commodities:** XAU (Gold), XAG (Silver), WTI (Crude Oil)  
**Indices:** SP500, NAS100, GER40  
**Crypto:** BTC, ETH, SOL, XRP

**Total Cross-Pairs:** 45+ FX pairs + Metals + Energy + Indices + Crypto = **200+ pairs**

## Output Files

| File | Contents |
|------|----------|
| `/public/data/calendar.json` | Economic events with surprise ratios |
| `/public/data/macro_data.json` | FRED historical series (GDP, CPI, PCE, etc.) |
| `/public/data/cftc_report.json` | Institutional long/short positions |
| `/public/data/master_bias.json` | Complete 200+ pair scoring matrix |
| `/public/data/ai_insights.json` | xAI-generated macro summary |

## Local Development

### Prerequisites
- Python 3.13+
- Node.js 20+
- API keys (see `.env.example`)

### Backend Setup
```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r backend/requirements.txt

# Configure API keys
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys

# Run the pipeline
python backend/fetch_pipeline.py
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev  # Development server on port 3000
npm run build  # Production build to frontend/dist/
```

### GitHub Actions Deployment
1. Push to `main` branch
2. Add repository secrets in Settings → Secrets and variables → Actions:
   - `FRED_API_KEY`
   - `ALPHAVANTAGE_API_KEY`
   - `FINNHUB_API_KEY`
   - `FMP_API_KEY`
   - `EODHD_API_KEY`
   - `NEWSDATA_API_KEY`
   - `XAI_API_KEY`
3. The workflow runs daily at 06:00 UTC and deploys to GitHub Pages

## Partner

**TradersYard** — Our partnered prop trading firm.  
Use code **ROSHAN** for exclusive discount.  
[Get Funded at TradersYard](https://shop.tradersyard.com/ref/1486/)

## License

MIT — Built for the trading community.