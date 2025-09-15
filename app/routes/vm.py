from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.vm import VM
from ..models.owner import Owner
from ..models.tag import Tag
from .. import db
from ..utils.audit import log_audit_event
from sqlalchemy import func

vm_bp = Blueprint('vm', __name__)


@vm_bp.route('/')
@login_required
def list_vms():
    vms = VM.query.order_by(VM.name.asc()).all()
    owners = Owner.query.order_by(Owner.name.asc()).all()
    tags = Tag.query.order_by(Tag.name.asc()).all()
    return render_template('vms/list.html', vms=vms, owners=owners, tags=tags)


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


@vm_bp.route('/api/stats')
@login_required
def vm_stats():
    """API endpoint to provide VM statistics for dashboard"""
    
    # Total VM count
    total_vms = VM.query.count()
    
    # Power state statistics
    power_stats = db.session.query(
        VM.power_state,
        func.count(VM.id).label('count')
    ).group_by(VM.power_state).all()
    
    # Convert power stats to dictionary
    power_on = 0
    power_off = 0
    for stat in power_stats:
        if stat.power_state and stat.power_state.lower() in ['poweredon', 'powered on', 'running']:
            power_on = stat.count
        elif stat.power_state and stat.power_state.lower() in ['poweredoff', 'powered off', 'stopped']:
            power_off = stat.count
    
    # OS statistics
    os_stats = db.session.query(
        VM.guest_os,
        VM.power_state,
        func.count(VM.id).label('count')
    ).group_by(VM.guest_os, VM.power_state).all()
    
    # Categorize OS types and count by power state
    windows_total = 0
    windows_on = 0
    windows_off = 0
    linux_total = 0
    linux_on = 0
    linux_off = 0
    other_total = 0
    other_on = 0
    other_off = 0
    
    for stat in os_stats:
        guest_os = stat.guest_os or ''
        power_state = stat.power_state or ''
        count = stat.count
        
        # Categorize OS
        is_windows = 'windows' in guest_os.lower()
        is_linux = any(os_type in guest_os.lower() for os_type in ['linux', 'ubuntu', 'centos', 'redhat', 'debian', 'fedora'])
        
        # Categorize power state
        is_on = power_state.lower() in ['poweredon', 'powered on', 'running']
        is_off = power_state.lower() in ['poweredoff', 'powered off', 'stopped']
        
        if is_windows:
            windows_total += count
            if is_on:
                windows_on += count
            elif is_off:
                windows_off += count
        elif is_linux:
            linux_total += count
            if is_on:
                linux_on += count
            elif is_off:
                linux_off += count
        else:
            other_total += count
            if is_on:
                other_on += count
            elif is_off:
                other_off += count
    
    # Additional metrics
    from ..models.owner import Owner
    from ..models.tag import Tag
    from ..models.vcenter import VCenterConfig
    
    # Calculate average CPU and memory
    avg_cpu = db.session.query(func.avg(VM.cpu)).scalar() or 0
    avg_memory_mb = db.session.query(func.avg(VM.memory_mb)).scalar() or 0
    avg_memory_gb = avg_memory_mb / 1024 if avg_memory_mb else 0
    
    # Count unique hypervisors from VM records (excluding null/empty values)
    unique_hypervisors = db.session.query(func.count(func.distinct(VM.hypervisor)))\
        .filter(VM.hypervisor.isnot(None), VM.hypervisor != '').scalar() or 0
    
    # Get hypervisor breakdown (hypervisor name -> VM count)
    hypervisor_stats = db.session.query(
        VM.hypervisor,
        func.count(VM.id).label('vm_count')
    ).filter(VM.hypervisor.isnot(None), VM.hypervisor != '')\
     .group_by(VM.hypervisor)\
     .order_by(func.count(VM.id).desc())\
     .limit(10).all()
    
    hypervisor_breakdown = [
        {'hypervisor': stat.hypervisor, 'vm_count': stat.vm_count}
        for stat in hypervisor_stats
    ]
    
    # Count active owners and tags
    total_owners = Owner.query.count()
    total_tags = Tag.query.count()
    total_hypervisors = VCenterConfig.query.filter_by(enabled=True).count()
    
    return jsonify({
        'total_vms': total_vms,
        'power_stats': {
            'powered_on': power_on,
            'powered_off': power_off
        },
        'os_breakdown': {
            'windows': {
                'total': windows_total,
                'powered_on': windows_on,
                'powered_off': windows_off
            },
            'linux': {
                'total': linux_total,
                'powered_on': linux_on,
                'powered_off': linux_off
            },
            'other': {
                'total': other_total,
                'powered_on': other_on,
                'powered_off': other_off
            }
        },
        'additional_metrics': {
            'avg_cpu': round(avg_cpu, 1),
            'avg_memory_gb': round(avg_memory_gb, 1),
            'total_owners': total_owners,
            'total_tags': total_tags,
            'total_hypervisors': total_hypervisors,
            'unique_hypervisors': unique_hypervisors
        },
        'hypervisor_breakdown': hypervisor_breakdown
    })

