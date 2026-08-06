import requests
import time
from .models import WeatherConfig

_weather_cache = {}
_weather_cache_ttl = 1800


WEATHER_ICON_SVG = {
    # 晴天/多云 (100-104)
    '100': '天气_晴.svg',        # 晴
    '101': '天气_多云.svg',      # 多云
    '102': '天气_多云.svg',      # 晴转多云
    '103': '天气_多云.svg',      # 多云
    '104': '天气_阴天.svg',      # 阴
    
    # 夜间天气 (150-153) - 使用月亮图标或保持晴天图标
    '150': '天气_晴.svg',        # 晴（夜间）
    '151': '天气_多云.svg',      # 多云（夜间）
    '152': '天气_多云.svg',      # 多云（夜间）
    '153': '天气_阴天.svg',      # 阴（夜间）
    
    # 雨天 (300-399) - 区分不同强度
    '300': '天气_阵雨.svg',      # 阵雨
    '301': '天气_雷阵雨.svg',    # 雷阵雨
    '302': '天气_雨加冰雹.svg',  # 雷阵雨伴有冰雹
    '303': '天气_雷阵雨.svg',    # 雷暴
    '304': '天气_雷阵雨.svg',    # 强雷暴
    '305': '天气_小雨.svg',      # 小雨
    '306': '天气_中雨.svg',      # 中雨
    '307': '天气_大雨.svg',      # 大雨
    '308': '天气_特大暴雨.svg',  # 极端降雨
    '309': '天气_小雨.svg',      # 毛毛雨/细雨
    '310': '天气_暴雨.svg',      # 暴雨
    '311': '天气_暴雨.svg',      # 大暴雨
    '312': '天气_特大暴雨.svg',  # 特大暴雨
    '313': '天气_雨夹雪.svg',    # 冻雨
    '314': '天气_中雨.svg',      # 小到中雨
    '315': '天气_大雨.svg',      # 中到大雨
    '316': '天气_暴雨.svg',      # 大到暴雨
    '317': '天气_特大暴雨.svg',  # 暴雨到大暴雨
    '318': '天气_特大暴雨.svg',  # 大暴雨到特大暴雨
    '399': '天气_中雨.svg',      # 雨
    
    # 雪天 (400-499)
    '400': '天气_阵雪.svg',      # 阵雪
    '401': '天气_小雪.svg',      # 小雪
    '402': '天气_中雪.svg',      # 中雪
    '403': '天气_大雪.svg',      # 大雪
    '404': '天气_暴雪.svg',      # 暴雪
    '405': '天气_雨夹雪.svg',    # 雨夹雪
    '406': '天气_雨夹雪.svg',    # 雨雪天气
    '407': '天气_阵雪.svg',      # 阵雪
    '408': '天气_中雪.svg',      # 小到中雪
    '409': '天气_大雪.svg',      # 中到大雪
    '410': '天气_暴雪.svg',      # 大到暴雪
    '499': '天气_小雪.svg',      # 雪
    
    # 雾/霾 (500-515)
    '500': '天气_雾.svg',        # 雾
    '501': '天气_雾.svg',        # 薄雾
    '502': '天气_雾霾.svg',      # 霾
    '503': '天气_沙尘.svg',      # 沙尘
    '504': '天气_沙尘.svg',      # 浮尘
    '507': '天气_雾.svg',        # 雾
    '508': '天气_雾霾.svg',      # 霾
    '509': '天气_沙尘.svg',      # 沙尘暴
    '510': '天气_沙尘.svg',      # 强沙尘暴
    '511': '天气_雾.svg',        # 浓雾
    '512': '天气_雾.svg',        # 强浓雾
    '513': '天气_雾.svg',        # 轻雾
    '514': '天气_雾.svg',        # 大雾
    '515': '天气_雾.svg',        # 特强浓雾
    
    # 极端天气 (900-999)
    '900': '天气_晴.svg',        # 热 - 使用晴天图标
    '901': '天气_小雪.svg',      # 冷 - 使用雪天图标
    '999': '天气_晴.svg',        # 未知 - 默认使用晴天
}

WEATHER_ICON_PATH = '/static/icons/weather/'

DAY_LABELS = ['今天', '明天', '后天']


