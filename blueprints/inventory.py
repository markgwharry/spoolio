"""Inventory lookup routes: materials, colors, manufacturers, spool types, subtypes."""

import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from blueprints._helpers import (
    admin_required,
    serialize_material,
    serialize_color,
    serialize_manufacturer,
    serialize_spool_type,
)

inventory_bp = Blueprint('inventory', __name__)


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _required_name(data, label):
    if data is None:
        return None, (jsonify({'msg': 'JSON object required'}), 400)
    value = data.get('name')
    if not isinstance(value, str) or not value.strip():
        return None, (jsonify({'msg': f'{label} name required'}), 400)
    return value.strip(), None


def _tare_weight(data):
    value = data.get('tare_weight', 0)
    if isinstance(value, bool):
        raise ValueError
    parsed = float(value or 0)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError
    return parsed


@inventory_bp.route('/materials/')
@jwt_required()
def get_materials():
    materials = models.Material.query.all()
    return jsonify({'materials': [serialize_material(m) for m in materials]})


@inventory_bp.route('/materials/', methods=['POST'])
@jwt_required()
def create_material():
    name, error = _required_name(_json_object(), 'Material')
    if error:
        return error
    material = models.Material.query.filter(db.func.lower(models.Material.name) == name.lower()).first()
    if material:
        return jsonify({'id': material.id, 'name': material.name}), 200
    material = models.Material(name=name)
    db.session.add(material)
    db.session.commit()
    return jsonify({'id': material.id, 'name': material.name}), 201


@inventory_bp.route('/colors/')
@jwt_required()
def get_colors():
    colors = models.Color.query.all()
    return jsonify({'colors': [serialize_color(c) for c in colors]})


@inventory_bp.route('/colors/', methods=['POST'])
@jwt_required()
def create_color():
    name, error = _required_name(_json_object(), 'Color')
    if error:
        return error
    color = models.Color.query.filter(db.func.lower(models.Color.name) == name.lower()).first()
    if color:
        return jsonify({'id': color.id, 'name': color.name}), 200
    color = models.Color(name=name)
    db.session.add(color)
    db.session.commit()
    return jsonify({'id': color.id, 'name': color.name}), 201


@inventory_bp.route('/manufacturers/')
@jwt_required()
def get_manufacturers():
    manufacturers = models.Manufacturer.query.all()
    return jsonify({'manufacturers': [serialize_manufacturer(m) for m in manufacturers]})


@inventory_bp.route('/manufacturers/', methods=['POST'])
@jwt_required()
def create_manufacturer():
    name, error = _required_name(_json_object(), 'Manufacturer')
    if error:
        return error
    manufacturer = models.Manufacturer.query.filter(db.func.lower(models.Manufacturer.name) == name.lower()).first()
    if manufacturer:
        return jsonify({'id': manufacturer.id, 'name': manufacturer.name}), 200
    manufacturer = models.Manufacturer(name=name)
    db.session.add(manufacturer)
    db.session.commit()
    return jsonify({'id': manufacturer.id, 'name': manufacturer.name}), 201


@inventory_bp.route('/manufacturers/<int:manufacturer_id>', methods=['DELETE'])
@admin_required
def delete_manufacturer(manufacturer_id):
    """Delete a manufacturer if unused."""
    from flask import current_app
    m = db.session.get(models.Manufacturer, manufacturer_id)
    if not m:
        return jsonify({'error': 'Manufacturer not found'}), 404
    spool_count = models.FilamentSpool.query.filter_by(
        manufacturer_id=manufacturer_id
    ).count()
    refill_count = models.FilamentRefill.query.filter_by(
        manufacturer_id=manufacturer_id
    ).count()
    if spool_count or refill_count:
        return jsonify({
            'error': 'Cannot delete manufacturer while in use',
            'num_spools': spool_count,
            'num_refills': refill_count,
        }), 409
    try:
        db.session.delete(m)
        db.session.commit()
        return jsonify({'message': 'Manufacturer deleted'})
    except Exception:
        current_app.logger.exception('Failed to delete manufacturer')
        db.session.rollback()
        return jsonify({'error': 'Failed to delete manufacturer'}), 500


@inventory_bp.route('/spooltypes/')
@jwt_required()
def get_spool_types():
    spool_types = models.SpoolType.query.all()
    return jsonify({'spool_types': [serialize_spool_type(s) for s in spool_types]})


