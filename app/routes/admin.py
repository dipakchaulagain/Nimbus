from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.admin import Admin
from .. import db


admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@login_required
@require_roles('superadmin')
def list_admins():
    admins = Admin.query.order_by(Admin.username.asc()).all()
    return render_template('admins/list.html', admins=admins)


@admin_bp.route('/api', methods=['POST'])
@login_required
@require_roles('superadmin')
def admin_create():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip()
    password = (data.get('password') or '').strip()
    role = (data.get('role') or 'viewer').strip()
    if not username or not email or not password:
        return jsonify({'error': 'username, email, password required'}), 400
    a = Admin(username=username, email=email, role=role)
    a.set_password(password)
    db.session.add(a)
    db.session.commit()
    return jsonify({'id': a.id}), 201


@admin_bp.route('/api/<int:admin_id>', methods=['PUT'])
@login_required
def admin_update(admin_id: int):
    a = Admin.query.get_or_404(admin_id)
    data = request.get_json() or {}
    if 'username' in data: a.username = (data['username'] or '').strip()
    if 'email' in data: a.email = (data['email'] or '').strip()
    if 'role' in data: a.role = (data['role'] or a.role).strip()
    if 'password' in data and data['password']:
        a.set_password(data['password'])
    db.session.commit()
    return jsonify({'status': 'ok'})


@admin_bp.route('/api/<int:admin_id>', methods=['DELETE'])
@login_required
def admin_delete(admin_id: int):
    a = Admin.query.get_or_404(admin_id)
    db.session.delete(a)
    db.session.commit()
    return jsonify({'status': 'deleted'})


