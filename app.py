import os
import logging
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.pool import NullPool
from models.database import db

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'quiz_master.db')

    secret = os.environ.get('SECRET_KEY')
    if not secret:
        logger.warning(
            "SECRET_KEY not set in environment — using insecure fallback. "
            "Set SECRET_KEY in production!"
        )
        secret = 'dev-fallback-secret-key-change-in-prod'

    app.config['SECRET_KEY'] = secret

    # Build the database URI — fix legacy 'postgres://' scheme from Heroku/Supabase
    # Use pg8000 dialect (pure Python, works on all serverless runtimes)
    database_url = os.environ.get('DATABASE_URL') or ('sqlite:///' + DB_PATH)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql+pg8000://', 1)
    elif database_url.startswith('postgresql://') and 'supabase' in database_url:
        database_url = database_url.replace('postgresql://', 'postgresql+pg8000://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour token expiry

    # Serverless connection pooling — use NullPool on Vercel to prevent
    # connection exhaustion (each Lambda invocation gets its own connection).
    # connect_timeout prevents pg8000 from hanging indefinitely if the
    # Supabase free-tier instance is paused / slow to accept connections.
    if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('VERCEL'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': NullPool,
            'connect_args': {'timeout': 8},
        }

    db.init_app(app)
    csrf.init_app(app)
    app.app_context().push()  # Needed so current_app proxy resolves in controllers module
    return app

app = create_app()

# Import controllers as a side-effect to register routes and error handlers.
# Do NOT use `from controllers.controllers import *` — that would overwrite `app`
# with controllers.py's module-level `app = current_app` alias.
import controllers.controllers  # noqa: F401

if __name__ == '__main__':
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'quiz_master.db')
    if not os.path.exists(DB_PATH):
        from controllers.controllers import init_db
        init_db()
    else:
        from controllers.controllers import create_update_default_admin
        create_update_default_admin()

    app.run(debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
