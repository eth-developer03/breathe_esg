from .base import *
import os
import dj_database_url

DEBUG = False
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Vercel sets VERCEL_URL automatically (without https://)
# Also accept any custom domain set via ALLOWED_HOSTS env var
_vercel_url = os.environ.get('VERCEL_URL', '')
_extra_hosts = config(
    'ALLOWED_HOSTS',
    default='',
    cast=lambda v: [s.strip() for s in v.split(',') if s.strip()]
)
ALLOWED_HOSTS = [
    'localhost', '127.0.0.1',
    '.vercel.app',
    '.onrender.com',
    '.railway.app',
] + ([_vercel_url] if _vercel_url else []) + _extra_hosts

# Allow all origins that hit a JWT-authenticated API — CORS is not the security boundary
CORS_ALLOW_ALL_ORIGINS = True

# Database — Vercel Postgres / Neon / Railway all provide DATABASE_URL
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config(
        conn_max_age=600,
        ssl_require=True,
    )

# JSON-only — disables browsable API which references DRF static files not available on Vercel
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
}

# Don't require a pre-built manifest; collectstatic may not run in serverless builds
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
