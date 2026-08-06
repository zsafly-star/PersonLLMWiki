from extensions import db
from .models import Article

class ArticleService:
    @staticmethod
    def get_all():
        articles = Article.query.order_by(Article.updated_at.desc()).all()
        return [article.to_dict() for article in articles]

    @staticmethod
    def get_by_id(article_id):
        article = Article.query.get(article_id)
        return article.to_dict() if article else None

    @staticmethod
    def create(data):
        article = Article(
            title=data.get('title'),
            content=data.get('content', ''),
            folder_id=data.get('folder_id')
        )
        db.session.add(article)
        db.session.commit()
        return article.to_dict()

    @staticmethod
    def update(article_id, data):
        article = Article.query.get(article_id)
        if not article:
            return None

        if 'title' in data:
            article.title = data['title']
        if 'content' in data:
            article.content = data['content']
        if 'folder_id' in data:
            article.folder_id = data['folder_id']

        db.session.commit()
        return article.to_dict()

    @staticmethod
    def delete(article_id):
        article = Article.query.get(article_id)
        if not article:
            return False

        db.session.delete(article)
        db.session.commit()
        return True
