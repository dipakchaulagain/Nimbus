from datetime import datetime
from .. import db


vm_owners = db.Table(
    'vm_owners',
    db.Column('vm_id', db.String(64), db.ForeignKey('vms.id', ondelete='CASCADE'), primary_key=True),
    db.Column('owner_id', db.Integer, db.ForeignKey('owners.id', ondelete='CASCADE'), primary_key=True),
)

vm_tags = db.Table(
    'vm_tags',
    db.Column('vm_id', db.String(64), db.ForeignKey('vms.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
)


class VM(db.Model):
    __tablename__ = 'vms'

    id = db.Column(db.String(64), primary_key=True)  # vCenter instanceUuid
    name = db.Column(db.String(255), index=True, nullable=False)
    cpu = db.Column(db.Integer)
    memory_mb = db.Column(db.Integer)
    guest_os = db.Column(db.String(255))
    power_state = db.Column(db.String(32), index=True)
    created_date = db.Column(db.DateTime(timezone=True))
    last_booted_date = db.Column(db.DateTime(timezone=True))
    hypervisor = db.Column(db.String(255), index=True)

    nics = db.relationship('VMNic', backref='vm', cascade='all, delete-orphan')
    disks = db.relationship('VMDisks', backref='vm', cascade='all, delete-orphan')
    owners = db.relationship('Owner', secondary=vm_owners, back_populates='vms')
    tags = db.relationship('Tag', secondary=vm_tags, back_populates='vms')

    created_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class VMDisks(db.Model):
    __tablename__ = 'vm_disks'
    id = db.Column(db.Integer, primary_key=True)
    vm_id = db.Column(db.String(64), db.ForeignKey('vms.id', ondelete='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(255))
    size_gb = db.Column(db.Numeric(10, 2))


class VMNic(db.Model):
    __tablename__ = 'vm_nics'
    id = db.Column(db.Integer, primary_key=True)
    vm_id = db.Column(db.String(64), db.ForeignKey('vms.id', ondelete='CASCADE'), nullable=False, index=True)
    label = db.Column(db.String(255))
    mac = db.Column(db.String(64), index=True)
    network = db.Column(db.String(255))
    connected = db.Column(db.Boolean, default=False)
    nic_type = db.Column(db.String(128))
    ip_addresses = db.Column(db.JSON)

