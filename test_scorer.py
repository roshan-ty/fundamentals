import sys
sys.path.insert(0, '.')
from datetime import datetime, timedelta, timezone
from backend.scorer import score_all

now = datetime.now(timezone.utc)
recent = now.strftime('%Y-%m-%d')
prev = (now - timedelta(days=30)).strftime('%Y-%m-%d')

test = {
    'fred': {
        'GDPC1': [{'date': recent, 'value': 23500.0}, {'date': prev, 'value': 24000.0}],
        'UNRATE': [{'date': recent, 'value': 5.2}, {'date': prev, 'value': 4.8}],
        'CPILFESL': [{'date': recent, 'value': 318.0}, {'date': prev, 'value': 320.0}],
        'FEDFUNDS': [{'date': recent, 'value': 4.5}, {'date': prev, 'value': 5.0}],
    },
    'cftc': {},
    'central_bank_rates': {'USD': 4.5},
    'yield_curve': {},
    'seasonality': {},
    'retail_sentiment': {},
}
r = score_all(test)
print('USD score:', r['base_scores']['USD'])
print('Window:', r['analysis_window_days'])
print('Breakdowns:', len(r['score_breakdowns']))
print('Pairs:', r['total_pairs'])
if 'USD' in r['score_breakdowns']:
    for item in r['score_breakdowns']['USD']:
        print(f"  {item['indicator']}: value={item['value']} score={item['score']} direction={item['direction']}")