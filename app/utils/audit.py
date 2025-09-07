from flask import request
from flask_login import current_user
from .. import db
from ..models.audit import AuditLog


def _get_source_ip() -> str:
    # Prefer X-Forwarded-For when behind proxies; fall back to remote_addr
    forwarded_for = request.headers.get('X-Forwarded-For') or request.headers.get('X-Real-IP')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or ''


def log_audit_event(action: str, entity: str = None, entity_id: str = None, details: str = None) -> None:
    try:
        user_id = None
        username = None
        if getattr(current_user, 'is_authenticated', False):
            try:
                user_id = int(current_user.get_id()) if current_user.get_id() is not None else None
            except Exception:
                # Some implementations may return a non-int id; store as None to avoid errors
                user_id = None
            username = getattr(current_user, 'username', None)

        audit = AuditLog(
            user_id=user_id,
            username=username,
            source_ip=_get_source_ip(),
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        )
        db.session.add(audit)
        # Do not commit here; let the surrounding request/handler own the transaction
    except Exception:
        # Never break the request flow due to audit logging
        db.session.rollback()
        try:
            # Best-effort attempt to continue without audit record
            pass
        except Exception:
            pass


