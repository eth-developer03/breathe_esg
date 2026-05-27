import sys
import os

# Vercel runs this file from the backend/ root, but let's be explicit
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'breathe.settings.production')

from breathe.wsgi import application as app
