from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.vm import VM
from ..models.owner import Owner
from ..models.tag import Tag
from .. import db
from ..utils.audit import log_audit_event

vm_bp = Blueprint('vm', __name__)


@vm_bp.route('/')
@login_required
def list_vms():
    vms = VM.query.order_by(VM.name.asc()).all()
    return render_template('vms/list.html', vms=vms)


@vm_bp.route('/api')
@login_required
def vms_api():
    q = VM.query
    name = request.args.get('name')
    if name:
        q = q.filter(VM.name.ilike(f"%{name}%"))
    data = [
        {
            'id': vm.id,
            'name': vm.name,
            'cpu': vm.cpu,
            'memory_mb': vm.memory_mb,
            'guest_os': vm.guest_os,
            'power_state': vm.power_state,
            'hypervisor': vm.hypervisor,
        }
        for vm in q.limit(500).all()
    ]
    return jsonify(data)


@vm_bp.route('/api/<string:vm_id>')
@login_required
def vm_detail(vm_id: str):
    vm = VM.query.get_or_404(vm_id)
    return jsonify({
        'id': vm.id,
        'name': vm.name,
        'cpu': vm.cpu,
        'memory_mb': vm.memory_mb,
        'guest_os': vm.guest_os,
        'power_state': vm.power_state,
        'hypervisor': vm.hypervisor,
        'owners': [ { 'id': o.id, 'name': o.name, 'email': o.email, 'department': o.department } for o in vm.owners ],
        'tags': [ { 'id': t.id, 'name': t.name } for t in vm.tags ],
        'disks': [ { 'label': d.label, 'size_gb': float(d.size_gb or 0) } for d in vm.disks ],
        'nics': [ { 'label': n.label, 'mac': n.mac, 'network': n.network, 'connected': n.connected, 'ip_addresses': n.ip_addresses } for n in vm.nics ],
    })


@vm_bp.route('/api/<string:vm_id>/owners', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def assign_vm_owners(vm_id: str):
    vm = VM.query.get_or_404(vm_id)
    data = request.get_json() or {}
    emails = data.get('emails') or []
    if isinstance(emails, str):
        emails = [e.strip() for e in emails.split(',') if e.strip()]
    new_owners = []
    for email in emails:
        owner = Owner.query.filter(Owner.email.ilike(email)).first()
        if not owner:
            # create minimal owner with email as name if not found
            owner = Owner(name=email.split('@')[0], email=email)
            db.session.add(owner)
            db.session.flush()
        new_owners.append(owner)
    vm.owners = new_owners
    detail_owners = ','.join([o.email for o in vm.owners])
    log_audit_event(action='vm.assign_owners', entity='vm', entity_id=vm.id, details=f"owners={detail_owners}")
    db.session.commit()
    return jsonify({'status': 'ok', 'owners': [ {'id': o.id, 'name': o.name, 'email': o.email } for o in vm.owners ]})


@vm_bp.route('/<string:vm_id>/owners/unassign', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def unassign_vm_owner(vm_id: str):
    vm = VM.query.get_or_404(vm_id)
    data = request.get_json() or {}
    email = (data.get('email') or '').strip()
    reason = (data.get('reason') or '').strip()
    if not email:
        return jsonify({'error': 'email is required'}), 400
    # Find owner by email in current owners
    owner = None
    for o in vm.owners:
        if o.email.lower() == email.lower():
            owner = o
            break
    if not owner:
        return jsonify({'error': 'owner not assigned'}), 404
    # Remove and persist
    vm.owners = [o for o in vm.owners if o.id != owner.id]
    log_audit_event(
        action='vm.unassign_owner',
        entity='vm',
        entity_id=vm.id,
        details=f"email={owner.email}; reason={reason}"
    )
    db.session.commit()
    return jsonify({'status': 'ok', 'owners': [ {'id': o.id, 'name': o.name, 'email': o.email, 'department': o.department } for o in vm.owners ]})

@vm_bp.route('/api/<string:vm_id>/tags', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def assign_vm_tags(vm_id: str):
    vm = VM.query.get_or_404(vm_id)
    data = request.get_json() or {}
    tags = data.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',') if t.strip()]
    new_tags = []
    for name in tags:
        tag = Tag.query.filter(Tag.name.ilike(name)).first()
        if not tag:
            tag = Tag(name=name)
            db.session.add(tag)
            db.session.flush()
        new_tags.append(tag)
    vm.tags = new_tags
    detail_tags = ','.join([t.name for t in vm.tags])
    log_audit_event(action='vm.assign_tags', entity='vm', entity_id=vm.id, details=f"tags={detail_tags}")
    db.session.commit()
    return jsonify({'status': 'ok', 'tags': [ {'id': t.id, 'name': t.name } for t in vm.tags ]})


@vm_bp.route('/api/<string:vm_id>/tags/unassign', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def unassign_vm_tag(vm_id: str):
    vm = VM.query.get_or_404(vm_id)
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'name is required'}), 400
    # Remove tag by name if present
    remaining = []
    removed = None
    for t in vm.tags:
        if t.name.lower() == name.lower():
            removed = t
        else:
            remaining.append(t)
    if not removed:
        return jsonify({'error': 'tag not assigned'}), 404
    vm.tags = remaining
    log_audit_event(action='vm.unassign_tag', entity='vm', entity_id=vm.id, details=f"tag={removed.name}")
    db.session.commit()
    return jsonify({'status': 'ok', 'tags': [ {'id': t.id, 'name': t.name } for t in vm.tags ]})

