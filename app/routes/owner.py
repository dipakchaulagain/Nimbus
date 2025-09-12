from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.owner import Owner
from ..utils.audit import log_audit_event
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
        { 
            'id': o.id, 
            'name': o.name, 
            'email': o.email, 
            'department': o.department,
            'vm_count': len(o.vms)
        }
        for o in owners
    ])


@owner_bp.route('/api', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def owners_api_create():
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    department = data.get('department', '').strip()
    if not name or not email:
        return jsonify({'error': 'Name and Email are required'}), 400
    o = Owner(name=name, email=email, department=department)
    db.session.add(o)
    log_audit_event(action='owner.create', entity='owner', entity_id=o.id, details=f"name={o.name}, email={o.email}")
    db.session.commit()
    return jsonify({'id': o.id}), 201


@owner_bp.route('/api/<int:owner_id>', methods=['PUT'])
@login_required
@require_roles('editor', 'superadmin')
def owners_api_update(owner_id: int):
    o = Owner.query.get_or_404(owner_id)
    data = request.get_json() or {}
    if 'name' in data: o.name = (data['name'] or '').strip()
    if 'email' in data: o.email = (data['email'] or '').strip()
    if 'department' in data: o.department = (data['department'] or '').strip()
    log_audit_event(action='owner.update', entity='owner', entity_id=o.id, details=f"name={o.name}, email={o.email}")
    db.session.commit()
    return jsonify({'status': 'ok'})


@owner_bp.route('/api/<int:owner_id>', methods=['DELETE'])
@login_required
@require_roles('editor', 'superadmin')
def owners_api_delete(owner_id: int):
    o = Owner.query.get_or_404(owner_id)
    oid = o.id
    oname = o.name
    oemail = o.email
    db.session.delete(o)
    log_audit_event(action='owner.delete', entity='owner', entity_id=oid, details=f"name={oname}, email={oemail}")
    db.session.commit()
    return jsonify({'status': 'deleted'})


@owner_bp.route('/api/<int:owner_id>/vms')
@login_required
def owner_vms(owner_id: int):
    """API endpoint to get VMs assigned to a specific owner"""
    owner = Owner.query.get_or_404(owner_id)
    return jsonify([
        {
            'id': vm.id,
            'name': vm.name,
            'cpu': vm.cpu,
            'memory_mb': vm.memory_mb,
            'guest_os': vm.guest_os,
            'power_state': vm.power_state,
            'hypervisor': vm.hypervisor,
            'created_at': vm.created_at.isoformat() if vm.created_at else None,
            'updated_at': vm.updated_at.isoformat() if vm.updated_at else None,
        }
        for vm in owner.vms
    ])