class WeatherService:

    @staticmethod
    def get_config():
        from extensions import db
        config = WeatherConfig.query.first()
        if not config:
            config = WeatherConfig()
            db.session.add(config)
            db.session.commit()
        return config.to_dict()

    @staticmethod
    def save_config(data):
        from extensions import db
        config = WeatherConfig.query.first()
        if not config:
            config = WeatherConfig()
            db.session.add(config)

        if 'api_host' in data:
            host = data['api_host'].strip()
            if host and not host.startswith('http'):
                host = 'https://' + host
            config.api_host = host
        if 'api_key' in data and data['api_key'] and data['api_key'] != '****':
            config.api_key = data['api_key']
        if 'city_name' in data:
            config.city_name = data['city_name']
        if 'location_id' in data:
            config.location_id = data['location_id']

        db.session.commit()
        return config.to_dict()

    @staticmethod
    def search_city(keyword, api_host=None, api_key=None):
        config = WeatherConfig.query.first()
        host = api_host or (config.api_host if config else 'https://devapi.qweather.com')
        if not host.startswith('http'):
            host = 'https://' + host
        token = api_key or (config.api_key if config else '')

        if not token:
            return {'code': 400, 'message': '请先配置和风天气 API Key'}

        url = f"{host.rstrip('/')}/geo/v2/city/lookup"
        params = {
            'location': keyword,
            'number': 10,
            'lang': 'zh',
            'key': token,
        }
        headers = {'X-QW-Api-Key': token}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            if data.get('code') == '200':
                cities = []
                for loc in data.get('location', []):
                    cities.append({
                        'id': loc.get('id'),
                        'name': loc.get('name'),
                        'adm1': loc.get('adm1'),
                        'adm2': loc.get('adm2'),
                        'country': loc.get('country'),
                    })
                return {'code': 200, 'data': cities}
            else:
                error_msg = data.get('code', '')
                if 'error' in data:
                    error_msg = data['error'].get('title', '') + ': ' + data['error'].get('detail', '')
                return {'code': 400, 'message': f"和风天气返回错误: {error_msg}"}
        except requests.RequestException as e:
            return {'code': 500, 'message': f'请求和风天气失败: {str(e)}'}

    @staticmethod
    def get_daily_forecast():
        global _weather_cache
        config = WeatherConfig.query.first()
        if not config or not config.api_key:
            return {'code': 400, 'message': '请先在设置中配置和风天气 API Key'}

        if not config.location_id:
            return {'code': 400, 'message': '请先在设置中选择城市'}

        cache_key = f"{config.location_id}:{config.api_key}"
        cached = _weather_cache.get(cache_key)
        if cached and (time.time() - cached['ts']) < _weather_cache_ttl:
            return cached['data']

        host = config.api_host or 'https://devapi.qweather.com'
        if not host.startswith('http'):
            host = 'https://' + host
        url = f"{host.rstrip('/')}/v7/weather/3d"
        params = {
            'location': config.location_id,
            'lang': 'zh',
            'unit': 'm',
            'key': config.api_key,
        }
        headers = {'X-QW-Api-Key': config.api_key}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            if data.get('code') == '200':
                daily_list = data.get('daily', [])
                result = []
                for i, day in enumerate(daily_list[:3]):
                    icon_day = day.get('iconDay', '100')
                    icon_path = WEATHER_ICON_PATH + WEATHER_ICON_SVG.get(icon_day, 'weather_晴.svg')
                    result.append({
                        'date': day.get('fxDate', ''),
                        'day_label': DAY_LABELS[i] if i < len(DAY_LABELS) else f'第{i+1}天',
                        'icon_day': icon_day,
                        'icon_path': icon_path,
                        'text_day': day.get('textDay', ''),
                        'text_night': day.get('textNight', ''),
                        'temp_max': day.get('tempMax', '--'),
                        'temp_min': day.get('tempMin', '--'),
                        'humidity': day.get('humidity', ''),
                        'wind_dir_day': day.get('windDirDay', ''),
                        'wind_scale_day': day.get('windScaleDay', ''),
                    })
                city_name = config.city_name or '未知'
                result_data = {
                    'code': 200,
                    'data': {
                        'city': city_name,
                        'update_time': data.get('updateTime', ''),
                        'forecast': result,
                    }
                }
                _weather_cache[cache_key] = {'ts': time.time(), 'data': result_data}
                return result_data
            else:
                error_msg = data.get('code', '')
                if 'error' in data:
                    error_msg = data['error'].get('title', '') + ': ' + data['error'].get('detail', '')
                return {'code': 400, 'message': f"和风天气返回错误: {error_msg}"}
        except requests.RequestException as e:
            return {'code': 500, 'message': f'请求和风天气失败: {str(e)}'}
