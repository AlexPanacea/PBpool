"""
Bitcoin RPC related functions and block template management
"""

import time


def get_rpc():
    """Get RPC connection from config module"""
    from config import get_rpc as _get_rpc
    return _get_rpc()


# Initialize RPC connection
rpc = None


def get_block_template(address=None):
    """Get real block template from Bitcoin Core"""
    global rpc
    if not rpc:
        rpc = get_rpc()
    
    if not rpc:
        # Fallback dummy template for testing
        return {
            'version': 536870912,
            'previousblockhash': '0' * 64,
            'transactions': [],
            'coinbaseaux': {'flags': ''},
            'coinbasevalue': 625000000,  # 6.25 BTC in satoshis
            'target': '0' * 56 + 'ffff0000',
            'mintime': int(time.time()) - 3600,
            'mutable': ['time', 'transactions', 'prevblock'],
            'noncerange': '00000000ffffffff',
            'sigoplimit': 20000,
            'sizelimit': 1000000,
            'curtime': int(time.time()),
            'bits': '207fffff',
            'height': 1
        }
    
    try:
        params = {
            "rules": ["segwit"],
            "capabilities": ["coinbasetxn", "workid", "coinbase/append"]
        }
        if address:
            params["coinbasetxn"] = {"mineraddress": address}
            
        template = rpc.getblocktemplate(params)
        print(f"Got real block template for height {template['height']}")
        return template
    except Exception as e:
        print(f"Failed to get block template: {e}")
        print("Using fallback template")
        # Return dummy template on error
        return get_block_template(None)  # Recursion with rpc=None fallback


def submit_block(block_hex):
    """Submit found block to Bitcoin network"""
    global rpc
    if not rpc:
        rpc = get_rpc()
    
    if not rpc:
        print("Would submit block to network (test mode)")
        return True
        
    try:
        result = rpc.submitblock(block_hex)
        if result is None:
            print("BLOCK ACCEPTED BY NETWORK!")
            return True
        else:
            print(f"Block rejected: {result}")
            return False
    except Exception as e:
        print(f"Block submission failed: {e}")
        return False


def send_to_address(address, amount):
    """Send Bitcoin to address (for payouts)"""
    global rpc
    if not rpc:
        rpc = get_rpc()
    
    if not rpc:
        print(f"Would pay {amount} BTC to {address} (test mode)")
        return "test_txid"
        
    try:
        txid = rpc.sendtoaddress(address, amount)
        return txid
    except Exception as e:
        raise Exception(f"Payment failed: {e}")