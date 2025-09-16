#!/usr/bin/env python3
import socket
import json

def test_port(host, port, test_name):
    print(f"\n=== Testing {test_name} on {host}:{port} ===")
    try:
        sock = socket.create_connection((host, port), timeout=5)
        print(f"Successfully connected to {host}:{port}")
        
        # Send a test message
        test_message = {"id": 1, "method": "mining.subscribe", "params": []}
        message_str = json.dumps(test_message) + '\n'
        sock.send(message_str.encode('utf-8'))
        
        # Try to receive response
        sock.settimeout(3)
        response = sock.recv(1024)
        print(f"Response received: {response[:100]}...")  # Show first 100 chars
        
        if response.startswith(b'<!DOCTYPE'):
            print("Received HTML response - this is the Flask HTTP server")
        elif response.startswith(b'{'):
            print("Received JSON response - this is the Stratum server")
        else:
            print(f"Unknown response format: {response[:50]}")
            
        sock.close()
        return True
        
    except socket.timeout:
        print(f"Connection timeout to {host}:{port}")
        return False
    except ConnectionRefusedError:
        print(f"Connection refused to {host}:{port} - service not running")
        return False
    except Exception as e:
        print(f"Error connecting to {host}:{port}: {e}")
        return False

def main():
    print("=== Pool Server Connection Test ===")
    
    # Test both ports
    flask_running = test_port("127.0.0.1", 5000, "Flask HTTP Server")
    stratum_running = test_port("127.0.0.1", 3333, "Stratum Server")
    
    print(f"\n=== Summary ===")
    print(f"Flask HTTP Server (port 5000): {'Running' if flask_running else 'Not running'}")
    print(f"Stratum Server (port 3333): {'Running' if stratum_running else 'Not running'}")
    
    if flask_running and not stratum_running:
        print("\nIssue: Only Flask server is running. Stratum server not started.")
        print("   Fix: Check your pool server integration (see below)")
    elif not flask_running and not stratum_running:
        print("\nIssue: No servers are running.")
        print("   Fix: Start your pool server first")
    elif stratum_running:
        print("\nBoth servers appear to be running correctly!")

if __name__ == "__main__":
    main()