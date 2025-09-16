"""
Configuration management for the mining pool
"""

import json

try:
    from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
    HAS_BITCOIN_RPC = True
except ImportError:
    print("Warning: bitcoinrpc not available, running in test mode")
    HAS_BITCOIN_RPC = False
    class JSONRPCException(Exception):
        pass


# Global configuration dictionary
config = {}
rpc = None


def load_config():
    """Load configuration from config.json"""
    global config, rpc
    
    try:
        with open('config.json') as f:
            config = json.load(f)
        print("Configuration loaded successfully")
    except FileNotFoundError:
        print("config.json not found!")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in config.json: {e}")
        return None
    
    # Initialize Bitcoin RPC connection
    if HAS_BITCOIN_RPC:
        try:
            rpc = AuthServiceProxy(
                f"http://{config['rpc_user']}:{config['rpc_password']}@"
                f"{config['rpc_host']}:{config['rpc_port']}"
            )
            # Test connection
            rpc.getblockchaininfo()
            print("Bitcoin RPC connection established")
        except Exception as e:
            print(f"Bitcoin RPC connection failed: {e}")
            print("Running in test mode without Bitcoin Core")
            rpc = None
    else:
        rpc = None
    
    return config


def get_config():
    """Get the current configuration"""
    return config


def get_rpc():
    """Get the RPC connection"""
    return rpc