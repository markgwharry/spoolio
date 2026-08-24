"""Spool history routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from blueprints._helpers import serialize_spool_history

history_bp = Blueprint('history', __name__)


def _serialize_owned_history(history, user_id):
    payload = serialize_spool_history(history)
    project = getattr(history, 'project', None)
    if project is not None and str(project.user_id) != str(user_id):
        payload['project_id'] = None
        payload['project_name'] = None
    return payload


@history_bp.route('/spoolhistory/')
@jwt_required()
def get_spool_history():
    user_id = get_jwt_identity()
    history = (
        models.SpoolHistory.query
        .join(
            models.FilamentSpool,
            models.SpoolHistory.spool_id == models.FilamentSpool.id,
        )
        .filter(models.FilamentSpool.user_id == user_id)
        .options(db.joinedload(models.SpoolHistory.project))
        .all()
    )
    return jsonify({
        'history': [_serialize_owned_history(h, user_id) for h in history]
    })


@history_bp.route('/spoolhistory/<int:history_id>/', methods=['PATCH'])
@jwt_required()
def update_spool_history(history_id):
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()
    h = (
        models.SpoolHistory.query
        .join(
            models.FilamentSpool,
            models.SpoolHistory.spool_id == models.FilamentSpool.id,
        )
        .filter(
            models.SpoolHistory.id == history_id,
            models.FilamentSpool.user_id == user_id,
        )
        .options(db.joinedload(models.SpoolHistory.project))
        .first()
    )
    if not h:
        return jsonify({'msg': 'History entry not found'}), 404
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'msg': 'JSON object required'}), 400
    if 'notes' in data:
        h.notes = data['notes']
    if 'project_id' in data:
        pid = data['project_id']
        if pid is None:
            h.project_id = None
        else:
            proj = models.Project.query.filter_by(id=pid, user_id=user_id).first()
            if not proj:
                return jsonify({'msg': 'Project not found'}), 400
            h.project_id = pid
    db.session.commit()
    return jsonify({'history': _serialize_owned_history(h, user_id)})


@history_bp.route('/spoolhistory/bulk-assign', methods=['POST'])
@jwt_required()
def bulk_assign_spool_history():
    """Assign multiple history entries to a project in one request."""
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'msg': 'JSON object required'}), 400
    history_ids = data.get('history_ids', [])
    project_id = data.get('project_id')

    if not history_ids or not isinstance(history_ids, list):
        return jsonify({'msg': 'history_ids array required'}), 400

    if len(history_ids) > 100:
        return jsonify({'msg': 'Maximum 100 entries per batch'}), 400

    if project_id is not None:
        proj = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
        if not proj:
            return jsonify({'msg': 'Project not found'}), 400

    owned_entries = (
        models.SpoolHistory.query
        .join(
            models.FilamentSpool,
            models.SpoolHistory.spool_id == models.FilamentSpool.id,
        )
        .filter(
            models.SpoolHistory.id.in_(history_ids),
            models.FilamentSpool.user_id == user_id,
        )
        .options(db.joinedload(models.SpoolHistory.project))
        .all()
    )
    updated = []
    for h in owned_entries:
        h.project_id = project_id
        updated.append(h)

    db.session.commit()
    return jsonify({
        'updated_count': len(updated),
        'history': [_serialize_owned_history(h, user_id) for h in updated]
    })
