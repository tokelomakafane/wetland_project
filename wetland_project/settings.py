import os
from pathlib import Path
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', get_random_secret_key())

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

CSRF_TRUSTED_ORIGINS = [
    'https://localhost:8000',
    'https://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # 'django.contrib.gis',  # GeoDjango (commented out - using JSON geometry instead)
    'mapping',
    'drone',
    'early_warning',
    'wetlands',
    'timelapse',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'wetland_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wetland_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # Regular SQLite (not spatialite)
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# GIS Configuration (NOT USED - using JSON geometry for simplicity)
GIS_ENABLED = False

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Maseru'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Earth Engine Configuration ──────────────────────────────────────
EE_PROJECT = os.environ.get('EE_PROJECT', 'tokelo-329815')
# Secondary EE project fallback when caller lacks permission on EE_PROJECT.
EE_FALLBACK_PROJECT = os.environ.get('EE_FALLBACK_PROJECT', 'crypto-analogy-444606-s2')
# Replace with your actual GEE asset ID after running the export task
EE_ASSET_ID = 'projects/tokelo-329815/assets/Lesotho_Wetland_Classification_2013_2023'
# Path to your GEE service account key JSON (for production)
# For development, ee.Authenticate() is used instead
EE_SERVICE_ACCOUNT_KEY = os.environ.get('EE_SERVICE_ACCOUNT_KEY', '')
