from flask import Flask, render_template, jsonify
import requests
import sqlite3
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import time

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exchange_data.db')

CURRENCIES = {
    'USD': {'name': '미국 달러', 'country': '미국', 'flag': '🇺🇸', 'symbol': '$',  'unit': 1},
    'EUR': {'name': '유로',       'country': '유럽', 'flag': '🇪🇺', 'symbol': '€',  'unit': 1},
    'JPY': {'name': '일본 엔',    'country': '일본', 'flag': '🇯🇵', 'symbol': '¥',  'unit': 100},
    'CNY': {'name': '중국 위안',  'country': '중국', 'flag': '🇨🇳', 'symbol': '¥',  'unit': 1},
    'GBP': {'name': '영국 파운드','country': '영국', 'flag': '🇬🇧', 'symbol': '£',  'unit': 1},
    'AUD': {'name': '호주 달러',  'country': '호주', 'flag': '🇦🇺', 'symbol': 'A$', 'unit': 1},
    'CAD': {'name': '캐나다 달러','country': '캐나다','flag': '🇨🇦', 'symbol': 'C$', 'unit': 1},
    'CHF': {'name': '스위스 프랑','country': '스위스','flag': '🇨🇭', 'symbol': 'Fr', 'unit': 1},
    'HKD': {'name': '홍콩 달러',  'country': '홍콩', 'flag': '🇭🇰', 'symbol': 'HK$','unit': 1},
    'SGD': {'name': '싱가포르 달러','country': '싱가포르','flag': '🇸🇬','symbol': 'S$','unit': 1},
    'THB': {'name': '태국 바트',  'country': '태국', 'flag': '🇹🇭', 'symbol': '฿',  'unit': 100},
    'INR': {'name': '인도 루피',  'country': '인도', 'flag': '🇮🇳', 'symbol': '₹',  'unit': 100},
    'MYR': {'name': '말레이시아 링깃','country': '말레이시아','flag': '🇲🇾','symbol': 'RM','unit': 1},
    'NZD': {'name': '뉴질랜드 달러','country': '뉴질랜드','flag': '🇳🇿','symbol': 'NZ$','unit': 1},
}

NEWS_QUERIES = {
    'USD': ('원달러 환율', 'USD KRW exchange rate'),
    'EUR': ('유로 환율 한국',   'EUR KRW exchange rate'),
    'JPY': ('원엔 환율 일본',   'JPY KRW exchange rate'),
    'CNY': ('원위안 환율 중국', 'CNY KRW exchange rate'),
    'GBP': ('영국 파운드 환율', 'GBP KRW exchange rate'),
    'AUD': ('호주 달러 환율',   'AUD KRW exchange rate'),
    'CAD': ('캐나다 달러 환율', 'CAD KRW exchange rate'),
    'CHF': ('스위스 프랑 환율', 'CHF KRW exchange rate'),
    'HKD': ('홍콩 달러 환율',   'HKD KRW exchange rate'),
    'SGD': ('싱가포르 달러 환율','SGD KRW exchange rate'),
    'THB': ('태국 바트 환율',   'THB KRW exchange rate'),
    'INR': ('인도 루피 환율',   'INR KRW exchange rate'),
    'MYR': ('말레이시아 링깃 환율', 'MYR KRW exchange rate'),
    'NZD': ('뉴질랜드 달러 환율', 'NZD KRW exchange rate'),
}

_cache = {}
CACHE_TTL = 300  # 5분

def cache_get(key):
    item = _cache.get(key)
    if item and time.time() - item['ts'] < CACHE_TTL:
        return item['data']
    return None

