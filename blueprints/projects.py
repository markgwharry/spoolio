"""Project routes."""

import csv
import datetime
import io
import math

from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db
import models
from time_utils import utc_now_naive

projects_bp = Blueprint('projects', __name__)


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _optional_budget(data):
    value = data.get('budget_grams')
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError
    return parsed


def _csv_safe(value):
    """Prevent spreadsheet formulas in user-controlled CSV text cells."""
    text = '' if value is None else str(value)
    if text.lstrip(' \t\r').startswith(('=', '+', '-', '@')):
        return "'" + text
    return text


def _owned_spool_history(project_id, user_id):
    return (
        models.SpoolHistory.query
        .join(
            models.FilamentSpool,
            models.SpoolHistory.spool_id == models.FilamentSpool.id,
        )
        .filter(
            models.SpoolHistory.project_id == project_id,
            models.FilamentSpool.user_id == user_id,
        )
    )


def _owned_bit_usage(project_id, user_id):
    return (
        models.BitUsage.query
        .join(models.Bit, models.BitUsage.bit_id == models.Bit.id)
        .filter(
            models.BitUsage.project_id == project_id,
            models.Bit.user_id == user_id,
        )
    )


@projects_bp.route('/projects/', methods=['GET', 'POST'])
@jwt_required()
def projects():
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()
    if request.method == 'GET':
        projs = models.Project.query.filter((models.Project.user_id == user_id) | (models.Project.user_id.is_(None))).all()
        return jsonify({'projects': [{'id': p.id, 'name': p.name, 'description': p.description, 'status': getattr(p, 'status', 'active') or 'active', 'budget_grams': getattr(p, 'budget_grams', None), 'created_at': p.created_at.isoformat() if p.created_at else None} for p in projs]})
    else:
        data = _json_object()
        if data is None:
            return jsonify({'msg': 'JSON object required'}), 400
        raw_name = data.get('name')
        raw_description = data.get('description')
        if not isinstance(raw_name, str):
            return jsonify({'msg': 'Project name required'}), 400
        if raw_description is not None and not isinstance(raw_description, str):
            return jsonify({'msg': 'Project description must be text'}), 400
        name = raw_name.strip()
        description = (raw_description or '').strip() or None
        if not name:
            return jsonify({'msg': 'Project name required'}), 400
        status = data.get('status', 'active')
        if status not in ('active', 'completed', 'archived'):
            status = 'active'
        try:
            budget_grams = _optional_budget(data)
        except (TypeError, ValueError):
            return jsonify({'msg': 'budget_grams must be a non-negative number'}), 400
        p = models.Project(name=name, description=description, user_id=user_id, status=status, budget_grams=budget_grams)
        db.session.add(p)
        db.session.commit()
        return jsonify({'id': p.id, 'name': p.name, 'description': p.description, 'status': p.status, 'budget_grams': p.budget_grams}), 201


