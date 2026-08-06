from extensions import db
from .models import Folder

class FolderService:
    @staticmethod
    def get_all():
        folders = Folder.query.order_by(Folder.name.asc()).all()
        return [folder.to_dict() for folder in folders]

    @staticmethod
    def get_by_id(folder_id):
        folder = Folder.query.get(folder_id)
        return folder.to_dict() if folder else None

    @staticmethod
    def create(data):
        folder = Folder(
            name=data.get('name'),
            parent_id=data.get('parent_id')
        )
        db.session.add(folder)
        db.session.commit()
        return folder.to_dict()

    @staticmethod
    def update(folder_id, data):
        folder = Folder.query.get(folder_id)
        if not folder:
            return None

        if 'name' in data:
            folder.name = data['name']
        if 'parent_id' in data:
            folder.parent_id = data['parent_id']

        db.session.commit()
        return folder.to_dict()

    @staticmethod
    def delete(folder_id):
        folder = Folder.query.get(folder_id)
        if not folder:
            return False

        db.session.delete(folder)
        db.session.commit()
        return True
