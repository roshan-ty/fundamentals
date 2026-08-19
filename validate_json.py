import json
import math

print('=== master_bias.json ===')
with open('public/data/master_bias.json') as f:
    mb = json.load(f)
print('Top-level keys:', sorted(mb.keys()))
print('has score_breakdowns:', 'score_breakdowns' in mb)
print('has analysis_window_days:', 'analysis_window_days' in mb)
print('has analysis_note:', 'analysis_note' in mb)
print('total_pairs:', mb.get('total_pairs'))
print('total_extreme:', mb.get('total_extreme'))
print('base_scores:', mb.get('base_scores'))
print('summary:', mb.get('summary'))

# Verify score_breakdowns structure
sb = mb.get('score_breakdowns', {})
print('breakdown keys:', list(sb.keys())[:10])
for asset, items in list(sb.items())[:3]:
    print(f'  {asset} has {len(items)} items')
    if items:
        print(f'    first item keys: {sorted(items[0].keys())}')

# Verify SP500 pair has proper quote_score now
for p in mb.get('pairs', []):
    if p['name'] == 'SP500':
        print('SP500 pair:', {k: p[k] for k in ['name', 'base_score', 'quote_score', 'combined_bias', 'direction']})
        break

# NaN/Inf check
def check(obj, path=''):
    if isinstance(obj, dict):
        for k, v in obj.items():
            check(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            check(v, f'{path}[{i}]')
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            print(f'NAN/INF at {path}: {obj}')

check(mb)
print('NaN check complete')

# Verify all pair scores in range
out = [p['name'] for p in mb.get('pairs', []) if not (1.0 <= p['combined_bias'] <= 10.0)]
print('out-of-range biases:', out if out else 'none')

# Verify no quote_score == 0.0 remains on INDEX pairs
zero_q = [p['name'] for p in mb.get('pairs', []) if p['asset_class'] == 'INDEX' and p['quote_score'] == 0.0]
print('INDEX pairs with zero quote_score:', zero_q if zero_q else 'none')

print()
print('=== cftc_report.json ===')
with open('public/data/cftc_report.json') as f:
    cftc = json.load(f)
print('total_markets:', cftc.get('total_markets'))
print('markets:', list(cftc.get('positions', {}).keys()))

print()
print('=== ai_insights.json ===')
with open('public/data/ai_insights.json') as f:
    ai = json.load(f)
print('provider:', ai.get('provider'))
print('analysis length:', len(ai.get('analysis', '')))
print('INVESTMENT_FLOWS mentioned:', 'INSTITUTIONAL FLOWS' in ai.get('analysis', ''))

print()
print('=== calendar.json ===')
with open('public/data/calendar.json') as f:
    cal = json.load(f)
print('total_events:', cal.get('total_events'))