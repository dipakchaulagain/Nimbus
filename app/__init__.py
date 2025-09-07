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
        
        # Dev: ensure default admin exists
        try:
            from .models.admin import Admin
            if not Admin.query.filter_by(username='admin').first():
                admin = Admin(username='admin', email='admin@example.com', role='superadmin')
                admin.set_password('admin')
                db.session.add(admin)
                db.session.commit()
        except Exception as e:
            app.logger.warning(f"Could not create admin user: {e}")

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

