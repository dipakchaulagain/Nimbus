from flask import Blueprint, jsonify
from flask_login import login_required
from ..models.vm import VM

report_bp = Blueprint('report', __name__)


@report_bp.route('/summary')
@login_required
def summary():
    total = VM.query.count()
    powered_on = VM.query.filter_by(power_state='poweredOn').count()
    powered_off = VM.query.filter_by(power_state='poweredOff').count()
    return jsonify({
        'total_vms': total,
        'powered_on': powered_on,
        'powered_off': powered_off,
    })

