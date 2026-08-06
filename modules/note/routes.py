from flask import Blueprint, render_template

note_bp = Blueprint('note', __name__, template_folder='templates')

@note_bp.route('/note')
def note():
    return render_template('note.html', active_view='note')