def cache_set(key, data):
    _cache[key] = {'data': data, 'ts': time.time()}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS rates (
            date     TEXT,
            currency TEXT,
            rate     REAL,
            PRIMARY KEY (date, currency)
        )
    ''')
    conn.commit()
    conn.close()

def fetch_current_rates():
    cached = cache_get('current_rates')
    if cached:
        return cached

    try:
        resp = requests.get('https://api.frankfurter.app/latest?from=KRW', timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cache_set('current_rates', data)

        today = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for currency, rate in data.get('rates', {}).items():
            c.execute(
                'INSERT OR REPLACE INTO rates (date, currency, rate) VALUES (?, ?, ?)',
                (today, currency, rate)
            )
        conn.commit()
        conn.close()
        return data
    except Exception as e:
        print(f'[rates error] {e}')
        return None

def fetch_yesterday_rates():
    cached = cache_get('yesterday_rates')
    if cached:
        return cached

    try:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        resp = requests.get(f'https://api.frankfurter.app/{yesterday}?from=KRW', timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cache_set('yesterday_rates', data)
        return data
    except Exception as e:
        print(f'[yesterday error] {e}')
        return None

def fetch_historical_rates(currency, days=30):
    key = f'hist_{currency}_{days}'
    cached = cache_get(key)
    if cached:
        return cached

    try:
        end   = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        url   = f'https://api.frankfurter.app/{start}..{end}?from=KRW&to={currency}'
        resp  = requests.get(url, timeout=10)
        resp.raise_for_status()
        data  = resp.json()
        cache_set(key, data)
        return data
    except Exception as e:
        print(f'[historical error] {e}')
        return None

def fetch_news(currency):
    key = f'news_{currency}'
    cached = cache_get(key)
    if cached:
        return cached

    ko_q, en_q = NEWS_QUERIES.get(currency, (f'{currency} 환율', f'{currency} exchange rate'))
    items = []

    # 한국어 뉴스
    try:
        url  = f'https://news.google.com/rss/search?q={requests.utils.quote(ko_q)}&hl=ko&gl=KR&ceid=KR:ko'
        feed = feedparser.parse(url)
        for entry in feed.entries[:6]:
            raw = getattr(entry, 'summary', '') or ''
            summary = BeautifulSoup(raw, 'html.parser').get_text()[:250]
            items.append({
                'title':     entry.title,
                'link':      entry.link,
                'published': getattr(entry, 'published', ''),
                'summary':   summary,
                'lang':      'ko',
            })
    except Exception as e:
        print(f'[ko news error] {e}')

    # 영어 뉴스
    try:
        url  = f'https://news.google.com/rss/search?q={requests.utils.quote(en_q)}&hl=en&gl=US&ceid=US:en'
        feed = feedparser.parse(url)
        for entry in feed.entries[:4]:
            raw = getattr(entry, 'summary', '') or ''
            summary = BeautifulSoup(raw, 'html.parser').get_text()[:250]
            items.append({
                'title':     entry.title,
                'link':      entry.link,
                'published': getattr(entry, 'published', ''),
                'summary':   summary,
                'lang':      'en',
            })
    except Exception as e:
        print(f'[en news error] {e}')

    cache_set(key, items)
    return items

# ────────────────────── routes ──────────────────────

@app.route('/')
def index():
    return render_template('index.html', currencies=CURRENCIES)

@app.route('/api/rates')
def api_rates():
    today_data     = fetch_current_rates()
    yesterday_data = fetch_yesterday_rates()

    if not today_data:
        return jsonify({'error': '환율 데이터를 불러올 수 없습니다.'}), 500

    today_raw     = today_data.get('rates', {})
    yesterday_raw = yesterday_data.get('rates', {}) if yesterday_data else {}
    result        = {}

    for code, info in CURRENCIES.items():
        if code not in today_raw:
            continue
        unit        = info['unit']
        rate_today  = (1 / today_raw[code]) * unit       # X 원 / unit
        rate_yday   = ((1 / yesterday_raw[code]) * unit) if code in yesterday_raw else None
        change      = round(rate_today - rate_yday, 2)   if rate_yday else None
        change_pct  = round((change / rate_yday) * 100, 3) if rate_yday and rate_yday != 0 else None

        result[code] = {
            'rate':       round(rate_today, 2),
            'unit':       unit,
            'change':     change,
            'change_pct': change_pct,
            'date':       today_data.get('date', ''),
        }

    return jsonify({'rates': result, 'date': today_data.get('date', '')})

@app.route('/api/historical/<currency>')
def api_historical(currency):
    if currency not in CURRENCIES:
        return jsonify({'error': '지원하지 않는 통화입니다.'}), 400

    data = fetch_historical_rates(currency, days=30)
    if not data:
        return jsonify({'error': '과거 데이터를 불러올 수 없습니다.'}), 500

    unit       = CURRENCIES[currency]['unit']
    chart_data = []
    for date, rates in sorted(data.get('rates', {}).items()):
        if currency in rates:
            chart_data.append({
                'date': date,
                'rate': round((1 / rates[currency]) * unit, 2),
            })

    return jsonify({'data': chart_data, 'currency': currency, 'unit': unit})

@app.route('/api/news/<currency>')
def api_news(currency):
    if currency not in CURRENCIES:
        return jsonify({'error': '지원하지 않는 통화입니다.'}), 400
    news = fetch_news(currency)
    return jsonify({'news': news, 'currency': currency})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
