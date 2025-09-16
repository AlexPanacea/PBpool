"""
Data models and database functions for the mining pool
"""

import os
import json
import shutil
import time
from datetime import datetime
from threading import Lock

miners_lock = Lock()


def load_miners():
    """Load miner data from JSON file"""
    if not os.path.exists('miners.json'):
        return {}
    
    try:
        with open('miners.json') as f:
            return json.load(f)
    except:
        try:
            if os.path.exists('miners.json.bak'):
                shutil.copy('miners.json.bak', 'miners.json')
                with open('miners.json') as f:
                    return json.load(f)
        except:
            pass
        return {}


def save_miners(miners):
    """Save miner data to JSON file with backup"""
    with miners_lock:
        if os.path.exists('miners.json'):
            shutil.copy('miners.json', 'miners.json.bak')
        
        with open('miners.json', 'w') as f:
            json.dump(miners, f, indent=2)


def process_share(worker_address, nonce, height=1, pool_fee=0.02):
    """Process a share submission"""
    miners = load_miners()
    
    if worker_address not in miners:
        miners[worker_address] = {
            'shares': 0,
            'blocks': [],
            'immature_balance': 0.0,
            'paid': 0.0,
            'last_share': datetime.now().isoformat(),
            'first_share': datetime.now().isoformat()
        }
    
    miners[worker_address]['shares'] += 1
    miners[worker_address]['last_share'] = datetime.now().isoformat()
    
    # Check for "block found" (every 1000 shares for testing)
    block_found = False
    reward = 0.0
    
    if miners[worker_address]['shares'] % 1000 == 0:
        block_reward = 3.125 * (1 - pool_fee)
        miners[worker_address]['blocks'].append({
            'height': height,
            'hash': f"block_{int(time.time())}",
            'value': block_reward,
            'status': 'immature',
            'timestamp': datetime.now().isoformat()
        })
        miners[worker_address]['immature_balance'] += block_reward
        block_found = True
        reward = block_reward
        print(f"BLOCK FOUND by {worker_address}! Reward: {block_reward} BTC")
    
    save_miners(miners)
    return {'block_found': block_found, 'reward': reward}


def get_miner_stats(address):
    """Get statistics for a specific miner"""
    miners = load_miners()
    
    if address not in miners:
        return None
    
    miner = miners[address]
    mature_balance = sum(
        block['value'] for block in miner['blocks']
        if block.get('status') == 'confirmed'
    )
    
    return {
        'address': address,
        'shares': miner['shares'],
        'blocks_found': len(miner['blocks']),
        'immature_balance': miner['immature_balance'],
        'mature_balance': mature_balance,
        'total_paid': miner.get('paid', 0.0),
        'last_share': miner['last_share'],
        'first_share': miner.get('first_share')
    }