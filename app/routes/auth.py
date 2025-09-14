from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from ..models.admin import Admin
from ..utils.audit import log_audit_event
from .. import db
from werkzeug.security import generate_password_hash

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Admin.query.filter_by(username=username).first()
        if user and user.check_password(password):
            # If user must change password, do NOT log them in yet
            if getattr(user, 'must_change_password', False):
                session['pending_user_id'] = user.id
                flash('Please change your password to continue.', 'warning')
                return redirect(url_for('auth.change_password'))

            # Otherwise, log them in normally
            session.permanent = True
            login_user(user)
            session['last_activity'] = int(__import__('time').time())
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


@auth_bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    # Identify the user: either a logged-in user or a pending user during forced change
    user = None
    if current_user.is_authenticated:
        user = current_user
    else:
        pending_user_id = session.get('pending_user_id')
        if pending_user_id:
            user = Admin.query.get(pending_user_id)
    
    if not user:
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        current = (request.form.get('current_password') or '').strip()
        new1 = (request.form.get('new_password') or '').strip()
        new2 = (request.form.get('confirm_password') or '').strip()
        if not new1 or not new2:
            flash('New password and confirmation are required', 'danger')
            return render_template('auth/change_password.html')
        if new1 != new2:
            flash('New password and confirmation do not match', 'danger')
            return render_template('auth/change_password.html')
        
        # If forced change (user.must_change_password), skip current password validation
        if not getattr(user, 'must_change_password', False):
            if not user.check_password(current):
                flash('Current password is incorrect', 'danger')
                return render_template('auth/change_password.html')
        
        # Update password
        user.set_password(new1)
        # Clear must_change_password flag if set
        if getattr(user, 'must_change_password', False):
            user.must_change_password = False
        db.session.commit()
        
        # If this was a pending change, complete login now
        if session.get('pending_user_id') == user.id and not current_user.is_authenticated:
            session.pop('pending_user_id', None)
            session.permanent = True
            login_user(user)
            session['last_activity'] = int(__import__('time').time())
            log_audit_event(action='auth.login', entity='admin', entity_id=user.id, details='post-password-change')
            db.session.commit()
        
        flash('Password updated successfully', 'success')
        return redirect(url_for('index'))
    return render_template('auth/change_password.html')

