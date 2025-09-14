from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_required, current_user
from apscheduler.schedulers.background import BackgroundScheduler
from config import get_config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
scheduler = BackgroundScheduler()


def create_app():
    app = Flask(__name__, static_url_path='/static', static_folder='static')
    app.config.from_object(get_config())

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.session_protection = 'strong'

    # Register blueprints
    from .routes.auth import auth_bp
    from .routes.vm import vm_bp
    from .routes.owner import owner_bp
    from .routes.tag import tag_bp
    from .routes.vcenter import vcenter_bp
    from .routes.admin import admin_bp
    from .routes.audit import audit_bp
    from .routes.report import report_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(vm_bp, url_prefix='/vms')
    app.register_blueprint(owner_bp, url_prefix='/owners')
    app.register_blueprint(tag_bp, url_prefix='/tags')
    app.register_blueprint(vcenter_bp, url_prefix='/vcenter')
    app.register_blueprint(report_bp, url_prefix='/reports')
    app.register_blueprint(admin_bp, url_prefix='/admins')
    app.register_blueprint(audit_bp, url_prefix='/audit')

    # Create database tables if they don't exist
    with app.app_context():
        # Ensure all models are imported so SQLAlchemy is aware before create_all
        try:
            from .models.audit import AuditLog  # noqa: F401
        except Exception:
            pass
        try:
            db.create_all()
        except Exception as e:
            app.logger.warning(f"Could not create tables: {e}")

        # Ensure new columns exist without full migrations (best-effort)
        try:
            from sqlalchemy import inspect, text
            insp = inspect(db.engine)
            admin_cols = {c['name'] for c in insp.get_columns('admins')}
            if 'must_change_password' not in admin_cols:
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE admins ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE"))
        except Exception as e:
            app.logger.warning(f"Column check/alter failed (safe to ignore if already present): {e}")
        
        # Dev: ensure default admin exists
        try:
            from .models.admin import Admin
            if not Admin.query.filter_by(username='admin').first():
                admin = Admin(username='admin', email='admin@example.com', role='superadmin', must_change_password=True)
                admin.set_password('admin')
                db.session.add(admin)
                db.session.commit()
            else:
                # If existing default admin still uses 'admin' password, force change
                a = Admin.query.filter_by(username='admin').first()
                try:
                    if a and a.check_password('admin'):
                        a.must_change_password = True
                        db.session.commit()
                except Exception:
                    pass
        except Exception as e:
            app.logger.warning(f"Could not create/admin-check admin user: {e}")

    @app.before_request
    def enforce_timeouts():
        # Enforce inactivity timeout based on SESSION_INACTIVITY_MINUTES
        from flask import session
        import time
        try:
            if getattr(current_user, 'is_authenticated', False):
                now = int(time.time())
                last = session.get('last_activity')
                max_idle = int(app.config.get('SESSION_INACTIVITY_MINUTES', 30)) * 60
                if last is not None and (now - int(last)) > max_idle:
                    from flask_login import logout_user
                    logout_user()
                else:
                    # refresh last activity timestamp
                    session['last_activity'] = now
        except Exception:
            # Never block request due to session housekeeping
            pass

    @app.route('/')
    def index():
        from flask import render_template, redirect, url_for
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        from .models.vm import VM
        total = VM.query.count()
        powered_on = VM.query.filter_by(power_state='poweredOn').count()
        powered_off = VM.query.filter_by(power_state='poweredOff').count()
        return render_template('dashboard.html', total_vms=total, powered_on=powered_on, powered_off=powered_off)

    return app

