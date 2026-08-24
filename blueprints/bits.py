"""Bits (hardware components) routes — CRUD, restock, usage tracking."""

import datetime
import math

from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from time_utils import utc_now_naive
from blueprints._helpers import (
    serialize_bit,
    serialize_bit_category,
    serialize_bit_usage,
    validation_error_response,
)

bits_bp = Blueprint('bits', __name__)


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _nonnegative_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a non-negative integer')
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f'{field} must be a non-negative integer')
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field} must be a non-negative integer') from exc
    if parsed < 0:
        raise ValueError(f'{field} must be a non-negative integer')
    return parsed


def _optional_price(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('price must be a non-negative number')
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('price must be a non-negative number') from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError('price must be a non-negative number')
    return parsed


def _purchase_date(value):
    if value in (None, ''):
        return None
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError) as exc:
        raise ValueError('purchase_date must use YYYY-MM-DD') from exc


def _serialize_owned_usage(usage, user_id):
    payload = serialize_bit_usage(usage)
    project = getattr(usage, 'project', None)
    if project is not None and str(project.user_id) != str(user_id):
        payload['project_id'] = None
        payload['project_name'] = None
    return payload


# --- Categories ---

@bits_bp.route('/bitcategories/', methods=['GET'])
@jwt_required()
def get_bit_categories():
    categories = models.BitCategory.query.order_by(models.BitCategory.name).all()
    return jsonify({'categories': [serialize_bit_category(c) for c in categories]})


@bits_bp.route('/bitcategories/', methods=['POST'])
@jwt_required()
def create_bit_category():
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    raw_name = data.get('name')
    name = raw_name.strip() if isinstance(raw_name, str) else ''
    if not name:
        return jsonify({'msg': 'Category name required'}), 400
    existing = models.BitCategory.query.filter(
        db.func.lower(models.BitCategory.name) == name.lower()
    ).first()
    if existing:
        return jsonify({'id': existing.id, 'name': existing.name}), 200
    category = models.BitCategory(name=name)
    db.session.add(category)
    db.session.commit()
    return jsonify({'id': category.id, 'name': category.name}), 201


# --- Bits CRUD ---

@bits_bp.route('/bits/', methods=['GET'])
@jwt_required()
def get_bits():
    user_id = get_jwt_identity()
    bits = models.Bit.query.filter_by(user_id=user_id).options(
        db.joinedload(models.Bit.category)
    ).all()
    return jsonify({'bits': [serialize_bit(b) for b in bits]})


