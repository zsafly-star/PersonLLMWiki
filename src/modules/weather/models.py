from datetime import datetime
from extensions import db


class WeatherConfig(db.Model):
    __tablename__ = 'weather_config'

    id = db.Column(db.Integer, primary_key=True)
    api_host = db.Column(db.String(500), default='https://devapi.qweather.com')
    api_key = db.Column(db.String(500), default='')
    city_name = db.Column(db.String(100), default='')
    location_id = db.Column(db.String(50), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'api_host': self.api_host,
            'api_key': self._mask_key(self.api_key) if self.api_key else '',
            'city_name': self.city_name,
            'location_id': self.location_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_dict_with_key(self):
        return {
            'id': self.id,
            'api_host': self.api_host,
            'api_key': self.api_key,
            'city_name': self.city_name,
            'location_id': self.location_id,
        }

    @staticmethod
    def _mask_key(key):
        if not key or len(key) < 8:
            return '****'
        return key[:4] + '****' + key[-4:]
