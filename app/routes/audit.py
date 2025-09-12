from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.audit import AuditLog


audit_bp = Blueprint('audit', __name__)


@audit_bp.route('/')
@login_required
@require_roles('superadmin')
def list_audit():
    logs = AuditLog.query.order_by(AuditLog.occurred_at.desc()).limit(500).all()
    return render_template('audit/list.html', logs=logs)


@audit_bp.route('/api')
@login_required
@require_roles('superadmin')
def audit_api():
    q = AuditLog.query
    action = (request.args.get('action') or '').strip()
    username = (request.args.get('username') or '').strip()
    entity = (request.args.get('entity') or '').strip()
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if username:
        q = q.filter(AuditLog.username.ilike(f"%{username}%"))
    if entity:
        q = q.filter(AuditLog.entity.ilike(f"%{entity}%"))
    logs = q.order_by(AuditLog.occurred_at.desc()).limit(1000).all()
    return jsonify([
        {
            'id': log.id,
            'occurred_at': log.occurred_at.isoformat() if log.occurred_at else None,
            'user_id': log.user_id,
            'username': log.username,
            'source_ip': log.source_ip,
            'action': log.action,
            'entity': log.entity,
            'entity_id': log.entity_id,
            'details': log.details,
        }
        for log in logs
    ])


@audit_bp.route('/api/recent')
@login_required
def recent_audit_logs():
    """API endpoint for recent audit logs (dashboard use)"""
    limit = request.args.get('limit', 10, type=int)
    logs = AuditLog.query.order_by(AuditLog.occurred_at.desc()).limit(limit).all()
    return jsonify([
        {
            'id': log.id,
            'timestamp': log.occurred_at.isoformat() if log.occurred_at else None,
            'user_id': log.user_id,
            'username': log.username,
            'action': log.action,
            'entity': log.entity,
            'entity_id': log.entity_id,
            'details': log.details,
        }
        for log in logs
    ])


