Nimbus - VM Inventory and Auditing
=================================

Nimbus is a Flask-based web application for discovering and managing VMware vCenter virtual machines, owners, and tags. It includes role-based access control (viewer/editor/superadmin), background vCenter sync, and a full auditing trail of user actions.

Key Features
------------
- VM inventory with owners and tags
- vCenter connection management and manual/automatic sync
- Role-based access control (RBAC)
  - Viewer: read-only across most pages; no Admins or Audit access
  - Editor: edit Owners/Tags/VM assignments; read-only vCenter; no Admins/Audit
  - Superadmin: full access
- Auditing of all key actions with user and source IP (via Nginx `X-Forwarded-For` / `X-Real-IP`)
- Modern UI built with Bootstrap and DataTables

Tech Stack
---------
- Python 3, Flask, Flask-Login, Flask-SQLAlchemy, Flask-Migrate
- APScheduler for background jobs
- Gunicorn behind Nginx (reverse proxy)
- PostgreSQL

Quick Start (Docker Compose)
---------------------------
Prerequisites: Docker and Docker Compose

1) Create an `.env` file at the repo root:

```
FLASK_ENV=development
FLASK_APP=run.py
SECRET_KEY=ddfSDfdr3sd22Sdfdf@sfrf
# Database
DATABASE_URL=postgresql+psycopg2://postgres:password@db:5432/vm_inventory
# Scheduler
VCENTER_SYNC_INTERVAL=30
# Gunicorn
WEB_CONCURRENCY=2
```

2) Build and start services:

```
docker-compose up -d --build
```

3) Access the app:
- Web UI: http://localhost/
- Default admin user (auto-created on first run):
  - username: `admin`
  - password: `admin`

Note: The app will create database tables automatically on startup. If you later adopt migrations, ensure to run `flask db migrate` / `flask db upgrade` accordingly.

Local Development (without Docker)
----------------------------------
1) Create and activate a virtual environment:
```
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2) Install dependencies:
```
pip install -r requirements.txt
```

3) Set environment variables (example):
```
export FLASK_ENV=development
export FLASK_APP=run.py
export SECRET_KEY=dev-secret
export DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/vm_inventory
export VCENTER_SYNC_INTERVAL=30
export WEB_CONCURRENCY=2
```

4) Initialize database (tables are auto-created at boot):
- Ensure the configured PostgreSQL database exists and is reachable

5) Run the app:
```
python run.py
```
The app will be available at http://localhost:5000

Roles and Access
----------------
- Viewer
  - Can view Dashboards, VMs, Owners, Tags, vCenter
  - Cannot see Admins or Audit Logs
  - No create/update/delete actions
- Editor
  - All viewer access
  - Can create/update/delete Owners and Tags
  - Can assign Owners/Tags to VMs
  - Read-only vCenter (can Test Connection and trigger Sync)
  - No Admins or Audit Logs access
- Superadmin
  - Full access to all pages and actions (Admins, Audit Logs, vCenter CRUD)

User roles are stored on the `admins` table (`role` column).

Auditing
--------
- All key actions (auth, owners, tags, VM assignments, vCenter actions) are recorded in `audit_logs`
- Recorded fields: timestamp, username/user_id, source IP, action, entity, entity_id, details
- Source IP is resolved from `X-Forwarded-For` or `X-Real-IP` headers (set by Nginx); falls back to `remote_addr`
- View logs in the UI under Audit Logs (superadmin only)

Nginx and Client IP Forwarding
------------------------------
The included Nginx proxy forwards client IPs:
- `X-Real-IP: $remote_addr`
- `X-Forwarded-For: $proxy_add_x_forwarded_for`

The application prefers the leftmost address in `X-Forwarded-For`, then `X-Real-IP`.

Background Sync
---------------
- APScheduler runs a background job to synchronize vCenter data on an interval defined by `VCENTER_SYNC_INTERVAL` (minutes)
- Manual sync can be triggered from the vCenter page (Editor or Superadmin)

Running Tests
-------------
```
pytest -q
```

Troubleshooting
---------------
- No audit logs recorded
  - Ensure the `audit_logs` table exists (created automatically at startup)
  - Ensure the application restarted after enabling auditing
- Login not working
  - Check the database connection and that the default admin exists (`admin`/`admin`)
- Client IPs show as proxy IP
  - Verify Nginx is in front of the app and the headers are being forwarded

License
-------
MIT


