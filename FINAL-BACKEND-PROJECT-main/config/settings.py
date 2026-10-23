"""
Django settings for the HubSpot Deals Extraction Service.

Settings are loaded from environment variables (via python-dotenv).
Never commit real secrets to version control.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env if it exists (silently ignored if missing)
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-change-this-in-production",
)

DEBUG = os.environ.get("DEBUG", "True").strip().lower() in ("1", "true", "yes")

ALLOWED_HOSTS: list[str] = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")
    if h.strip()
]

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    # Local
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_database_url = os.environ.get("DATABASE_URL", "").strip()

if _database_url and _database_url.startswith("postgresql"):
    # Basic PostgreSQL support (requires psycopg2/psycopg)
    import re

    _m = re.match(
        r"postgresql(?:\+\w+)?://(?P<user>[^:]+):(?P<pw>[^@]+)@(?P<host>[^:/]+)"
        r"(?::(?P<port>\d+))?/(?P<name>.+)",
        _database_url,
    )
    if _m:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": _m.group("name"),
                "USER": _m.group("user"),
                "PASSWORD": _m.group("pw"),
                "HOST": _m.group("host"),
                "PORT": _m.group("port") or "5432",
            }
        }
    else:
        raise ValueError(f"Cannot parse DATABASE_URL: {_database_url}")
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "api.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "HubSpot Deals Extraction Service API",
    "DESCRIPTION": (
        "REST API for the HubSpot Deals DLT Integration Service.\n\n"
        "Start extraction jobs, poll their status, retrieve paginated deal data, "
        "cancel or remove jobs, and view aggregated statistics.\n\n"
        "Authentication is job-level: supply a HubSpot private-app access token "
        "when starting a scan via POST /api/v1/scan/start."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {"name": "API Support"},
    "LICENSE": {"name": "MIT"},
}

# ---------------------------------------------------------------------------
# HubSpot API configuration (read by services)
# ---------------------------------------------------------------------------
HUBSPOT_BASE_URL = os.environ.get("HUBSPOT_BASE_URL", "https://api.hubapi.com")
HUBSPOT_TIMEOUT = int(os.environ.get("HUBSPOT_TIMEOUT", "30"))
HUBSPOT_RATE_LIMIT_REQUESTS = int(os.environ.get("HUBSPOT_RATE_LIMIT_REQUESTS", "150"))
HUBSPOT_RATE_LIMIT_PERIOD = int(os.environ.get("HUBSPOT_RATE_LIMIT_PERIOD", "10"))

# ---------------------------------------------------------------------------
# Pipeline settings
# ---------------------------------------------------------------------------
PIPELINE_NAME = os.environ.get("PIPELINE_NAME", "hubspot_deals")
DB_SCHEMA = os.environ.get("DB_SCHEMA", "hubspot_deals")
CHECKPOINT_EVERY = int(os.environ.get("CHECKPOINT_EVERY", "5"))

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"

# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "services": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "api": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
    },
}
