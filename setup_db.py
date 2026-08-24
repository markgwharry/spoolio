#!/usr/bin/env python3
"""Upgrade the Spoolio database and seed its shared reference data."""

from pathlib import Path

from flask_migrate import upgrade

from app import create_app
from extensions import db
import models


BASE_DIR = Path(__file__).resolve().parent


def seed_initial_data():
    """Idempotently seed shared lookup values in one transaction."""
    materials = ['PLA', 'PETG', 'ABS']
    colors = ['white', 'grey', 'red', 'black', 'clear']
    manufacturers = ['Bambu', 'Sunlu', 'Elegoo']
    spool_types = [
        {'name': 'Bambu spool', 'compatible_with_ams': True},
        {'name': 'Sunlu refill', 'compatible_with_ams': False},
        {'name': 'Elegoo spool', 'compatible_with_ams': False},
    ]

    for model, names in (
        (models.Material, materials),
        (models.Color, colors),
        (models.Manufacturer, manufacturers),
    ):
        for name in names:
            if model.query.filter_by(name=name).first() is None:
                db.session.add(model(name=name))

    for spool_type in spool_types:
        if models.SpoolType.query.filter_by(name=spool_type['name']).first() is None:
            db.session.add(models.SpoolType(**spool_type))

    db.session.commit()

    print("Reference data is present.")

def main():
    print("Upgrading Spoolio database...")

    app = create_app()
    with app.app_context():
        upgrade(directory=str(BASE_DIR / 'migrations'))
        seed_initial_data()

    print("Database setup complete.")

if __name__ == '__main__':
    main()
