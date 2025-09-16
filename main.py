#!/usr/bin/env python3
"""
Bitcoin Mining Pool Server - Main Entry Point
Supports both HTTP REST API and Stratum protocol
"""

import os
from threading import Thread
from time import sleep

from config import load_config, get_rpc
from models import save_miners
from api import app
from stratum import StratumServer
from services import payout_processor, backup_service


def main():
    """Main function"""
    print("Starting Bitcoin Mining Pool Server...")
    
    # Load configuration
    config = load_config()
    if not config:
        print("Failed to load configuration. Exiting.")
        return
    
    rpc = get_rpc()
    if rpc:
        print("Bitcoin Core integration active")
    else:
        print("Running in TEST MODE (no Bitcoin Core)")
        print("   - Using dummy block templates")
        print("   - For ASIC mining, Bitcoin Core is required!")
    
    # Initialize database
    if not os.path.exists('miners.json'):
        save_miners({})
        print("Initialized miners database")
    
    # Start Stratum server
    stratum_server = StratumServer(port=config.get('stratum_port', 3333), config=config)
    stratum_thread = Thread(target=stratum_server.start, daemon=True)
    stratum_thread.start()
    
    # Start background services
    Thread(target=payout_processor, daemon=True).start()
    Thread(target=backup_service, daemon=True).start()
    
    print("All services started successfully")
    print(f"Stratum server: 0.0.0.0:{config.get('stratum_port', 3333)}")
    print(f"HTTP server: 0.0.0.0:{config.get('pool_port', 5000)}")
    print("Pool is ready for miners!")
    
    # Start Flask HTTP server (blocking)
    try:
        app.run(
            host='0.0.0.0', 
            port=config.get('pool_port', 5000),
            debug=False
        )
    except KeyboardInterrupt:
        print("\nShutting down pool server...")
        if stratum_server:
            stratum_server.running = False


if __name__ == '__main__':
    main()