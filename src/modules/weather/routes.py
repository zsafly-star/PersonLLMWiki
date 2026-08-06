from flask import Blueprint, request
from common.response import success_response, error_response
from .weather_service import WeatherService

weather_bp = Blueprint('weather', __name__)


@weather_bp.route('/api/weather/config', methods=['GET'])
def get_weather_config():
    config = WeatherService.get_config()
    return success_response(config)


@weather_bp.route('/api/weather/config', methods=['POST'])
def save_weather_config():
    data = request.get_json()
    if not data:
        return error_response('缺少数据')
    config = WeatherService.save_config(data)
    return success_response(config, '保存成功')


@weather_bp.route('/api/weather/city/search', methods=['GET'])
def search_city():
    keyword = request.args.get('keyword', '')
    if not keyword:
        return error_response('请输入城市名称')
    result = WeatherService.search_city(keyword)
    if result['code'] == 200:
        return success_response(result['data'])
    return error_response(result.get('message', '搜索失败'), result.get('code', 400))


@weather_bp.route('/api/weather/daily', methods=['GET'])
def get_daily_forecast():
    result = WeatherService.get_daily_forecast()
    if result['code'] == 200:
        return success_response(result['data'])
    return error_response(result.get('message', '获取天气失败'), result.get('code', 400))
