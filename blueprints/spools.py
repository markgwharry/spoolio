"""Spool, empty-spool, refill, assembly, and group routes."""

import datetime
import math

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from time_utils import utc_now_naive
from blueprints._helpers import (
    serialize_spool,
    serialize_empty_spool,
    serialize_refill,
    serialize_group,
    _ensure_group,
    _maybe_create_empty_from_spool,
)

spools_bp = Blueprint('spools', __name__)


def _json_object():
    """Return an object JSON body, or ``None`` for malformed/unsupported input."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _nonnegative_number(data, field, *, required=False):
    """Parse a finite, non-negative numeric field without accepting booleans."""
    value = data.get(field)
    if value is None:
        if required:
            raise ValueError(f'{field} is required')
        return None
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a non-negative number')
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a non-negative number') from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f'{field} must be a non-negative number')
    return parsed


def _purchase_date(value):
    if value in (None, ''):
        return None
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise ValueError('purchase_date must use YYYY-MM-DD') from exc


def _reference_id(value, field):
    """Parse a positive integer reference without accepting compound JSON values."""
    if isinstance(value, bool):
        raise ValueError(f'Invalid {field}')
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f'Invalid {field}')
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid {field}') from exc
    if parsed <= 0:
        raise ValueError(f'Invalid {field}')
    return parsed


def _validate_reference_ids(data, *, include_spool_type=True):
    checks = [
        ('material_id', models.Material),
        ('color_id', models.Color),
        ('manufacturer_id', models.Manufacturer),
    ]
    if include_spool_type:
        checks.append(('spool_type_id', models.SpoolType))
    for field, model in checks:
        try:
            reference_id = _reference_id(data.get(field), field)
        except ValueError:
            return f'Invalid {field}'
        if db.session.get(model, reference_id) is None:
            return f'Invalid {field}'
        data[field] = reference_id
    return None


# --- Groups ---

@spools_bp.route('/groups/')
@jwt_required()
def get_groups():
    user_id = get_jwt_identity()
    groups = models.FilamentGroup.query.filter_by(user_id=user_id).all()
    return jsonify({'groups': [serialize_group(g) for g in groups]})


# --- Spools ---

@spools_bp.route('/spools/', methods=['POST'])
@jwt_required()
def create_spool():
    user_id = get_jwt_identity()
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    required_fields = ['material_id', 'color_id', 'manufacturer_id', 'spool_type_id', 'weight_start', 'weight_remaining']
    if not all(field in data for field in required_fields):
        return jsonify({'msg': 'Missing required fields'}), 400
    reference_error = _validate_reference_ids(data)
    if reference_error:
        return jsonify({'msg': reference_error}), 400
    try:
        weight_start = _nonnegative_number(data, 'weight_start', required=True)
        weight_remaining = _nonnegative_number(data, 'weight_remaining', required=True)
        low_stock_threshold = _nonnegative_number(data, 'low_stock_threshold')
        price = _nonnegative_number(data, 'price')
        purchase_date = _purchase_date(data.get('purchase_date'))
    except ValueError as exc:
        return jsonify({'msg': str(exc)}), 400
    if weight_remaining > weight_start:
        return jsonify({'msg': 'weight_remaining cannot exceed weight_start'}), 400

    group = _ensure_group(user_id, data['material_id'], data['color_id'])
    spool = models.FilamentSpool(
        material_id=data['material_id'],
        color_id=data['color_id'],
        manufacturer_id=data['manufacturer_id'],
        spool_type_id=data['spool_type_id'],
        group_id=group.id,
        user_id=user_id,
        weight_start=weight_start,
        weight_remaining=weight_remaining,
        is_active=data.get('is_active', True),
        is_empty=data.get('is_empty', False),
        notes=data.get('notes', ''),
        subtype=data.get('subtype'),
        low_stock_threshold=100 if low_stock_threshold is None else low_stock_threshold,
        purchase_date=purchase_date,
        barcode=data.get('barcode'),
        serial_number=data.get('serial_number'),
        price=price
    )
    db.session.add(spool)
    db.session.commit()
    _maybe_create_empty_from_spool(spool)
    return jsonify({'spool': serialize_spool(spool)}), 201


@spools_bp.route('/spools/')
@jwt_required()
def get_spools():
    user_id = get_jwt_identity()
    spools = models.FilamentSpool.query.filter_by(user_id=user_id).options(
        db.joinedload(models.FilamentSpool.material),
        db.joinedload(models.FilamentSpool.color),
        db.joinedload(models.FilamentSpool.manufacturer),
        db.joinedload(models.FilamentSpool.spool_type)
    ).all()
    return jsonify({'spools': [serialize_spool(s) for s in spools]})


@spools_bp.route('/spools/<int:spool_id>/', methods=['PATCH'])
@jwt_required()
def update_spool(spool_id):
    user_id = get_jwt_identity()
    spool = models.FilamentSpool.query.filter_by(id=spool_id, user_id=user_id).first()
    if not spool:
        return jsonify({'msg': 'Spool not found'}), 404
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    was_empty = bool(spool.is_empty)

    numeric_updates = {}
    try:
        for field in ['weight_remaining', 'weight_start']:
            if field in data:
                numeric_updates[field] = _nonnegative_number(
                    data,
                    field,
                    required=True,
                )
        for field in ['low_stock_threshold', 'price']:
            if field in data:
                numeric_updates[field] = _nonnegative_number(data, field)
        purchase_date = (
            _purchase_date(data.get('purchase_date'))
            if 'purchase_date' in data
            else spool.purchase_date
        )
    except ValueError as exc:
        return jsonify({'msg': str(exc)}), 400

    final_weight_start = numeric_updates.get('weight_start', spool.weight_start)
    final_weight_remaining = numeric_updates.get(
        'weight_remaining',
        spool.weight_remaining,
    )
    if (
        ('weight_remaining' in data or 'weight_start' in data)
        and final_weight_remaining > final_weight_start
    ):
        return jsonify({'msg': 'weight_remaining cannot exceed weight_start'}), 400

    reference_models = {
        'manufacturer_id': models.Manufacturer,
        'spool_type_id': models.SpoolType,
    }
    reference_updates = {}
    for field, model in reference_models.items():
        if field not in data:
            continue
        try:
            reference_id = _reference_id(data.get(field), field)
        except ValueError as exc:
            return jsonify({'msg': str(exc)}), 400
        if db.session.get(model, reference_id) is None:
            return jsonify({'msg': f'Invalid {field}'}), 400
        reference_updates[field] = reference_id

    for field in ['is_active', 'is_empty']:
        if field in data and not isinstance(data.get(field), bool):
            return jsonify({'msg': f'{field} must be a boolean'}), 400

    text_fields = ['notes', 'subtype', 'barcode', 'serial_number', 'nfc_tag_id']
    for field in text_fields:
        if field in data and data.get(field) is not None and not isinstance(data.get(field), str):
            return jsonify({'msg': f'{field} must be text'}), 400

    for field, value in numeric_updates.items():
        setattr(spool, field, value)
    for field, value in reference_updates.items():
        setattr(spool, field, value)
    for field in text_fields + ['is_active', 'is_empty']:
        if field in data:
            setattr(spool, field, data[field])

    if 'purchase_date' in data:
        spool.purchase_date = purchase_date
    if (not was_empty) and bool(getattr(spool, 'is_empty', False)) and getattr(spool, 'nfc_tag_id', None):
        spool.nfc_tag_id = None
    db.session.commit()
    _maybe_create_empty_from_spool(spool)
    return jsonify({'spool': serialize_spool(spool)})


@spools_bp.route('/spools/<int:spool_id>', methods=['DELETE'])
@spools_bp.route('/spools/<int:spool_id>/', methods=['DELETE'])
@jwt_required()
def delete_spool(spool_id):
    from flask import current_app
    user_id = get_jwt_identity()
    spool = models.FilamentSpool.query.filter_by(id=spool_id, user_id=user_id).first()
    if not spool:
        return jsonify({'msg': 'Spool not found'}), 404
    try:
        models.EmptySpool.query.filter_by(origin_spool_id=spool.id).update(
            {models.EmptySpool.origin_spool_id: None},
            synchronize_session=False,
        )
        models.HardwareEvent.query.filter_by(spool_id=spool.id).update(
            {models.HardwareEvent.spool_id: None},
            synchronize_session=False,
        )
        db.session.delete(spool)
        db.session.commit()
        return jsonify({'msg': 'Spool deleted'})
    except Exception:
        current_app.logger.exception('Failed to delete spool')
        db.session.rollback()
        return jsonify({'error': 'Failed to delete spool'}), 500


@spools_bp.route('/spools/<int:spool_id>/use', methods=['POST'])
@jwt_required()
def use_spool(spool_id):
    """Record spool usage and update last_used_date."""
    user_id = get_jwt_identity()
    spool = models.FilamentSpool.query.filter_by(id=spool_id, user_id=user_id).first()
    if not spool:
        return jsonify({'msg': 'Spool not found'}), 404

    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    try:
        requested_weight = _nonnegative_number(data, 'weight_used', required=True)
    except ValueError as exc:
        return jsonify({'msg': str(exc)}), 400
    if requested_weight <= 0:
        return jsonify({'msg': 'weight_used must be greater than zero'}), 400
    notes = data.get('notes', '')
    project_id = data.get('project_id')

    if project_id is not None:
        project = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
        if not project:
            return jsonify({'msg': 'Project not found'}), 400

    remaining = max(0.0, float(spool.weight_remaining or 0))
    if remaining <= 0:
        return jsonify({'msg': 'Spool has no remaining filament'}), 400
    actual_weight_used = min(requested_weight, remaining)
    was_empty = bool(spool.is_empty)
    spool.weight_remaining = remaining - actual_weight_used
    spool.last_used_date = utc_now_naive()
    spool.is_empty = spool.weight_remaining <= 0
    if (not was_empty) and bool(spool.is_empty) and getattr(spool, 'nfc_tag_id', None):
        spool.nfc_tag_id = None

    history = models.SpoolHistory(
        spool_id=spool.id,
        date=utc_now_naive(),
        weight_used=actual_weight_used,
        notes=notes,
        project_id=project_id
    )

    db.session.add(history)
    db.session.commit()
    _maybe_create_empty_from_spool(spool)
    return jsonify({'spool': serialize_spool(spool)})


# --- Barcode / Serial lookups ---

@spools_bp.route('/spools/barcode/<barcode>', methods=['GET'])
@jwt_required()
def get_spool_by_barcode(barcode):
    """Get spool by barcode for mobile scanning."""
    user_id = get_jwt_identity()
    spool = models.FilamentSpool.query.filter_by(barcode=barcode, user_id=user_id).first()
    if not spool:
        return jsonify({'msg': 'Spool not found'}), 404
    return jsonify({'spool': serialize_spool(spool)})


@spools_bp.route('/spools/serial/<serial_number>', methods=['GET'])
@jwt_required()
def get_spool_by_serial(serial_number):
    """Get spool by serial number for mobile scanning."""
    user_id = get_jwt_identity()
    spool = models.FilamentSpool.query.filter_by(serial_number=serial_number, user_id=user_id).first()
    if not spool:
        return jsonify({'msg': 'Spool not found'}), 404
    return jsonify({'spool': serialize_spool(spool)})


# --- Empty Spools ---

@spools_bp.route('/empty-spools/', methods=['GET'])
@jwt_required()
def list_empty_spools():
    user_id = get_jwt_identity()
    empties = models.EmptySpool.query.filter((models.EmptySpool.user_id == user_id) | (models.EmptySpool.user_id.is_(None))).all()
    return jsonify({'empty_spools': [serialize_empty_spool(e) for e in empties]})


@spools_bp.route('/empty-spools/', methods=['POST'])
@jwt_required()
def create_empty_spool():
    user_id = get_jwt_identity()
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    spool_type_id = data.get('spool_type_id')
    if not spool_type_id:
        return jsonify({'msg': 'spool_type_id is required'}), 400
    if db.session.get(models.SpoolType, spool_type_id) is None:
        return jsonify({'msg': 'Invalid spool_type_id'}), 400
    origin_spool_id = data.get('origin_spool_id')
    if origin_spool_id is not None:
        origin = models.FilamentSpool.query.filter_by(
            id=origin_spool_id,
            user_id=user_id,
        ).first()
        if not origin:
            return jsonify({'msg': 'Origin spool not found'}), 400
    empty = models.EmptySpool(
        user_id=user_id,
        spool_type_id=spool_type_id,
        origin_spool_id=origin_spool_id,
        notes=(data.get('notes') or '').strip() or None
    )
    db.session.add(empty)
    db.session.commit()
    return jsonify({'empty_spool': serialize_empty_spool(empty)}), 201


@spools_bp.route('/empty-spools/<int:empty_id>/', methods=['DELETE'])
@jwt_required()
def delete_empty_spool(empty_id):
    user_id = get_jwt_identity()
    empty = models.EmptySpool.query.filter_by(id=empty_id, user_id=user_id).first()
    if not empty:
        return jsonify({'msg': 'Empty spool not found'}), 404
    db.session.delete(empty)
    db.session.commit()
    return jsonify({'message': 'Empty spool deleted'})


# --- Refills ---

@spools_bp.route('/refills/', methods=['GET'])
@jwt_required()
def list_refills():
    user_id = get_jwt_identity()
    refills = models.FilamentRefill.query.filter_by(user_id=user_id).all()
    return jsonify({'refills': [serialize_refill(r) for r in refills]})


@spools_bp.route('/refills/', methods=['POST'])
@jwt_required()
def create_refill():
    user_id = get_jwt_identity()
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    required = ['material_id', 'color_id', 'manufacturer_id', 'weight_total']
    if not all(k in data for k in required):
        return jsonify({'msg': 'Missing required fields'}), 400
    reference_error = _validate_reference_ids(data, include_spool_type=False)
    if reference_error:
        return jsonify({'msg': reference_error}), 400
    try:
        weight_total = _nonnegative_number(data, 'weight_total', required=True)
        weight_remaining = (
            weight_total
            if data.get('weight_remaining') is None
            else _nonnegative_number(data, 'weight_remaining', required=True)
        )
        price = _nonnegative_number(data, 'price')
        purchase_date = _purchase_date(data.get('purchase_date'))
    except ValueError as exc:
        return jsonify({'msg': str(exc)}), 400
    if weight_total <= 0:
        return jsonify({'msg': 'weight_total must be greater than zero'}), 400
    if weight_remaining > weight_total:
        return jsonify({'msg': 'weight_remaining cannot exceed weight_total'}), 400
    group = _ensure_group(user_id, data['material_id'], data['color_id'])
    refill = models.FilamentRefill(
        user_id=user_id,
        material_id=data['material_id'],
        color_id=data['color_id'],
        manufacturer_id=data['manufacturer_id'],
        group_id=group.id,
        weight_total=weight_total,
        weight_remaining=weight_remaining,
        subtype=data.get('subtype'),
        purchase_date=purchase_date,
        notes=(data.get('notes') or '').strip() or None,
        price=price,
        barcode=data.get('barcode'),
        serial_number=data.get('serial_number')
    )
    db.session.add(refill)
    db.session.commit()
    return jsonify({'refill': serialize_refill(refill)}), 201


@spools_bp.route('/refills/<int:refill_id>/', methods=['PATCH'])
@jwt_required()
def update_refill(refill_id):
    user_id = get_jwt_identity()
    refill = models.FilamentRefill.query.filter_by(id=refill_id, user_id=user_id).first()
    if not refill:
        return jsonify({'msg': 'Refill not found'}), 404
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    if 'weight_remaining' in data:
        try:
            weight_remaining = _nonnegative_number(data, 'weight_remaining', required=True)
        except ValueError as exc:
            return jsonify({'msg': str(exc)}), 400
        if weight_remaining > refill.weight_total:
            return jsonify({'msg': 'weight_remaining cannot exceed weight_total'}), 400
        refill.weight_remaining = weight_remaining
    if 'price' in data:
        try:
            refill.price = _nonnegative_number(data, 'price')
        except ValueError as exc:
            return jsonify({'msg': str(exc)}), 400
    for field in ['notes', 'subtype', 'barcode', 'serial_number']:
        if field in data:
            setattr(refill, field, data[field])
    if 'purchase_date' in data:
        try:
            refill.purchase_date = _purchase_date(data.get('purchase_date'))
        except ValueError as exc:
            return jsonify({'msg': str(exc)}), 400
    db.session.commit()
    return jsonify({'refill': serialize_refill(refill)})


@spools_bp.route('/refills/<int:refill_id>/', methods=['DELETE'])
@jwt_required()
def delete_refill(refill_id):
    user_id = get_jwt_identity()
    refill = models.FilamentRefill.query.filter_by(id=refill_id, user_id=user_id).first()
    if not refill:
        return jsonify({'msg': 'Refill not found'}), 404
    db.session.delete(refill)
    db.session.commit()
    return jsonify({'message': 'Refill deleted'})


# --- Assembly ---

@spools_bp.route('/assemble/', methods=['POST'])
@jwt_required()
def assemble_refill_onto_empty():
    user_id = get_jwt_identity()
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    refill_id = data.get('refill_id')
    empty_id = data.get('empty_spool_id')
    spool_type_id = data.get('spool_type_id')
    if not refill_id or (not empty_id and not spool_type_id):
        return jsonify({'msg': 'refill_id and (empty_spool_id or spool_type_id) are required'}), 400

    refill = models.FilamentRefill.query.filter_by(id=refill_id, user_id=user_id).first()
    if not refill:
        return jsonify({'msg': 'Refill not found'}), 404
    if not refill.weight_remaining or refill.weight_remaining <= 0:
        return jsonify({'msg': 'Refill has no remaining filament'}), 400

    if empty_id:
        empty = models.EmptySpool.query.filter_by(id=empty_id, user_id=user_id).first()
        if not empty:
            return jsonify({'msg': 'Empty spool not found'}), 404
        spool_type_id = empty.spool_type_id
    else:
        empty = None
        if db.session.get(models.SpoolType, spool_type_id) is None:
            return jsonify({'msg': 'Invalid spool_type_id'}), 400

    group = _ensure_group(user_id, refill.material_id, refill.color_id)

    new_spool = models.FilamentSpool(
        material_id=refill.material_id,
        color_id=refill.color_id,
        manufacturer_id=refill.manufacturer_id,
        spool_type_id=spool_type_id,
        group_id=group.id,
        user_id=user_id,
        weight_start=float(refill.weight_remaining),
        weight_remaining=float(refill.weight_remaining),
        is_active=True,
        is_empty=False,
        notes=refill.notes,
        subtype=refill.subtype,
        low_stock_threshold=100,
        purchase_date=refill.purchase_date,
        barcode=None,
        serial_number=None,
        price=refill.price
    )
    db.session.add(new_spool)
    refill.weight_remaining = 0
    db.session.delete(refill)
    if empty:
        db.session.delete(empty)
    db.session.commit()
    return jsonify({'spool': serialize_spool(new_spool)})
