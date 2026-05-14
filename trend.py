import requests
import sqlite3
import os
from datetime import datetime, timedelta
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exchange_data.db')

_trend_cache = {}
CACHE_TTL = 3600  # 1시간

def _cache_get(key):
    item = _trend_cache.get(key)
    if item and time.time() - item['ts'] < CACHE_TTL:
        return item['data']
    return None

def _cache_set(key, data):
    _trend_cache[key] = {'data': data, 'ts': time.time()}

def fetch_rate_history(currency, days=30):
    """Fetch historical rates from Frankfurter API. Returns list of (date, rate_krw_per_unit) sorted by date."""
    key = f'trend_raw_{currency}_{days}'
    cached = _cache_get(key)
    if cached:
        return cached

    try:
        end   = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        url   = f'https://api.frankfurter.app/{start}..{end}?from=KRW&to={currency}'
        resp  = requests.get(url, timeout=10)
        resp.raise_for_status()
        data  = resp.json()

        # Convert to list of (date, raw_rate) sorted chronologically
        # raw_rate = 1 KRW in foreign currency units
        result = []
        for date, rates in sorted(data.get('rates', {}).items()):
            if currency in rates:
                result.append((date, rates[currency]))

        _cache_set(key, result)
        return result
    except Exception as e:
        print(f'[trend fetch error] {currency}: {e}')
        return []

def get_trend_analysis(currency, days=30):
    """
    Returns dict with trend analysis:
    - direction: 'up' | 'down' | 'flat'  (KRW rate vs foreign)
    - change_pct: float (% change over period)
    - recent_7d_pct: float (% change last 7 days)
    - volatility: float (std dev of daily changes)
    """
    history = fetch_rate_history(currency, days)
    if len(history) < 5:
        return {'direction': 'flat', 'change_pct': 0, 'recent_7d_pct': 0, 'volatility': 0}

    # Overall trend (first vs last)
    first_rate = history[0][1]
    last_rate  = history[-1][1]
    change_pct = ((last_rate - first_rate) / first_rate) * 100 if first_rate else 0

    # Recent 7-day trend
    recent = history[-7:] if len(history) >= 7 else history
    r_first = recent[0][1]
    r_last  = recent[-1][1]
    recent_7d_pct = ((r_last - r_first) / r_first) * 100 if r_first else 0

    # Volatility: average of absolute daily changes
    daily_changes = []
    for i in range(1, len(history)):
        prev = history[i-1][1]
        curr = history[i][1]
        if prev:
            daily_changes.append(abs((curr - prev) / prev) * 100)
    volatility = sum(daily_changes) / len(daily_changes) if daily_changes else 0

    direction = 'up' if change_pct > 0.3 else ('down' if change_pct < -0.3 else 'flat')

    return {
        'direction':     direction,
        'change_pct':    round(change_pct, 3),
        'recent_7d_pct': round(recent_7d_pct, 3),
        'volatility':    round(volatility, 4),
    }

def get_trend_score(currency, rates_data=None):
    """
    Return trend score 0-20.
    Scoring: how favorable is the current exchange rate for Korean travelers?
    - KRW strengthening (rate UP) = good for travel = higher score
    - KRW weakening (rate DOWN) = expensive travel = lower score
    - Stability bonus: low volatility is preferable
    """
    analysis = get_trend_analysis(currency)
    change_pct = analysis['change_pct']
    recent_7d  = analysis['recent_7d_pct']
    volatility = analysis['volatility']

    # Base score from 30-day trend (0-14)
    if change_pct > 3:
        base = 14
    elif change_pct > 1.5:
        base = 12
    elif change_pct > 0.5:
        base = 10
    elif change_pct > -0.5:
        base = 8   # roughly flat
    elif change_pct > -1.5:
        base = 5
    elif change_pct > -3:
        base = 3
    else:
        base = 1

    # Recent momentum bonus/penalty (0 to +4 or -2)
    if recent_7d > 1:
        momentum = 4
    elif recent_7d > 0:
        momentum = 2
    elif recent_7d > -1:
        momentum = 0
    else:
        momentum = -2

    # Stability bonus (0-2): prefer low volatility
    stability = 2 if volatility < 0.3 else (1 if volatility < 0.6 else 0)

    score = max(0, min(20, base + momentum + stability))
    return score
