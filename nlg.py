# nlg.py — Korean natural language generation for travel recommendations

MONTH_KO = {
    1:'1월', 2:'2월', 3:'3월', 4:'4월', 5:'5월', 6:'6월',
    7:'7월', 8:'8월', 9:'9월', 10:'10월', 11:'11월', 12:'12월'
}

SEASON_KO = {
    (12,1,2): '겨울', (3,4,5): '봄', (6,7,8): '여름', (9,10,11): '가을'
}

def _get_season(month):
    for months, name in SEASON_KO.items():
        if month in months:
            return name
    return ''

def _weather_sentence(city, weather_data, month):
    if not weather_data:
        return f'{city}의 날씨 정보를 불러오지 못했습니다.'

    temp = weather_data.get('temp_avg', 20)
    precip = weather_data.get('precip_avg', 0)
    season = _get_season(month)
    month_ko = MONTH_KO.get(month, f'{month}월')

    if temp >= 30:
        temp_desc = f'기온이 {temp}°C로 매우 더운 편'
    elif temp >= 24:
        temp_desc = f'기온이 {temp}°C로 따뜻하고 활동하기 좋은 날씨'
    elif temp >= 18:
        temp_desc = f'기온이 {temp}°C로 쾌적한 날씨'
    elif temp >= 10:
        temp_desc = f'기온이 {temp}°C로 선선한 날씨'
    elif temp >= 0:
        temp_desc = f'기온이 {temp}°C로 쌀쌀한 편'
    else:
        temp_desc = f'기온이 {temp}°C로 매우 추운 편'

    if precip < 2:
        precip_desc = '강수량이 적어 야외 활동에 최적'
    elif precip < 5:
        precip_desc = '가끔 비가 오지만 여행에는 크게 지장 없음'
    elif precip < 10:
        precip_desc = '비가 자주 오므로 우산 필수'
    else:
        precip_desc = '우기로 강한 비가 잦음, 실내 활동 위주 권장'

    return f'{city}는 {month_ko} {season}에 {temp_desc}이며, {precip_desc}합니다.'

def _trend_sentence(currency, trend_data):
    if not trend_data:
        return ''

    change = trend_data.get('change_pct', 0)
    direction = trend_data.get('direction', 'flat')
    recent = trend_data.get('recent_7d_pct', 0)

    currency_ko = {
        'USD':'달러', 'EUR':'유로', 'JPY':'엔화', 'CNY':'위안화',
        'GBP':'파운드', 'AUD':'호주달러', 'CAD':'캐나다달러', 'CHF':'프랑',
        'HKD':'홍콩달러', 'SGD':'싱가포르달러', 'THB':'바트화',
        'INR':'루피화', 'MYR':'링깃', 'NZD':'뉴질랜드달러'
    }.get(currency, currency)

    if direction == 'up':
        base = f'최근 30일간 원화 대비 {currency_ko}가 약세를 보이며 여행 비용이 유리해졌습니다'
    elif direction == 'down':
        base = f'최근 30일간 원화 대비 {currency_ko}가 강세를 보여 여행 비용 부담이 다소 있습니다'
    else:
        base = f'환율이 비교적 안정적으로 유지되고 있습니다'

    if abs(recent) > 1:
        if recent > 0:
            momentum = f' 특히 최근 7일 사이 {abs(recent):.1f}% 유리한 방향으로 움직이고 있습니다.'
        else:
            momentum = f' 최근 7일간 {abs(recent):.1f}% 부담이 커졌습니다.'
    else:
        momentum = '.'

    return base + momentum

def _sentiment_sentence(sentiment_label_tuple):
    label, cls = sentiment_label_tuple if isinstance(sentiment_label_tuple, tuple) else (sentiment_label_tuple, 'neutral')

    templates = {
        'very_positive': '현지 관련 뉴스도 매우 긍정적으로, 안전하고 활기찬 여행을 기대할 수 있습니다.',
        'positive':      '현지 관련 뉴스가 대체로 긍정적이어서 안정적인 여행 환경을 예상할 수 있습니다.',
        'neutral':       '현재 특별히 우려할 만한 이슈는 없습니다.',
        'negative':      '최근 관련 뉴스에 다소 부정적인 내용이 있으니 여행 전 현지 상황을 확인하세요.',
        'very_negative': '현지 상황이 불안정하다는 뉴스가 많으므로 여행 계획을 신중히 검토하시기 바랍니다.',
    }
    return templates.get(cls, templates['neutral'])

def _overall_sentence(total, city, month):
    month_ko = MONTH_KO.get(month, f'{month}월')

    if total >= 80:
        return f'{month_ko} {city} 여행은 날씨·환율·현지 분위기 모든 면에서 최적의 타이밍입니다! 강력 추천합니다.'
    elif total >= 65:
        return f'{month_ko}은 {city} 여행을 떠나기 좋은 시기입니다. 만족스러운 여행이 될 것입니다.'
    elif total >= 50:
        return f'{month_ko} {city} 여행은 무난한 선택입니다. 몇 가지 사항만 주의하면 즐거운 여행이 가능합니다.'
    elif total >= 35:
        return f'{month_ko}은 {city} 여행의 최적 시기는 아닙니다. 다른 달을 고려해보는 것도 좋습니다.'
    else:
        return f'{month_ko} {city} 여행은 권장하기 어렵습니다. 여행 시기를 다시 검토해보세요.'

def generate_recommendation(score_result):
    """
    Generate Korean travel recommendation text from compute_all_scores() result dict.
    Returns dict with: summary, weather_text, trend_text, sentiment_text, tip
    """
    currency    = score_result.get('currency', '')
    month       = score_result.get('month', 1)
    city        = score_result.get('city', '')
    scores      = score_result.get('scores', {})
    total       = scores.get('total', 50)
    weather_data   = score_result.get('weather_data')
    trend_data     = score_result.get('trend_data')
    sent_label     = score_result.get('sentiment_label', ('중립', 'neutral'))

    summary      = _overall_sentence(total, city, month)
    weather_text = _weather_sentence(city, weather_data, month)
    trend_text   = _trend_sentence(currency, trend_data)
    sentiment_text = _sentiment_sentence(sent_label)

    # Travel tip based on lowest scoring component
    w = scores.get('weather', 20)
    t = scores.get('trend', 10)
    s = scores.get('sentiment', 10)
    se = scores.get('season', 10)

    min_comp = min([(w,'weather'),(t,'trend'),(s,'sentiment'),(se,'season')], key=lambda x: x[0])
    tips = {
        'weather':   f'{city} {MONTH_KO.get(month)}는 날씨 컨디션에 주의가 필요합니다. 현지 기상 예보를 꼭 확인하세요.',
        'trend':     '환율 변동이 있으므로 여행 전 환전 타이밍을 전략적으로 잡으세요.',
        'sentiment': '현지 뉴스를 미리 살펴보고 여행 일정을 유연하게 준비하세요.',
        'season':    f'{MONTH_KO.get(month)}은 {city}의 비수기 또는 혼잡기일 수 있습니다. 예약을 서두르거나 대안 일정을 검토하세요.',
    }
    tip = tips.get(min_comp[1], '')

    return {
        'summary':        summary,
        'weather_text':   weather_text,
        'trend_text':     trend_text,
        'sentiment_text': sentiment_text,
        'tip':            tip,
    }
