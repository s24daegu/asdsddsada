import calendar
import requests
import sqlite3
import os
from datetime import datetime
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exchange_data.db')

CITY_COORDS = {
    'USD': {'city': 'New York',      'lat': 40.71,  'lon': -74.01},
    'EUR': {'city': 'Paris',         'lat': 48.85,  'lon': 2.35},
    'JPY': {'city': 'Tokyo',         'lat': 35.68,  'lon': 139.69},
    'CNY': {'city': 'Beijing',       'lat': 39.91,  'lon': 116.39},
    'GBP': {'city': 'London',        'lat': 51.51,  'lon': -0.13},
    'AUD': {'city': 'Sydney',        'lat': -33.87, 'lon': 151.21},
    'CAD': {'city': 'Toronto',       'lat': 43.65,  'lon': -79.38},
    'CHF': {'city': 'Zurich',        'lat': 47.38,  'lon': 8.54},
    'HKD': {'city': 'Hong Kong',     'lat': 22.32,  'lon': 114.17},
    'SGD': {'city': 'Singapore',     'lat': 1.35,   'lon': 103.82},
    'THB': {'city': 'Bangkok',       'lat': 13.75,  'lon': 100.52},
    'INR': {'city': 'Mumbai',        'lat': 19.08,  'lon': 72.88},
    'MYR': {'city': 'Kuala Lumpur',  'lat': 3.14,   'lon': 101.69},
    'NZD': {'city': 'Auckland',      'lat': -36.87, 'lon': 174.77},
}

_weather_cache = {}
CACHE_TTL = 86400  # 24시간

def _cache_key(currency, month):
    return f'weather_{currency}_{month}'

def _cache_get(key):
    item = _weather_cache.get(key)
    if item and time.time() - item['ts'] < CACHE_TTL:
        return item['data']
    return None

def _cache_set(key, data):
    _weather_cache[key] = {'data': data, 'ts': time.time()}

def fetch_weather_month(currency, month):
    """
    Fetch average weather for a given month (1-12) using Open-Meteo historical archive.
    Averages data from the same month in 2022 and 2023 for stability.
    Returns dict: {temp_max, temp_min, temp_avg, precip_avg, city} or None.
    """
    key = _cache_key(currency, month)
    cached = _cache_get(key)
    if cached:
        return cached

    info = CITY_COORDS.get(currency)
    if not info:
        return None

    lat, lon = info['lat'], info['lon']
    city = info['city']

    all_temps_max = []
    all_temps_min = []
    all_precips = []

    # Fetch same month from 2022 and 2023
    for year in [2022, 2023]:
        last_day = calendar.monthrange(year, month)[1]
        start = f'{year}-{month:02d}-01'
        end   = f'{year}-{month:02d}-{last_day}'

        url = (
            f'https://archive-api.open-meteo.com/v1/archive'
            f'?latitude={lat}&longitude={lon}'
            f'&start_date={start}&end_date={end}'
            f'&daily=temperature_2m_max,temperature_2m_min,precipitation_sum'
            f'&timezone=auto'
        )

        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            daily = data.get('daily', {})

            temps_max = [v for v in daily.get('temperature_2m_max', []) if v is not None]
            temps_min = [v for v in daily.get('temperature_2m_min', []) if v is not None]
            precips   = [v for v in daily.get('precipitation_sum', []) if v is not None]

            all_temps_max.extend(temps_max)
            all_temps_min.extend(temps_min)
            all_precips.extend(precips)
        except Exception as e:
            print(f'[weather error] {currency} {year}-{month}: {e}')

    if not all_temps_max:
        # Try DB fallback
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT temp_max, temp_min, precip_sum FROM weather_cache WHERE city=? ORDER BY date DESC LIMIT 1',
                      (f'{currency}_m{month}',))
            row = c.fetchone()
            conn.close()
            if row:
                return {
                    'city': city, 'month': month,
                    'temp_max': row[0], 'temp_min': row[1],
                    'temp_avg': round((row[0]+row[1])/2, 1),
                    'precip_avg': row[2],
                }
        except Exception:
            pass
        return None

    result = {
        'city':       city,
        'month':      month,
        'temp_max':   round(sum(all_temps_max) / len(all_temps_max), 1),
        'temp_min':   round(sum(all_temps_min) / len(all_temps_min), 1),
        'temp_avg':   round((sum(all_temps_max) + sum(all_temps_min)) / (len(all_temps_max) + len(all_temps_min)), 1),
        'precip_avg': round(sum(all_precips) / len(all_precips), 1) if all_precips else 0,
    }

    _cache_set(key, result)

    # Also store in SQLite for persistence
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            'INSERT OR REPLACE INTO weather_cache (city, date, temp_max, temp_min, precip_sum) VALUES (?, ?, ?, ?, ?)',
            (f'{currency}_m{month}', datetime.now().strftime('%Y-%m-%d'), result['temp_max'], result['temp_min'], result['precip_avg'])
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[weather db error] {e}')

    return result

def get_weather_score(currency, month):
    """
    Return weather score 0-40.
    Scoring logic:
    - Comfortable temperature (15-28°C avg): up to 25 pts
    - Low precipitation (< 3mm/day avg): up to 15 pts
    """
    data = fetch_weather_month(currency, month)
    if not data:
        return 15  # neutral fallback

    temp = data['temp_avg']
    precip = data['precip_avg']

    # Temperature score (0-25)
    if 18 <= temp <= 26:
        temp_score = 25
    elif 15 <= temp < 18 or 26 < temp <= 30:
        temp_score = 20
    elif 10 <= temp < 15 or 30 < temp <= 35:
        temp_score = 12
    elif 5 <= temp < 10 or 35 < temp <= 38:
        temp_score = 6
    else:
        temp_score = 2

    # Precipitation score (0-15)
    if precip < 2:
        precip_score = 15
    elif precip < 4:
        precip_score = 11
    elif precip < 7:
        precip_score = 7
    elif precip < 12:
        precip_score = 3
    else:
        precip_score = 0

    return temp_score + precip_score
