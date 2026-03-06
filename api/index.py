"""
api/index.py — Vercel serverless entry point.

Vercel's Python runtime expects a WSGI-callable named 'app' (or exported from this file).
This module ensures the project root is on sys.path so all imports resolve correctly.

IMPORTANT — SQLite on Vercel:
  Vercel functions run in an ephemeral, read-only filesystem (except /tmp).
  SQLite files written to the project directory will NOT persist between
  invocations and will NOT survive redeploys.

  For persistent data on Vercel, replace SQLite with a hosted database:
    • PlanetScale  (MySQL-compatible, free tier)  — set DATABASE_URL env var
    • Supabase     (PostgreSQL, free tier)         — set DATABASE_URL env var
    • Railway      (PostgreSQL/MySQL, free tier)   — set DATABASE_URL env var
    • Neon         (serverless PostgreSQL)         — set DATABASE_URL env var

  Update config.py → ProductionConfig.SQLALCHEMY_DATABASE_URI to read from
  os.environ.get('DATABASE_URL') (already done).
  Install the driver:  pip install psycopg2-binary  (PostgreSQL)
                                   PyMySQL          (MySQL)
"""

import sys
import os

# Make the project root importable regardless of where Vercel invokes this file
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('FLASK_ENV', 'production')

from app import app  # noqa: E402  — WSGI application
from models.database import db
from controllers.controllers import create_update_default_admin

import logging
_logger = logging.getLogger(__name__)

# Lazy DB initialisation — runs on the FIRST real request, not at import time.
# This prevents cold-start timeouts on Vercel when Supabase free-tier is paused.
_db_initialized = False

@app.before_request
def _lazy_init_db():
    global _db_initialized
    if not _db_initialized:
        try:
            db.create_all()
            create_update_default_admin()
            _db_initialized = True
            _logger.info("DB initialised successfully on first request.")
        except Exception as e:
            _logger.error("DB init failed: %s", e, exc_info=True)
            # Don't set _db_initialized = True so we retry on next request

# Vercel looks for `app` at module level
__all__ = ['app']
