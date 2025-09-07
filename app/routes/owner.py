from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..models.owner import Owner
from .. import db

owner_bp = Blueprint('owner', __name__)


@owner_bp.route('/')
@login_required
def list_owners():
    owners = Owner.query.order_by(Owner.name.asc()).all()
    return render_template('owners/list.html', owners=owners)


@owner_bp.route('/api', methods=['GET'])
@login_required
def owners_api_list():
    owners = Owner.query.order_by(Owner.name.asc()).all()
    return jsonify([
        { 'id': o.id, 'name': o.name, 'email': o.email, 'department': o.department }
        for o in owners
    ])


@owner_bp.route('/api', methods=['POST'])
@login_required
def owners_api_create():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    department = data.get('department', '').strip()
    if not name or not email:
        return jsonify({'error': 'Name and Email are required'}), 400
    o = Owner(name=name, email=email, department=department)
    db.session.add(o)
    db.session.commit()
    return jsonify({'id': o.id}), 201


@owner_bp.route('/api/<int:owner_id>', methods=['PUT'])
@login_required
def owners_api_update(owner_id: int):
    o = Owner.query.get_or_404(owner_id)
    data = request.get_json() or {}
    if 'name' in data: o.name = (data['name'] or '').strip()
    if 'email' in data: o.email = (data['email'] or '').strip()
    if 'department' in data: o.department = (data['department'] or '').strip()
    db.session.commit()
    return jsonify({'status': 'ok'})


@owner_bp.route('/api/<int:owner_id>', methods=['DELETE'])
@login_required
def owners_api_delete(owner_id: int):
    o = Owner.query.get_or_404(owner_id)
    db.session.delete(o)
    db.session.commit()
    return jsonify({'status': 'deleted'})

