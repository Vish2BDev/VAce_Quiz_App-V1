import sys
import os
import traceback
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('VERCEL', '1')

_logger = logging.getLogger(__name__)
_startup_error = None

try:
    from app import app
    from models.database import db
    from controllers.controllers import create_update_default_admin

    _db_initialized = False

    @app.before_request
    def _lazy_init_db():
        """Create tables and seed admin on first request (lazy cold-start init)."""
        global _db_initialized
        if not _db_initialized:
            try:
                db.create_all()
                create_update_default_admin()
                _db_initialized = True
                _logger.info('DB initialised on first request.')
            except Exception as e:
                _logger.error('DB init failed: %s', e, exc_info=True)

except Exception:
    _startup_error = traceback.format_exc()
    from flask import Flask as _Flask
    app = _Flask(__name__)

    @app.route('/', defaults={'_p': ''})
    @app.route('/<path:_p>')
    def _startup_error_handler(_p):
        return (
            f'<h2>Startup Error</h2><pre>{_startup_error}</pre>',
            500,
        )

__all__ = ['app']
