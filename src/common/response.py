from flask import jsonify

def success_response(data=None, message='操作成功'):
    return jsonify({
        'code': 200,
        'message': message,
        'data': data
    })

def error_response(message='操作失败', code=400):
    return jsonify({
        'code': code,
        'message': message,
        'data': None
    })