@inventory_bp.route('/spooltypes/', methods=['POST'])
@jwt_required()
def create_spooltype():
    data = _json_object()
    name, error = _required_name(data, 'Spool type')
    if error:
        return error
    compatible_with_ams = data.get('compatible_with_ams', False)
    try:
        tare_weight = _tare_weight(data)
    except (TypeError, ValueError):
        return jsonify({'msg': 'tare_weight must be a non-negative number'}), 400
    spooltype = models.SpoolType.query.filter(db.func.lower(models.SpoolType.name) == name.lower()).first()
    if spooltype:
        if tare_weight and (getattr(spooltype, 'tare_weight', 0) or 0) != tare_weight:
            spooltype.tare_weight = tare_weight
            db.session.commit()
        return jsonify({'id': spooltype.id, 'name': spooltype.name, 'compatible_with_ams': spooltype.compatible_with_ams, 'tare_weight': getattr(spooltype, 'tare_weight', 0) or 0}), 200
    spooltype = models.SpoolType(name=name, compatible_with_ams=compatible_with_ams, tare_weight=tare_weight)
    db.session.add(spooltype)
    db.session.commit()
    return jsonify({'id': spooltype.id, 'name': spooltype.name, 'compatible_with_ams': spooltype.compatible_with_ams, 'tare_weight': getattr(spooltype, 'tare_weight', 0) or 0}), 201


@inventory_bp.route('/spooltypes/<int:spooltype_id>', methods=['PATCH'])
@admin_required
def update_spooltype(spooltype_id):
    """Update spool type fields."""
    st = db.session.get(models.SpoolType, spooltype_id)
    if not st:
        return jsonify({'error': 'Spool type not found'}), 404
    data = _json_object()
    if data is None:
        return jsonify({'error': 'JSON object required'}), 400
    raw_name = data.get('name')
    if raw_name is not None and not isinstance(raw_name, str):
        return jsonify({'error': 'Invalid name'}), 400
    name = (raw_name or '').strip()
    if name:
        existing = models.SpoolType.query.filter(db.func.lower(models.SpoolType.name) == name.lower(), models.SpoolType.id != st.id).first()
        if existing:
            return jsonify({'error': 'Spool type name already exists'}), 409
        st.name = name
    if 'compatible_with_ams' in data:
        st.compatible_with_ams = bool(data.get('compatible_with_ams'))
    if 'tare_weight' in data:
        try:
            st.tare_weight = _tare_weight(data)
        except (TypeError, ValueError):
            return jsonify({'error': 'Invalid tare_weight'}), 400
    db.session.commit()
    return jsonify(serialize_spool_type(st))


@inventory_bp.route('/spooltypes/<int:spooltype_id>', methods=['DELETE'])
@admin_required
def delete_spooltype(spooltype_id):
    """Delete a spool type if unused."""
    from flask import current_app
    st = db.session.get(models.SpoolType, spooltype_id)
    if not st:
        return jsonify({'error': 'Spool type not found'}), 404
    spool_count = models.FilamentSpool.query.filter_by(
        spool_type_id=spooltype_id
    ).count()
    empty_spool_count = models.EmptySpool.query.filter_by(
        spool_type_id=spooltype_id
    ).count()
    if spool_count or empty_spool_count:
        return jsonify({
            'error': 'Cannot delete spool type while in use',
            'num_spools': spool_count,
            'num_empty_spools': empty_spool_count,
        }), 409
    try:
        db.session.delete(st)
        db.session.commit()
        return jsonify({'message': 'Spool type deleted'})
    except Exception:
        current_app.logger.exception('Failed to delete spool type')
        db.session.rollback()
        return jsonify({'error': 'Failed to delete spool type'}), 500


@inventory_bp.route('/subtypes/')
@jwt_required()
def get_subtypes():
    user_id = get_jwt_identity()
    subtypes = (
        models.FilamentSpool.query
        .filter_by(user_id=user_id)
        .with_entities(models.FilamentSpool.subtype)
        .distinct()
        .all()
    )
    subtype_list = sorted(set(s[0] for s in subtypes if s[0]))
    return jsonify({'subtypes': subtype_list})


@inventory_bp.route('/subtypes/<string:subtype>', methods=['DELETE'])
@jwt_required()
def clear_subtype(subtype):
    """Clear a subtype value from all current user's spools that match it."""
    from flask import current_app
    user_id = get_jwt_identity()
    subtype_clean = (subtype or '').strip()
    if not subtype_clean:
        return jsonify({'error': 'Subtype is required'}), 400
    try:
        updated = (
            models.FilamentSpool.query
            .filter(
                models.FilamentSpool.user_id == user_id,
                models.FilamentSpool.subtype == subtype_clean
            )
            .update({'subtype': None}, synchronize_session=False)
        )
        db.session.commit()
        return jsonify({'message': 'Subtype cleared', 'rows_affected': int(updated or 0)})
    except Exception:
        current_app.logger.exception('Failed to clear subtype')
        db.session.rollback()
        return jsonify({'error': 'Failed to clear subtype'}), 500
