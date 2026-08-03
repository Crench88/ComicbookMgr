"""
WSGI entry point template for PythonAnywhere.

On PythonAnywhere, open the Web tab → WSGI configuration file, replace the
sample code with this file's contents, and set YOUR_USERNAME (or set
COMICBOOKMGR_HOME).
"""

import os
import sys

# --- PythonAnywhere: set this to your cloned project path ---
PROJECT_HOME = os.environ.get(
    'COMICBOOKMGR_HOME',
    '/home/YOUR_USERNAME/ComicbookMgr',
)

if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

os.chdir(PROJECT_HOME)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_HOME, '.env'))

from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app

application = create_app()
# PythonAnywhere terminates TLS in front of the app.
application.wsgi_app = ProxyFix(application.wsgi_app, x_for=1, x_proto=1, x_host=1)
