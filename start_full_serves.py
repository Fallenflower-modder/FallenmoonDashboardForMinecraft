#!/usr/bin/env python3
import sys
import os
import asyncio
import threading
from server.app import app
from server.websocket_server import start_websocket_server

def run_websocket_server():
    """Run the WebSocket server in a separate thread"""
    asyncio.run(start_websocket_server())

if __name__ == "__main__":
    # Start WebSocket server in a separate thread
    websocket_thread = threading.Thread(target=run_websocket_server, daemon=True)
    websocket_thread.start()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=5000, debug=False)
