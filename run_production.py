"""
Production entry point for the Comic Book Collection Manager application.
"""

import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Production configuration
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    app.run(debug=debug_mode, host=host, port=port)
