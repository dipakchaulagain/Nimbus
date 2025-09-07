from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from ..models.admin import Admin
from ..utils.audit import log_audit_event
from .. import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Admin.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            # audit
            log_audit_event(action='auth.login', entity='admin', entity_id=user.id, details=None)
            db.session.commit()
            return redirect(url_for('index'))
        flash('Invalid credentials', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    # audit before losing user context
    try:
        log_audit_event(action='auth.logout', entity='admin', entity_id=None, details=None)
        db.session.commit()
    finally:
        pass
    logout_user()
    return redirect(url_for('auth.login'))

