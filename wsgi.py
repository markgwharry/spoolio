import os

from app import create_app


def make_app():
    app = create_app()
    static_dir = os.environ.get("SPOOLIO_STATIC_DIR")
    if static_dir:
        app.static_folder = static_dir
    return app


app = make_app()
