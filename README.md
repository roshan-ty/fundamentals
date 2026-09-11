# Bulls & Bears Fundamentals

A fundamentals screening platform for serious FX, metals, energy, crypto and
index traders. Dense, real-data-driven bias scoring, positioning analysis and
trade setup ranking — updated around the clock.

## What it provides

- **Headline bias** — 0–10 bias scores for currencies, metals, energy, crypto
  and equity indices, derived from published economic data and positioning
  flows. Bands: 0–2 very bearish · 3–4 bearish · 5 neutral · 6–7 bullish ·
  8–10 very bullish.
- **Data** — per-instrument deep dive: economic calendar, bias scoring per data
  point, positioning report, yield context, and instrument-tagged news.
- **Bias** — the full traded universe as a sortable, searchable matrix.
- **Positioning** — commitment-of-traders reports: non-commercial vs
  commercial exposure, net positioning curves and week-over-week shifts.
- **Historical Data** — interactive multi-series charts (rates, yields,
  inflation, labor, growth, sentiment).
- **Analysis** — a data-driven narrative for every scored pair, generated from
  the actual collected data.
- **Top Setups** — ranked trade setups by bias magnitude × data confidence.

## Scoring methodology

A data point contributes to a score **only when the published actual differs
from the previous value** — an unchanged reading contributes zero. The direction
(higher/lower = bullish) and impact weight of each data point are defined in
`config/scorecard.json` and are fully tunable. Currency scores normalize to a
0–10 scale; pairs are derived from the two currencies; metals/energy score off
the dollar plus positioning; crypto and indices use a clearly-labelled derived
sentiment proxy (they have no economic calendar or positioning data).

Bias never uses news or yield curves — those run separately as confirmation and
context.

## Automation

The data layer refreshes on a schedule independent of any local machine. All
credentials are held as repository secrets and injected only at run time. The
website is fully static and served from the committed data layer.

## Local development

```
pip install -r requirements.txt
cp .env.example .env        # fill for local testing only
python scripts/orchestrator.py scoring
```

A local preview server:

```
python -m http.server 8899
# open http://127.0.0.1:8899/
```

## Repository layout

```
config/     scoring rules, instrument universe, news rules (all tunable)
scripts/    collectors, scoring engine, narrative + setup generation
data/       the committed database the website reads
css, js     static web app (the 7 tabs) served at the repo root
.github/    scheduled automation, validation and deployment
```