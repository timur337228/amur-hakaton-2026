from __future__ import annotations

import os
from pathlib import Path

from core.api.app.config import get_settings


def _split_csv_env(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "budget-analytics-dev-secret-key")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = _split_csv_env(os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver"))

INSTALLED_APPS = [
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.web.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "web" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [],
        },
    }
]

WSGI_APPLICATION = "core.web.wsgi.application"
ASGI_APPLICATION = "core.web.asgi.application"

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    BASE_DIR / "core" / "web" / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
BUDGET_API_BASE_URL = os.getenv("BUDGET_API_BASE_URL", "http://localhost:8000").rstrip("/")
BUDGET_DEPLOY_MODE = get_settings().deploy_mode
