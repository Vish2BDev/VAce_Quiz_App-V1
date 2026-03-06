"""
tests/conftest.py — Pytest session configuration.

This file is loaded by pytest BEFORE any test module imports, which means
the DATABASE_URL environment variable is set before `app.py` is imported.
Flask-SQLAlchemy creates the engine lazily on first use; by setting DATABASE_URL
here we ensure the engine is built pointing at the temp test DB — not the
production quiz_master.db.
"""
import os
import sys
import tempfile
import atexit

# Create a fresh temp file for the test session
_FD, _DB_PATH = tempfile.mkstemp(suffix='.db', prefix='test_vace_')

# Set env vars that app.py reads on import
os.environ['DATABASE_URL'] = f'sqlite:///{_DB_PATH}'
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-tests-only')
os.environ['FLASK_TESTING'] = '1'


def _cleanup():
    try:
        os.close(_FD)
    except OSError:
        pass
    try:
        if os.path.exists(_DB_PATH):
            os.unlink(_DB_PATH)
    except OSError:
        pass


atexit.register(_cleanup)
