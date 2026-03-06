"""
config.py — Centralised configuration for VAce_QuizMaster.

Usage in app.py:
    app.config.from_object(config_by_name[os.environ.get('FLASK_ENV', 'development')])
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared by all environments."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'CHANGE-ME-IN-PRODUCTION'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL')
        or 'sqlite:///' + os.path.join(BASE_DIR, 'quiz_master.db')
    )


class ProductionConfig(Config):
    DEBUG = False
    # For Vercel / cloud deploy replace with a persistent DB URL:
    #   DATABASE_URL=postgresql://user:pass@host/dbname
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL')
        or 'sqlite:///' + os.path.join(BASE_DIR, 'quiz_master.db')
    )


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False          # Disable CSRF in tests
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SECRET_KEY = 'test-secret-key'


config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
}
