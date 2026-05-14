import sqlite3
import os
from datetime import datetime
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exchange_data.db')

_sentiment_cache = {}
CACHE_TTL = 3600  # 1시간

# Keyword categories with weights
KEYWORDS = {
    'positive': {
        # Korean
        '안정': 2, '강세': 2, '회복': 2, '상승': 1, '호조': 2,
        '관광': 2, '여행': 2, '개방': 2, '평화': 3, '성장': 1,
        '투자': 1, '협력': 2, '우호': 2, '우량': 1, '저렴': 2,
        # English
        'stable': 2, 'strong': 2, 'recovery': 2, 'growth': 1, 'bullish': 2,
        'tourism': 2, 'travel': 2, 'open': 1, 'peace': 3, 'cooperation': 2,
        'affordable': 2, 'boost': 1, 'optimistic': 2, 'rally': 2,
    },
    'negative': {
        # Korean
        '불안': 3, '약세': 2, '급락': 3, '위기': 3, '전쟁': 4,
        '폭등': 2, '폭락': 3, '봉쇄': 3, '테러': 4, '지진': 3,
        '홍수': 2, '태풍': 2, '폭염': 2, '전염병': 3, '갈등': 2,
        '제재': 2, '분쟁': 3, '시위': 2, '혼란': 2, '충돌': 2,
        # English
        'war': 4, 'crisis': 3, 'unstable': 3, 'weak': 2, 'bearish': 2,
        'terror': 4, 'earthquake': 3, 'flood': 2, 'typhoon': 2, 'outbreak': 3,
        'pandemic': 3, 'sanctions': 2, 'conflict': 3, 'protest': 2, 'tension': 2,
        'collapse': 3, 'recession': 2, 'inflation': 1, 'plunge': 3,
    }
}

def analyze_text(text):
    """Return (positive_score, negative_score) for a text string."""
    text_lower = text.lower()
    pos = 0
    neg = 0
    for word, weight in KEYWORDS['positive'].items():
        if word.lower() in text_lower:
            pos += weight
    for word, weight in KEYWORDS['negative'].items():
        if word.lower() in text_lower:
            neg += weight
    return pos, neg

def get_sentiment_score(currency, news_items=None):
    """
    Return sentiment score 0-20.
    Analyzes news titles and summaries for travel-relevant sentiment.
    Higher = more positive news context for travel.
    """
    key = f'sentiment_{currency}'
    cached = _sentiment_cache.get(key)
    if cached and time.time() - cached['ts'] < CACHE_TTL:
        return cached['data']

    if not news_items:
        return 10  # neutral fallback

    total_pos = 0
    total_neg = 0
    count = 0

    for item in news_items:
        title   = item.get('title', '')
        summary = item.get('summary', '')
        combined = f'{title} {summary}'

        pos, neg = analyze_text(combined)
        total_pos += pos
        total_neg += neg
        count += 1

    if count == 0:
        return 10

    # Net sentiment ratio
    net = total_pos - total_neg
    total = total_pos + total_neg if (total_pos + total_neg) > 0 else 1
    ratio = net / total  # -1.0 to +1.0

    # Map ratio to 0-20 scale
    if ratio > 0.5:
        score = 18
    elif ratio > 0.2:
        score = 15
    elif ratio > 0.0:
        score = 12
    elif ratio > -0.2:
        score = 9
    elif ratio > -0.5:
        score = 5
    else:
        score = 2

    # Persist to DB
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'INSERT OR REPLACE INTO sentiment_cache (currency, date, score) VALUES (?, ?, ?)',
            (currency, datetime.now().strftime('%Y-%m-%d'), score)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[sentiment db error] {e}')

    _sentiment_cache[key] = {'data': score, 'ts': time.time()}
    return score

def get_sentiment_label(score):
    """Return human-readable sentiment label."""
    if score >= 16:
        return ('매우 긍정적', 'very_positive')
    elif score >= 12:
        return ('긍정적', 'positive')
    elif score >= 8:
        return ('중립', 'neutral')
    elif score >= 5:
        return ('부정적', 'negative')
    else:
        return ('매우 부정적', 'very_negative')
