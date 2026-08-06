from datetime import datetime
from extensions import db


class WikiPage(db.Model):
    __tablename__ = 'wiki_page'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    kind = db.Column(db.String(20), default='concept')
    summary = db.Column(db.Text, default='')
    body = db.Column(db.Text, default='')
    sources = db.Column(db.Text, default='[]')
    confidence = db.Column(db.Float, default=0.0)
    links = db.Column(db.Text, default='[]')
    provenance_refs = db.Column(db.Text, default='[]')
    content_hash = db.Column(db.String(64), default='')
    review_status = db.Column(db.String(20), default='approved')
    author = db.Column(db.String(100), default='')  # Phase 3: 提交者标识
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'title': self.title,
            'slug': self.slug,
            'kind': self.kind,
            'summary': self.summary,
            'body': self.body,
            'sources': json.loads(self.sources) if self.sources else [],
            'confidence': self.confidence,
            'links': json.loads(self.links) if self.links else [],
            'provenance_refs': json.loads(self.provenance_refs) if self.provenance_refs else [],
            'review_status': self.review_status,
            'author': self.author,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
