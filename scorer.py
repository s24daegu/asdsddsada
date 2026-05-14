import sqlite3
import os
from datetime import datetime
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exchange_data.db')

_score_cache = {}
CACHE_TTL = 1800  # 30분

SEASON_DATA = {
    'USD': {'best': [4,5,6,9,10], 'avoid': [], 'peak': [7,8]},
    'EUR': {'best': [4,5,6,9,10], 'avoid': [7,8], 'peak': [7,8]},
    'JPY': {'best': [3,4,10,11], 'avoid': [6,7,8], 'peak': [3,4]},
    'CNY': {'best': [3,4,9,10], 'avoid': [1,2,7,8], 'peak': [10]},
    'GBP': {'best': [5,6,7,8,9], 'avoid': [11,12,1,2], 'peak': [6,7,8]},
    'AUD': {'best': [9,10,11,3,4], 'avoid': [12,1,2], 'peak': [12,1]},
    'CAD': {'best': [6,7,8,9], 'avoid': [12,1,2,3], 'peak': [7,8]},
    'CHF': {'best': [6,7,8,12,1,2], 'avoid': [], 'peak': [7,8]},
    'HKD': {'best': [10,11,12,1,2], 'avoid': [6,7,8,9], 'peak': [10,11]},
    'SGD': {'best': [2,3,7,8], 'avoid': [11,12], 'peak': [7,8]},
    'THB': {'best': [11,12,1,2,3], 'avoid': [5,6,7,8,9], 'peak': [12,1]},
    'INR': {'best': [10,11,12,1,2,3], 'avoid': [6,7,8,9], 'peak': [12,1]},
    'MYR': {'best': [3,4,5,6], 'avoid': [10,11], 'peak': [3,4]},
    'NZD': {'best': [12,1,2,3], 'avoid': [6,7,8], 'peak': [1,2]},
}

CITY_NAMES = {
    'USD': '뉴욕', 'EUR': '파리', 'JPY': '도쿄', 'CNY': '베이징',
    'GBP': '런던', 'AUD': '시드니', 'CAD': '토론토', 'CHF': '취리히',
    'HKD': '홍콩', 'SGD': '싱가포르', 'THB': '방콕', 'INR': '뭄바이',
    'MYR': '쿠알라룸푸르', 'NZD': '오클랜드',
}

def get_season_score(currency, month):
    """Return season score 0-20 based on SEASON_DATA."""
    data = SEASON_DATA.get(currency, {})
    best  = data.get('best', [])
    avoid = data.get('avoid', [])
    peak  = data.get('peak', [])

    if month in best and month not in avoid:
        base = 18
    elif month in avoid:
        base = 3
    else:
        base = 10

    # Peak season (crowded, expensive) slight penalty
    if month in peak:
        base = max(0, base - 3)

    return base

def compute_total_score(currency, month, weather_s, trend_s, sentiment_s, season_s):
    """Combine all component scores into total 0-100."""
    total = weather_s + trend_s + sentiment_s + season_s
    return min(100, max(0, round(total, 1)))

def score_label(total):
    """Return (Korean label, css class) for a total score."""
    if total >= 80:
        return ('최고의 선택', 'excellent')
    elif total >= 65:
        return ('추천', 'good')
    elif total >= 50:
        return ('무난함', 'fair')
    elif total >= 35:
        return ('비추천', 'poor')
    else:
        return ('피하세요', 'avoid')

