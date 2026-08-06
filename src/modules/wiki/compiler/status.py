import threading

_status = {
    'running': False,
    'progress': '',
    'errors': [],
    'completed': 0,
    'total': 0,
}

_lock = threading.Lock()


def get_compile_status():
    with _lock:
        return dict(_status)


def is_running():
    with _lock:
        return _status['running']


def reset(progress=''):
    with _lock:
        _status['running'] = True
        _status['progress'] = progress
        _status['errors'] = []
        _status['completed'] = 0
        _status['total'] = 0


def set_progress(msg):
    with _lock:
        _status['progress'] = msg


def add_error(msg):
    with _lock:
        _status['errors'].append(msg)


def increment_completed(n=1):
    with _lock:
        _status['completed'] += n


def set_total(n):
    with _lock:
        _status['total'] = n


def finish(progress=''):
    with _lock:
        _status['progress'] = progress
        _status['running'] = False


def already_running():
    with _lock:
        if _status['running']:
            return True
        return False
