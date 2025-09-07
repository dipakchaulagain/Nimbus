from datetime import datetime
from .. import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    occurred_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, index=True)

    # Who and from where
    user_id = db.Column(db.Integer, nullable=True, index=True)
    username = db.Column(db.String(120), nullable=True, index=True)
    source_ip = db.Column(db.String(64), nullable=True, index=True)

    # What happened
    action = db.Column(db.String(120), nullable=False, index=True)
    entity = db.Column(db.String(64), nullable=True, index=True)
    entity_id = db.Column(db.String(64), nullable=True, index=True)

    # Arbitrary JSON/text details
    details = db.Column(db.Text, nullable=True)