def compute_all_scores(currency, month, news_items=None, rates_data=None):
    """
    Full pipeline: compute all component scores and return structured result.
    Imports weather, trend, sentiment modules inline to avoid circular deps.
    Returns dict with all scores and metadata.
    """
    key = f'all_{currency}_{month}'
    cached = _score_cache.get(key)
    if cached and time.time() - cached['ts'] < CACHE_TTL:
        return cached['data']

    from weather import get_weather_score, fetch_weather_month, CITY_COORDS
    from trend import get_trend_score, get_trend_analysis
    from sentiment import get_sentiment_score, get_sentiment_label

    # Compute each component with individual fallbacks
    try:
        weather_s = get_weather_score(currency, month)
    except Exception as e:
        print(f'[scorer weather error] {currency}: {e}')
        weather_s = 15  # neutral

    try:
        trend_s = get_trend_score(currency, rates_data)
    except Exception as e:
        print(f'[scorer trend error] {currency}: {e}')
        trend_s = 10  # neutral

    try:
        sentiment_s = get_sentiment_score(currency, news_items)
    except Exception as e:
        print(f'[scorer sentiment error] {currency}: {e}')
        sentiment_s = 10  # neutral

    season_s = get_season_score(currency, month)
    total    = compute_total_score(currency, month, weather_s, trend_s, sentiment_s, season_s)

    # Gather supplementary data for NLG
    try:
        weather_data = fetch_weather_month(currency, month)
    except Exception:
        weather_data = None
    try:
        trend_data = get_trend_analysis(currency)
    except Exception:
        trend_data = None
    sent_label = get_sentiment_label(sentiment_s)
    label, css = score_label(total)

    result = {
        'currency':     currency,
        'month':        month,
        'city':         CITY_NAMES.get(currency, ''),
        'scores': {
            'weather':   weather_s,
            'trend':     trend_s,
            'sentiment': sentiment_s,
            'season':    season_s,
            'total':     total,
        },
        'label':        label,
        'css_class':    css,
        'weather_data': weather_data,
        'trend_data':   trend_data,
        'sentiment_label': sent_label,
    }

    _score_cache[key] = {'data': result, 'ts': time.time()}

    # Persist to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            '''INSERT OR REPLACE INTO travel_scores
               (currency, month, weather_score, trend_score, sentiment_score, season_score, total_score, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (currency, month, weather_s, trend_s, sentiment_s, season_s, total, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[scorer db error] {e}')

    return result


# ─── Travel Style Profiles ───────────────────────────────────────────────────

STYLE_WEIGHTS = {
    'weather_lover': {
        'weather':   0.55,  # 55 pts max (was 40)
        'trend':     0.15,
        'sentiment': 0.15,
        'season':    0.15,
    },
    'budget_focused': {
        'weather':   0.25,
        'trend':     0.40,  # 40 pts max
        'sentiment': 0.20,
        'season':    0.15,
    },
    'adventure': {
        'weather':   0.30,
        'trend':     0.25,
        'sentiment': 0.20,
        'season':    0.25,
    },
    'balanced': {
        'weather':   0.40,
        'trend':     0.20,
        'sentiment': 0.20,
        'season':    0.20,
    },
}

STYLE_LABELS = {
    'weather_lover':  '날씨 우선',
    'budget_focused': '비용 우선',
    'adventure':      '모험가',
    'balanced':       '밸런스',
}

def compute_styled_total(scores_dict, style='balanced'):
    """
    Re-weight component scores by travel style.
    scores_dict keys: weather, trend, sentiment, season (raw 0-max values)
    Returns weighted total 0-100.
    """
    weights = STYLE_WEIGHTS.get(style, STYLE_WEIGHTS['balanced'])

    # Normalize each component to 0-1 range, then apply weight × 100
    # Actual maximums: weather=40, trend=20, sentiment=18, season=18
    normalized = {
        'weather':   scores_dict.get('weather', 20)   / 40,
        'trend':     scores_dict.get('trend', 10)      / 20,
        'sentiment': scores_dict.get('sentiment', 10)  / 18,
        'season':    scores_dict.get('season', 10)     / 18,
    }

    total = sum(normalized[k] * weights[k] * 100 for k in weights)
    return round(min(100, max(0, total)), 1)

def rank_currencies_for_month(month, style='balanced', news_map=None):
    """
    Rank all 14 currencies for a given month and style.
    Returns list of score_result dicts sorted by styled total (descending).
    news_map: dict of currency -> list of news items (optional)
    """
    from weather import CITY_COORDS
    results = []
    for currency in CITY_COORDS.keys():
        news_items = (news_map or {}).get(currency)
        result = compute_all_scores(currency, month, news_items=news_items)
        if result:
            styled_total = compute_styled_total(result['scores'], style)
            result = dict(result)
            result['styled_total'] = styled_total
            result['style']        = style
            result['style_label']  = STYLE_LABELS.get(style, style)
            label, css = score_label(styled_total)
            result['styled_label']    = label
            result['styled_css']      = css
            results.append(result)

    results.sort(key=lambda x: x['styled_total'], reverse=True)
    return results
