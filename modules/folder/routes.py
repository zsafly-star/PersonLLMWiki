from flask import Blueprint, request
from .services import FolderService
from common.response import success_response, error_response

folder_bp = Blueprint('folder', __name__, template_folder='templates')

@folder_bp.route('/api/folders', methods=['GET'])
def get_folders():
    folders = FolderService.get_all()
    return success_response(folders)

@folder_bp.route('/api/folders/<int:folder_id>', methods=['GET'])
def get_folder(folder_id):
    folder = FolderService.get_by_id(folder_id)
    if folder:
        return success_response(folder)
    return error_response('文件夹不存在', 404)

@folder_bp.route('/api/folders', methods=['POST'])
def create_folder():
    data = request.get_json()
    if not data or 'name' not in data:
        return error_response('缺少名称')

    folder = FolderService.create(data)
    return success_response(folder, '创建成功')

@folder_bp.route('/api/folders/<int:folder_id>', methods=['PUT'])
def update_folder(folder_id):
    data = request.get_json()
    folder = FolderService.update(folder_id, data)
    if folder:
        return success_response(folder, '更新成功')
    return error_response('文件夹不存在', 404)

@folder_bp.route('/api/folders/<int:folder_id>', methods=['DELETE'])
def delete_folder(folder_id):
    success = FolderService.delete(folder_id)
    if success:
        return success_response(None, '删除成功')
    return error_response('文件夹不存在', 404)
