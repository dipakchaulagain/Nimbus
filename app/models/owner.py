from datetime import datetime
from .. import db
from .vm import vm_owners


class Owner(db.Model):
    __tablename__ = 'owners'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    department = db.Column(db.String(120))
    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    vms = db.relationship('VM', secondary=vm_owners, back_populates='owners')

