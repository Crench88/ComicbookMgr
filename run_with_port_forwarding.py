#!/usr/bin/env python3
"""
Run Flask app with port forwarding to mask the port number.
This script runs the Flask app on port 5000 but makes it accessible on port 80.
"""

import socket
import threading
import sys
from app import create_app

def forward_port(source_port, dest_port):
    """Forward traffic from source_port to dest_port."""
    try:
        # Create socket for incoming connections
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('0.0.0.0', source_port))
        server.listen(5)
        
        print(f"🔀 Port forwarding: {source_port} -> {dest_port}")
        
        while True:
            client, addr = server.accept()
            print(f"📡 Connection from {addr}")
            
            # Create connection to destination
            dest = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dest.connect(('127.0.0.1', dest_port))
            
            # Start forwarding in both directions
            threading.Thread(target=forward_data, args=(client, dest)).start()
            threading.Thread(target=forward_data, args=(dest, client)).start()
            
    except Exception as e:
        print(f"❌ Port forwarding error: {e}")

def forward_data(source, dest):
    """Forward data from source socket to destination socket."""
    try:
        while True:
            data = source.recv(4096)
            if not data:
                break
            dest.send(data)
    except:
        pass
    finally:
        source.close()
        dest.close()

def run_flask_with_forwarding():
    """Run Flask app with port forwarding."""
    print("🚀 Starting Comic Book Manager with port forwarding...")
    print("📝 Flask will run on port 5000")
    print("🌐 Access your app at: http://localhost (no port number needed)")
    print()
    
    # Start port forwarding in a separate thread
    forwarding_thread = threading.Thread(target=forward_port, args=(80, 5000))
    forwarding_thread.daemon = True
    forwarding_thread.start()
    
    # Create and run Flask app
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    try:
        run_flask_with_forwarding()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        sys.exit(0)
