from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from ..models.tag import Tag
from .. import db

tag_bp = Blueprint('tag', __name__)


@tag_bp.route('/')
@login_required
def list_tags():
    tags = Tag.query.order_by(Tag.name.asc()).all()
    return render_template('tags/list.html', tags=tags)


@tag_bp.route('/api', methods=['GET'])
@login_required
def tags_api_list():
    tags = Tag.query.order_by(Tag.name.asc()).all()
    return jsonify([
        { 'id': t.id, 'name': t.name, 'description': t.description }
        for t in tags
    ])


@tag_bp.route('/api', methods=['POST'])
@login_required
def tags_api_create():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    t = Tag(name=name, description=description)
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id}), 201


@tag_bp.route('/api/<int:tag_id>', methods=['PUT'])
@login_required
def tags_api_update(tag_id: int):
    t = Tag.query.get_or_404(tag_id)
    data = request.get_json() or {}
    if 'name' in data: t.name = (data['name'] or '').strip()
    if 'description' in data: t.description = (data['description'] or '').strip()
    db.session.commit()
    return jsonify({'status': 'ok'})


@tag_bp.route('/api/<int:tag_id>', methods=['DELETE'])
@login_required
def tags_api_delete(tag_id: int):
    t = Tag.query.get_or_404(tag_id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({'status': 'deleted'})

