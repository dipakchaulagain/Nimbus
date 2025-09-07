#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from app import create_app, db
from app.models.admin import Admin

app = create_app()
with app.app_context():
    # Fallback: ensure tables exist if migrations not set up
    try:
        db.engine.execute('SELECT 1')
        db.create_all()
    except Exception:
        pass
    if not Admin.query.filter_by(username='admin').first():
        u = Admin(username='admin', email='admin@example.com', role='superadmin')
        u.set_password('admin')
        db.session.add(u)
        db.session.commit()
        print('Seeded default admin: admin/admin')
PY

exec "$@"