@projects_bp.route('/projects/<int:project_id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def project_detail(project_id):
    """Get, update, or delete a single project."""
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()

    project = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
    if not project:
        return jsonify({'msg': 'Project not found'}), 404

    if request.method == 'GET':
        return jsonify({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'status': getattr(project, 'status', 'active') or 'active',
            'budget_grams': getattr(project, 'budget_grams', None),
            'created_at': project.created_at.isoformat() if project.created_at else None
        })

    elif request.method == 'PUT':
        data = _json_object()
        if data is None:
            return jsonify({'msg': 'JSON object required'}), 400
        if 'name' in data:
            raw_name = data.get('name')
            if not isinstance(raw_name, str):
                return jsonify({'msg': 'Project name cannot be empty'}), 400
            name = raw_name.strip()
            if not name:
                return jsonify({'msg': 'Project name cannot be empty'}), 400
            project.name = name
        if 'description' in data:
            description = data.get('description')
            if description is not None and not isinstance(description, str):
                return jsonify({'msg': 'Project description must be text'}), 400
            project.description = (description or '').strip() or None
        if 'status' in data:
            status = data['status']
            if status in ('active', 'completed', 'archived'):
                project.status = status
        if 'budget_grams' in data:
            try:
                project.budget_grams = _optional_budget(data)
            except (TypeError, ValueError):
                return jsonify({'msg': 'budget_grams must be a non-negative number'}), 400
        db.session.commit()
        return jsonify({
            'id': project.id,
            'name': project.name,
            'description': project.description,
            'status': getattr(project, 'status', 'active') or 'active',
            'budget_grams': getattr(project, 'budget_grams', None)
        })

    else:  # DELETE
        models.SpoolHistory.query.filter_by(project_id=project_id).update({'project_id': None})
        models.BitUsage.query.filter_by(project_id=project_id).update({'project_id': None})
        db.session.delete(project)
        db.session.commit()
        return jsonify({'msg': 'Project deleted'}), 200


@projects_bp.route('/projects/<int:project_id>/analytics')
@jwt_required()
def project_analytics(project_id):
    """Return simple analytics for a project over the last 90 days by default."""
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()
    try:
        days = max(1, min(int(request.args.get('days', 90)), 365))
    except (ValueError, TypeError):
        days = 90
    project = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
    if not project:
        return jsonify({'msg': 'Project not found'}), 404
    since = utc_now_naive() - datetime.timedelta(days=days)
    entries = _owned_spool_history(project_id, user_id).filter(
        models.SpoolHistory.date >= since
    ).all()
    total_g = sum(e.weight_used or 0 for e in entries)
    spool_ids = set(e.spool_id for e in entries)
    spool_cache = {s.id: s for s in models.FilamentSpool.query.filter(models.FilamentSpool.id.in_(spool_ids)).all()} if spool_ids else {}
    material_cache = {m.id: m.name for m in models.Material.query.all()}
    cost = 0.0
    material_breakdown = {}
    for e in entries:
        spool = spool_cache.get(e.spool_id)
        if not spool:
            continue
        mat_name = material_cache.get(spool.material_id, 'Unknown')
        if mat_name not in material_breakdown:
            material_breakdown[mat_name] = {'grams': 0.0, 'cost': 0.0}
        material_breakdown[mat_name]['grams'] += float(e.weight_used or 0)
        price = getattr(spool, 'price', None)
        if price and (spool.weight_start or 0) > 0:
            entry_cost = (price / float(spool.weight_start)) * float(e.weight_used)
            cost += entry_cost
            material_breakdown[mat_name]['cost'] += entry_cost
    materials_list = [
        {'material': name, 'grams': round(data['grams'], 2), 'cost': round(data['cost'], 2)}
        for name, data in sorted(material_breakdown.items(), key=lambda x: x[1]['grams'], reverse=True)
    ]
    by_day = {}
    for e in entries:
        d = (e.date.date().isoformat() if e.date else None)
        if not d:
            continue
        by_day[d] = by_day.get(d, 0) + float(e.weight_used or 0)
    timeline = sorted([{'date': d, 'grams': g} for d, g in by_day.items()], key=lambda x: x['date'])

    # --- Bits analytics ---
    bit_entries = _owned_bit_usage(project_id, user_id).filter(
        models.BitUsage.date >= since
    ).all()
    bits_total_used = sum(e.quantity_used or 0 for e in bit_entries)
    bit_ids = set(e.bit_id for e in bit_entries)
    bit_cache = {b.id: b for b in models.Bit.query.filter(models.Bit.id.in_(bit_ids)).options(db.joinedload(models.Bit.category)).all()} if bit_ids else {}
    bits_cost = 0.0
    category_breakdown = {}
    for e in bit_entries:
        bit = bit_cache.get(e.bit_id)
        if not bit:
            continue
        cat_name = bit.category.name if bit.category else 'Other'
        if cat_name not in category_breakdown:
            category_breakdown[cat_name] = {'count': 0, 'cost': 0.0}
        category_breakdown[cat_name]['count'] += e.quantity_used or 0
        if bit.price and (bit.quantity_total or 0) > 0:
            entry_cost = (bit.price / float(bit.quantity_total)) * float(e.quantity_used)
            bits_cost += entry_cost
            category_breakdown[cat_name]['cost'] += entry_cost
    bits_breakdown = [
        {'category': name, 'count': data['count'], 'cost': round(data['cost'], 2)}
        for name, data in sorted(category_breakdown.items(), key=lambda x: x[1]['count'], reverse=True)
    ]

    return jsonify({
        'project': {'id': project.id, 'name': project.name, 'status': getattr(project, 'status', 'active') or 'active'},
        'days': days,
        'total_grams': total_g,
        'estimated_cost': round(cost + bits_cost, 2),
        'filament_cost': round(cost, 2),
        'budget_grams': getattr(project, 'budget_grams', None),
        'materials': materials_list,
        'timeline': timeline,
        'entry_count': len(entries),
        'bits_total_used': bits_total_used,
        'bits_estimated_cost': round(bits_cost, 2),
        'bits_breakdown': bits_breakdown,
        'bits_entry_count': len(bit_entries),
    })


@projects_bp.route('/projects/<int:project_id>/export.csv')
@jwt_required()
def project_export_csv(project_id):
    try:
        user_id = int(get_jwt_identity())
    except Exception:
        user_id = get_jwt_identity()
    project = models.Project.query.filter_by(id=project_id, user_id=user_id).first()
    if not project:
        return jsonify({'msg': 'Project not found'}), 404
    entries = _owned_spool_history(project_id, user_id).order_by(
        models.SpoolHistory.date.desc()
    ).all()
    spool_ids = set(e.spool_id for e in entries)
    spool_cache = {s.id: s for s in models.FilamentSpool.query.filter(models.FilamentSpool.id.in_(spool_ids)).all()} if spool_ids else {}
    material_cache = {m.id: m.name for m in models.Material.query.all()}
    color_cache = {c.id: c.name for c in models.Color.query.all()}
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow([
        'type', 'date', 'item_id', 'name', 'category',
        'quantity', 'unit', 'cost', 'notes',
    ])
    for e in entries:
        dt = e.date.isoformat() if e.date else ''
        notes = _csv_safe((e.notes or '').replace('\n', ' '))
        spool = spool_cache.get(e.spool_id)
        mat_name = material_cache.get(spool.material_id, '') if spool else ''
        col_name = color_cache.get(spool.color_id, '') if spool else ''
        item_name = _csv_safe(f'{mat_name} {col_name}'.strip())
        entry_cost = ''
        if spool:
            price = getattr(spool, 'price', None)
            if price and (spool.weight_start or 0) > 0:
                entry_cost = str(round((price / float(spool.weight_start)) * float(e.weight_used), 4))
        writer.writerow([
            'filament', dt, e.spool_id, item_name, 'Filament',
            e.weight_used, 'g', entry_cost, notes,
        ])

    # Bit usage rows
    bit_entries = _owned_bit_usage(project_id, user_id).order_by(
        models.BitUsage.date.desc()
    ).all()
    bit_ids = set(e.bit_id for e in bit_entries)
    bit_cache = {b.id: b for b in models.Bit.query.filter(models.Bit.id.in_(bit_ids)).options(db.joinedload(models.Bit.category)).all()} if bit_ids else {}
    for e in bit_entries:
        dt = e.date.isoformat() if e.date else ''
        notes = _csv_safe((e.notes or '').replace('\n', ' '))
        bit = bit_cache.get(e.bit_id)
        bit_name = _csv_safe(bit.name if bit else '')
        cat_name = _csv_safe(bit.category.name if bit and bit.category else '')
        unit = _csv_safe(bit.unit if bit else 'pcs')
        entry_cost = ''
        if bit and bit.price and (bit.quantity_total or 0) > 0:
            entry_cost = str(round((bit.price / float(bit.quantity_total)) * float(e.quantity_used), 4))
        writer.writerow([
            'bit', dt, e.bit_id, bit_name, cat_name,
            e.quantity_used, unit, entry_cost, notes,
        ])

    return Response(output.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename=project_{project_id}_usage.csv'
    })
