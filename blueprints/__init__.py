"""Blueprint registration for the Spoolio API."""

from blueprints.auth import auth_bp
from blueprints.account import account_bp
from blueprints.spools import spools_bp
from blueprints.inventory import inventory_bp
from blueprints.history import history_bp
from blueprints.projects import projects_bp
from blueprints.hardware import hardware_bp
from blueprints.hardware_comms import hardware_comms_bp
from blueprints.firmware import firmware_bp
from blueprints.admin import admin_bp
from blueprints.bits import bits_bp
from blueprints.spoolman import spoolman_bp


def register_blueprints(app):
    """Register all API sub-blueprints under the ``/api`` prefix."""
    prefix = '/api'
    app.register_blueprint(auth_bp, url_prefix=prefix)
    app.register_blueprint(account_bp, url_prefix=prefix)
    app.register_blueprint(spools_bp, url_prefix=prefix)
    app.register_blueprint(inventory_bp, url_prefix=prefix)
    app.register_blueprint(history_bp, url_prefix=prefix)
    app.register_blueprint(projects_bp, url_prefix=prefix)
    app.register_blueprint(hardware_bp, url_prefix=prefix)
    app.register_blueprint(hardware_comms_bp, url_prefix=prefix)
    app.register_blueprint(firmware_bp, url_prefix=prefix)
    app.register_blueprint(admin_bp, url_prefix=prefix)
    app.register_blueprint(bits_bp, url_prefix=prefix)
    # Spoolman-compatible API: carries its own full paths
    # (/spoolman/<token>/api/v1/... and /api/integrations/spoolman), so it is
    # registered without the shared /api prefix.
    app.register_blueprint(spoolman_bp)
