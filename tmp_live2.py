import requests
base = 'https://roshan-ty.github.io/fundamentals/'
for p in ['', 'js/app.js', 'js/views.js', 'js/boot.js', 'css/style.css',
          'data/news/feed.json', 'data/bias/currencies.json', 'data/bias/pairs.json',
          'data/bias/instruments.json', 'data/calendar/releases.json', 'data/setups/top.json']:
    r = requests.get(base + p, timeout=45)
    print('OK' if r.status_code == 200 else 'FAIL', p, r.status_code)

news = requests.get(base + 'data/news/feed.json', timeout=45).json()
print('News items:', len(news), '| with url:', sum(1 for n in news if n.get('url')) if isinstance(news, list) else '?')
cur = requests.get(base + 'data/bias/currencies.json', timeout=45).json().get('currencies', {})
print('Currencies verdicts:', ', '.join(['%s=%s(%dpts)' % (k, v.get('verdict'), v.get('released_points', 0)) for k, v in cur.items()]))
pairs = requests.get(base + 'data/bias/pairs.json', timeout=45).json().get('pairs', [])
from collections import Counter
print('Pairs:', len(pairs), dict(Counter(p.get('verdict') for p in pairs)))
setups = requests.get(base + 'data/setups/top.json', timeout=45).json().get('setups', [])
print('Top setups:', [(s.get('symbol'), s.get('verdict'), s.get('confidence')) for s in setups[:6]])