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

    _db_initialized = False

    @app.before_request
    def _lazy_init_db():
        """Create tables + seed demo accounts on first request.
        Uses SQLite in /tmp — always available, no external DB needed.
        """
        global _db_initialized
        if not _db_initialized:
            db.create_all()
            _seed_demo_data()
            _db_initialized = True
            _logger.info('DB initialised and demo data seeded.')

    def _seed_demo_data():
        from models.models import User
        accounts = [
            {'username': 'admin',      'full_name': 'VAce Admin',      'password': 'admin123',  'role': 'admin'},
            {'username': 'demo',       'full_name': 'Demo Student',    'password': 'demo1234',  'role': 'user'},
            {'username': 'student1',   'full_name': 'Alice Johnson',   'password': 'student123','role': 'user'},
        ]
        for acc in accounts:
            if not User.query.filter_by(username=acc['username']).first():
                u = User(username=acc['username'], full_name=acc['full_name'], role=acc['role'])
                u.set_password(acc['password'])
                db.session.add(u)
        db.session.commit()

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
