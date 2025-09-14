from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_required
from ..utils.roles import require_roles
from ..models.vcenter import VCenterConfig
from ..utils.audit import log_audit_event
from .. import db, scheduler
from ..scheduler.tasks import sync_vcenter_job
import threading
import ssl
import urllib3
from pyVim.connect import SmartConnect, Disconnect

vcenter_bp = Blueprint('vcenter', __name__)

@vcenter_bp.route('/')
@login_required
def list_configs():
    configs = VCenterConfig.query.order_by(VCenterConfig.name.asc()).all()
    return render_template('vcenter/vcenter.html', configs=configs)

@vcenter_bp.route('/create', methods=['POST'])
@login_required
@require_roles('superadmin')
def create_config():
    name = request.form.get('name')
    host = request.form.get('host')
    username = request.form.get('username')
    password = request.form.get('password')
    disable_ssl = bool(request.form.get('disable_ssl'))
    enabled = bool(request.form.get('enabled'))

    if not name or not host or not username or not password:
        flash('All required fields must be filled', 'error')
        return redirect(url_for('vcenter.list_configs'))

    cfg = VCenterConfig(
        name=name, host=host, username=username, password=password,
        disable_ssl=disable_ssl, enabled=enabled
    )
    db.session.add(cfg)
    log_audit_event(action='vcenter.create', entity='vcenter', entity_id=cfg.id, details=f"name={cfg.name}, host={cfg.host}")
    db.session.commit()
    flash('vCenter configuration created successfully', 'success')
    return redirect(url_for('vcenter.list_configs'))

@vcenter_bp.route('/edit/<int:cfg_id>', methods=['POST'])
@login_required
@require_roles('superadmin')
def edit_config(cfg_id):
    cfg = VCenterConfig.query.get_or_404(cfg_id)
    cfg.name = request.form.get('name') or cfg.name
    cfg.host = request.form.get('host') or cfg.host
    cfg.username = request.form.get('username') or cfg.username
    if request.form.get('password'):
        cfg.password = request.form.get('password')
    cfg.disable_ssl = bool(request.form.get('disable_ssl'))
    cfg.enabled = bool(request.form.get('enabled'))
    log_audit_event(action='vcenter.update', entity='vcenter', entity_id=cfg.id, details=f"name={cfg.name}, host={cfg.host}")
    db.session.commit()
    flash('vCenter configuration updated successfully', 'success')
    return redirect(url_for('vcenter.list_configs'))

@vcenter_bp.route('/test/<int:cfg_id>', methods=['POST'])
@login_required
@require_roles('editor', 'superadmin')
def test_connection(cfg_id):
    cfg = VCenterConfig.query.get_or_404(cfg_id)
    try:
        if cfg.disable_ssl:
            urllib3.disable_warnings()
            context = ssl._create_unverified_context()
        else:
            context = None

        si = SmartConnect(
            host=cfg.host,
            user=cfg.username,
            pwd=cfg.password,
            sslContext=context
        )
        Disconnect(si)
        log_audit_event(action='vcenter.test_connection', entity='vcenter', entity_id=cfg.id, details='success')
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Connection successful'})
    except Exception as e:
        log_audit_event(action='vcenter.test_connection', entity='vcenter', entity_id=cfg.id, details=f'error: {str(e)}')
        db.session.commit()
        return jsonify({'status': 'error', 'message': f'Connection failed: {str(e)}'})

@vcenter_bp.route('/toggle/<int:cfg_id>', methods=['POST'])
@login_required
@require_roles('superadmin')
def toggle_config(cfg_id):
    cfg = VCenterConfig.query.get_or_404(cfg_id)
    cfg.enabled = not cfg.enabled
    log_audit_event(action='vcenter.toggle', entity='vcenter', entity_id=cfg.id, details=f"enabled={cfg.enabled}")
    db.session.commit()
    flash(f"vCenter configuration {'enabled' if cfg.enabled else 'disabled'}", 'success')
    return redirect(url_for('vcenter.list_configs'))

@vcenter_bp.route('/sync')
@login_required
@require_roles('editor', 'superadmin')
def manual_sync():
    def run_sync(app_instance):
        from .. import db
        with app_instance.app_context():
            try:
                sync_vcenter_job()
                app_instance.logger.info("Manual vCenter sync completed successfully")
            except Exception as e:
                app_instance.logger.error(f"Manual vCenter sync failed: {e}")
            finally:
                db.session.remove()  # ensure connections are returned
    
    thread = threading.Thread(target=run_sync, args=(current_app._get_current_object(),))
    thread.daemon = True
    thread.start()
    log_audit_event(action='vcenter.sync', entity='vcenter', entity_id=None, details='manual sync triggered')
    db.session.commit()
    flash('Sync started in background', 'info')
    return redirect(url_for('vcenter.list_configs'))

@vcenter_bp.route('/delete/<int:cfg_id>', methods=['POST'])
@login_required
@require_roles('superadmin')
def delete_config(cfg_id):
    cfg = VCenterConfig.query.get_or_404(cfg_id)
    cid = cfg.id
    cname = cfg.name
    db.session.delete(cfg)
    log_audit_event(action='vcenter.delete', entity='vcenter', entity_id=cid, details=f"name={cname}")
    db.session.commit()
    flash('vCenter configuration deleted successfully', 'success')
    return redirect(url_for('vcenter.list_configs'))