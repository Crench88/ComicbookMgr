#!/usr/bin/env python3
# Comic Book Manager Startup Script
# Run this script to start your app on port 80

import os
import sys
from app import create_app

if __name__ == '__main__':
    print("Starting Comic Book Manager on port 80...")
    print("Access your app at: http://comicbook.local")
    print("Press Ctrl+C to stop")
    print()
    
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=80)
