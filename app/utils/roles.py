from functools import wraps
from flask import abort
from flask_login import current_user


def require_roles(*allowed_roles: str):
    """Decorator to require the current user to have one of the allowed roles.

    Usage: @require_roles('editor', 'superadmin')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not getattr(current_user, 'is_authenticated', False):
                abort(401)
            role = getattr(current_user, 'role', None)
            if role not in allowed_roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