@bits_bp.route('/bits/', methods=['POST'])
@jwt_required()
def create_bit():
    user_id = get_jwt_identity()
    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    required_fields = ['category_id', 'name', 'quantity_total']
    if not all(field in data for field in required_fields):
        return jsonify({'msg': 'Missing required fields: category_id, name, quantity_total'}), 400

    category_value = data['category_id']
    if isinstance(category_value, bool) or not isinstance(category_value, (int, str)):
        category = None
    else:
        try:
            category = db.session.get(models.BitCategory, category_value)
        except (TypeError, ValueError):
            category = None
    if not category:
        return jsonify({'msg': 'Category not found'}), 400

    try:
        quantity_total = _nonnegative_int(data['quantity_total'], 'quantity_total')
        quantity_remaining = (
            quantity_total
            if data.get('quantity_remaining') is None
            else _nonnegative_int(data['quantity_remaining'], 'quantity_remaining')
        )
        low_stock_threshold = _nonnegative_int(
            data.get('low_stock_threshold', 10),
            'low_stock_threshold',
        )
        price = _optional_price(data.get('price'))
        purchase_date = _purchase_date(data.get('purchase_date'))
    except ValueError:
        return validation_error_response()

    raw_name = data.get('name')
    name = raw_name.strip() if isinstance(raw_name, str) else ''
    if not name:
        return jsonify({'msg': 'Bit name required'}), 400
    if quantity_total <= 0:
        return jsonify({'msg': 'quantity_total must be positive'}), 400
    if quantity_remaining > quantity_total:
        return jsonify({'msg': 'quantity_remaining cannot exceed quantity_total'}), 400

    bit = models.Bit(
        user_id=user_id,
        category_id=data['category_id'],
        name=name,
        description=(data.get('description') or '').strip() or None,
        quantity_total=quantity_total,
        quantity_remaining=quantity_remaining,
        low_stock_threshold=low_stock_threshold,
        unit=data.get('unit', 'pcs'),
        price=price,
        supplier=(data.get('supplier') or '').strip() or None,
        purchase_date=purchase_date,
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(bit)
    db.session.commit()
    return jsonify({'bit': serialize_bit(bit)}), 201


@bits_bp.route('/bits/<int:bit_id>/', methods=['PATCH'])
@jwt_required()
def update_bit(bit_id):
    user_id = get_jwt_identity()
    bit = models.Bit.query.filter_by(id=bit_id, user_id=user_id).first()
    if not bit:
        return jsonify({'msg': 'Bit not found'}), 404

    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    category_id = bit.category_id
    if 'category_id' in data:
        category_value = data['category_id']
        if isinstance(category_value, bool) or not isinstance(category_value, (int, str)):
            category = None
        else:
            try:
                category = db.session.get(models.BitCategory, category_value)
            except (TypeError, ValueError):
                category = None
        if category is None:
            return jsonify({'msg': 'Category not found'}), 400
        category_id = category.id

    try:
        quantity_total = (
            _nonnegative_int(data['quantity_total'], 'quantity_total')
            if 'quantity_total' in data else bit.quantity_total
        )
        quantity_remaining = (
            _nonnegative_int(data['quantity_remaining'], 'quantity_remaining')
            if 'quantity_remaining' in data else bit.quantity_remaining
        )
        low_stock_threshold = (
            _nonnegative_int(data['low_stock_threshold'], 'low_stock_threshold')
            if 'low_stock_threshold' in data else bit.low_stock_threshold
        )
        price = _optional_price(data['price']) if 'price' in data else bit.price
        purchase_date = (
            _purchase_date(data.get('purchase_date'))
            if 'purchase_date' in data else bit.purchase_date
        )
    except ValueError:
        return validation_error_response()
    if quantity_total <= 0:
        return jsonify({'msg': 'quantity_total must be positive'}), 400
    if quantity_remaining > quantity_total:
        return jsonify({'msg': 'quantity_remaining cannot exceed quantity_total'}), 400

    if 'name' in data:
        name = data['name'].strip() if isinstance(data['name'], str) else ''
        if not name:
            return jsonify({'msg': 'Bit name required'}), 400
        bit.name = name
    for field in ['description', 'unit', 'supplier', 'notes', 'is_active']:
        if field in data:
            setattr(bit, field, data[field])
    bit.quantity_total = quantity_total
    bit.quantity_remaining = quantity_remaining
    bit.low_stock_threshold = low_stock_threshold
    bit.price = price
    bit.purchase_date = purchase_date
    bit.category_id = category_id

    db.session.commit()
    return jsonify({'bit': serialize_bit(bit)})


@bits_bp.route('/bits/<int:bit_id>', methods=['DELETE'])
@bits_bp.route('/bits/<int:bit_id>/', methods=['DELETE'])
@jwt_required()
def delete_bit(bit_id):
    user_id = get_jwt_identity()
    bit = models.Bit.query.filter_by(id=bit_id, user_id=user_id).first()
    if not bit:
        return jsonify({'msg': 'Bit not found'}), 404
    try:
        db.session.delete(bit)
        db.session.commit()
        return jsonify({'msg': 'Bit deleted'})
    except Exception:
        current_app.logger.exception('Failed to delete bit')
        db.session.rollback()
        return jsonify({'error': 'Failed to delete bit'}), 500


# --- Restock ---

@bits_bp.route('/bits/<int:bit_id>/restock', methods=['POST'])
@jwt_required()
def restock_bit(bit_id):
    """Add stock to an existing bit."""
    user_id = get_jwt_identity()
    bit = models.Bit.query.filter_by(id=bit_id, user_id=user_id).first()
    if not bit:
        return jsonify({'msg': 'Bit not found'}), 404

    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    try:
        quantity_add = _nonnegative_int(data.get('quantity'), 'quantity')
        price = (
            _optional_price(data['price'])
            if data.get('price') is not None else bit.price
        )
        purchase_date = (
            _purchase_date(data.get('purchase_date'))
            if data.get('purchase_date') not in (None, '') else bit.purchase_date
        )
    except ValueError:
        return validation_error_response()

    if quantity_add <= 0:
        return jsonify({'msg': 'quantity must be positive'}), 400

    bit.quantity_total += quantity_add
    bit.quantity_remaining += quantity_add

    bit.price = price
    if 'supplier' in data:
        bit.supplier = (data['supplier'] or '').strip() or None
    bit.purchase_date = purchase_date

    db.session.commit()
    return jsonify({'bit': serialize_bit(bit)})


# --- Use (record consumption) ---

@bits_bp.route('/bits/<int:bit_id>/use', methods=['POST'])
@jwt_required()
def use_bit(bit_id):
    """Record bit usage, decrement quantity, create usage entry."""
    user_id = get_jwt_identity()
    bit = models.Bit.query.filter_by(id=bit_id, user_id=user_id).first()
    if not bit:
        return jsonify({'msg': 'Bit not found'}), 404

    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    try:
        requested_quantity = _nonnegative_int(
            data.get('quantity_used'),
            'quantity_used',
        )
    except ValueError:
        return validation_error_response()

    if requested_quantity <= 0:
        return jsonify({'msg': 'quantity_used must be positive'}), 400

    project_id = data.get('project_id')
    if project_id is not None:
        project = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
        if not project:
            return jsonify({'msg': 'Project not found'}), 400

    if bit.quantity_remaining <= 0:
        return jsonify({'msg': 'Bit has no remaining stock'}), 400
    quantity_used = min(requested_quantity, bit.quantity_remaining)
    bit.quantity_remaining -= quantity_used

    usage = models.BitUsage(
        bit_id=bit.id,
        project_id=project_id,
        quantity_used=quantity_used,
        date=utc_now_naive(),
        notes=(data.get('notes') or '').strip() or None,
    )
    db.session.add(usage)
    db.session.commit()
    return jsonify({'bit': serialize_bit(bit), 'usage': serialize_bit_usage(usage)})


# --- Usage history ---

@bits_bp.route('/bitusage/', methods=['GET'])
@jwt_required()
def get_bit_usage():
    user_id = get_jwt_identity()
    usages = (
        models.BitUsage.query
        .join(models.Bit, models.BitUsage.bit_id == models.Bit.id)
        .filter(models.Bit.user_id == user_id)
        .order_by(models.BitUsage.date.desc())
        .all()
    )
    return jsonify({
        'usage': [_serialize_owned_usage(usage, user_id) for usage in usages]
    })


@bits_bp.route('/bitusage/<int:usage_id>/', methods=['PATCH'])
@jwt_required()
def update_bit_usage(usage_id):
    user_id = get_jwt_identity()
    usage = (
        models.BitUsage.query
        .join(models.Bit, models.BitUsage.bit_id == models.Bit.id)
        .filter(models.BitUsage.id == usage_id, models.Bit.user_id == user_id)
        .first()
    )
    if not usage:
        return jsonify({'msg': 'Usage entry not found'}), 404

    data = _json_object()
    if data is None:
        return jsonify({'msg': 'JSON object required'}), 400
    if 'notes' in data:
        usage.notes = data['notes']
    if 'project_id' in data:
        pid = data['project_id']
        if pid is None:
            usage.project_id = None
        else:
            proj = models.Project.query.filter_by(id=pid, user_id=user_id).first()
            if not proj:
                return jsonify({'msg': 'Project not found'}), 400
            usage.project_id = pid

    db.session.commit()
    return jsonify({'usage': _serialize_owned_usage(usage, user_id)})


@bits_bp.route('/bitusage/<int:usage_id>/', methods=['DELETE'])
@jwt_required()
def delete_bit_usage(usage_id):
    user_id = get_jwt_identity()
    usage = (
        models.BitUsage.query
        .join(models.Bit, models.BitUsage.bit_id == models.Bit.id)
        .filter(models.BitUsage.id == usage_id, models.Bit.user_id == user_id)
        .first()
    )
    if not usage:
        return jsonify({'msg': 'Usage entry not found'}), 404

    db.session.delete(usage)
    db.session.commit()
    return jsonify({'msg': 'Usage entry deleted'})
