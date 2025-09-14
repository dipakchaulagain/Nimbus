import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///instance/dev.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SCHEDULER_API_ENABLED = False
    VCENTER_SYNC_INTERVAL = int(os.getenv("VCENTER_SYNC_INTERVAL", "30"))

    # Flask session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_ABSOLUTE_HOURS", "3")))  # absolute timeout
    REMEMBER_COOKIE_DURATION = timedelta(hours=int(os.getenv("SESSION_ABSOLUTE_HOURS", "3")))
    SESSION_INACTIVITY_MINUTES = int(os.getenv("SESSION_INACTIVITY_MINUTES", "30"))  # custom (we'll enforce)

    # Harden SQLAlchemy connection pool to avoid stale/leaked connections
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("SQL_POOL_RECYCLE", "1800")),  # 30 min
        # Optional tuning knobs; can be overridden by env if needed
        "pool_size": int(os.getenv("SQL_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("SQL_MAX_OVERFLOW", "20")),
    }


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    env = os.getenv("FLASK_ENV", "development")
    return config_by_name.get(env, DevelopmentConfig)

