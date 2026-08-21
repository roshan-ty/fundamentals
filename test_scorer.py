import sys
sys.path.insert(0, '.')
from datetime import datetime, timedelta, timezone
from backend.scorer import score_all, apply_cross_asset_spillover, INVERSE_USD_ASSETS, DIRECT_USD_ASSETS

now = datetime.now(timezone.utc)
recent = now.strftime('%Y-%m-%d')
prev = (now - timedelta(days=30)).strftime('%Y-%m-%d')

# OVERWHELMINGLY BEARISH USD SCENARIO:
# - Weak GDP (falling below previous)
# - Rising unemployment
# - Soft CPI (below previous)
# - NFP miss (payrolls falling sharply)
# - Falling 10Y yields (capital fleeing USD)
# - Fed Funds cut (rate declining)
test = {
    'fred': {
        'GDPC1': [{'date': recent, 'value': 23500.0}, {'date': prev, 'value': 24000.0}],
        'UNRATE': [{'date': recent, 'value': 5.6}, {'date': prev, 'value': 4.8}],
        'CPILFESL': [{'date': recent, 'value': 317.0}, {'date': prev, 'value': 320.0}],
        'FEDFUNDS': [{'date': recent, 'value': 4.0}, {'date': prev, 'value': 4.5}],
        'PAYEMS': [{'date': recent, 'value': 140000.0}, {'date': prev, 'value': 180000.0}],
        'DGS10': [{'date': recent, 'value': 3.6}, {'date': prev, 'value': 4.2}],
    },
    'cftc': {},
    'central_bank_rates': {'USD': 4.0, 'EUR': 4.25, 'GBP': 5.25, 'JPY': 0.5,
                           'AUD': 4.35, 'CAD': 5.0, 'CHF': 1.75, 'NZD': 5.5},
    'yield_curve': {},
    'seasonality': {},
    'retail_sentiment': {},
}
r = score_all(test)
usd = r['base_scores']['USD']
print('USD score:', usd)

# Verify cross-asset spillover: weak USD => bullish XAU/XAG/EUR/GBP/AUD/NZD/BTC
print('\nCounter-asset scores (should be > 6.0 when USD < 4.0):')
for asset in ['XAU', 'XAG', 'EUR', 'GBP', 'AUD', 'NZD', 'BTC']:
    score = r['base_scores'].get(asset, 5.0)
    status = 'PASS' if (r['base_scores'].get('USD', 5.0) < 4.0 and score > 6.0) or r['base_scores'].get('USD', 5.0) >= 4.0 else 'FAIL'
    print(f'  {asset}: {score:.1f} {status}')

print('\nWindow:', r['analysis_window_days'])
print('Breakdowns:', len(r['score_breakdowns']))
print('Pairs:', r['total_pairs'])
if 'USD' in r['score_breakdowns']:
    for item in r['score_breakdowns']['USD']:
        print(f"  {item['indicator']}: value={item['value']} score={item['score']} direction={item['direction']}")

# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-ASSET SPILLOVER MATRIX VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
print('\n' + '=' * 70)
print('CROSS-ASSET SPILLOVER MATRIX VERIFICATION')
print('=' * 70)

# Test with a known USD score
test_usd = 3.2
test_scores = {'USD': test_usd}
for a in INVERSE_USD_ASSETS + DIRECT_USD_ASSETS:
    test_scores[a] = 5.0  # placeholder
result = apply_cross_asset_spillover(test_scores)

print(f'\nS_USD = {test_usd}')
print(f'Expected inverse asset score = 11.0 - {test_usd} = {11.0 - test_usd:.1f}')
print(f'Expected direct asset score  = {test_usd}')

all_pass = True
for asset in INVERSE_USD_ASSETS:
    expected = round(max(1.0, min(10.0, 11.0 - test_usd)), 2)
    actual = result[asset]
    ok = abs(actual - expected) < 0.01
    all_pass = all_pass and ok
    print(f'  {asset}: {actual:.2f} (expected {expected:.2f}) {"PASS" if ok else "FAIL"}')

for asset in DIRECT_USD_ASSETS:
    expected = round(max(1.0, min(10.0, test_usd)), 2)
    actual = result[asset]
    ok = abs(actual - expected) < 0.01
    all_pass = all_pass and ok
    print(f'  {asset}: {actual:.2f} (expected {expected:.2f}) {"PASS" if ok else "FAIL"}')

print(f'\nCross-asset spillover: {"ALL PASS" if all_pass else "SOME FAILED"}')

# Verify the full pipeline produces bearish USD
print('\n' + '=' * 70)
print('FULL PIPELINE VERIFICATION (Bearish USD Scenario)')
print('=' * 70)
usd_score = r['base_scores'].get('USD', 5.0)
print(f'USD Score: {usd_score:.2f} {"PASS" if usd_score < 4.0 else "FAIL"} (expected < 4.0)')

# Verify inverse assets are bullish
for asset in ['XAU', 'EUR', 'GBP', 'AUD', 'NZD', 'BTC']:
    score = r['base_scores'].get(asset, 5.0)
    expected = round(max(1.0, min(10.0, 11.0 - usd_score)), 2)
    ok = abs(score - expected) < 0.01
    print(f'{asset}: {score:.2f} (expected {expected:.2f}) {"PASS" if ok else "FAIL"}')