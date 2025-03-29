import json
import os
import hashlib
import struct
import re
import shutil
from datetime import datetime
from threading import Thread, Lock
from time import sleep
from flask import Flask, request, jsonify
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

app = Flask(__name__)
miners_lock = Lock()

# Load configuration
with open('config.json') as f:
    config = json.load(f)

# Initialize RPC connection
rpc = AuthServiceProxy(
    f"http://{config['rpc_user']}:{config['rpc_password']}@"
    f"{config['rpc_host']}:{config['rpc_port']}"
)

# Helper functions
def validate_bitcoin_address(address):
    pattern = r'^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}$'
    return re.match(pattern, address) is not None

def double_sha256(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def create_coinbase_tx(height, value, address):
    value_sat = int(value * 10**8)
    if address.startswith('bc1'):
        script_pubkey = bytes.fromhex(f"0014{hashlib.new('ripemd160', hashlib.sha256(bytes.fromhex(address)).digest()).hex()}")
    else:
        script_pubkey = bytes.fromhex(f"76a914{hashlib.new('ripemd160', hashlib.sha256(bytes.fromhex(address)).digest()).hex()}88ac")
    
    tx = struct.pack('<L', 1)
    tx += b'\x01'
    tx += b'\x00'*32
    tx += b'\xff'*4
    tx += struct.pack('<B', 4) + struct.pack('<L', height)
    tx += b'\xff'*4
    tx += b'\x01'
    tx += struct.pack('<Q', value_sat)
    tx += struct.pack('<B', len(script_pubkey))
    tx += script_pubkey
    tx += b'\x00'*4
    return tx.hex()

def calculate_merkle_root(tx_hashes):
    if not tx_hashes:
        return '0'*64
    hashes = [bytes.fromhex(h)[::-1] for h in tx_hashes]
    while len(hashes) > 1:
        if len(hashes) % 2 != 0:
            hashes.append(hashes[-1])
        hashes = [double_sha256(hashes[i] + hashes[i+1]) for i in range(0, len(hashes), 2)]
    return hashes[0][::-1].hex()

# Database functions with backup system
def load_miners():
    if not os.path.exists('miners.json'):
        return {}
    
    # Try to load from backup if main file is corrupted
    try:
        with open('miners.json') as f:
            return json.load(f)
    except:
        try:
            shutil.copy('miners.json.bak', 'miners.json')
            with open('miners.json') as f:
                return json.load(f)
        except:
            return {}

def save_miners(miners):
    with miners_lock:
        # Create backup first
        if os.path.exists('miners.json'):
            shutil.copy('miners.json', 'miners.json.bak')
        
        # Save new data
        with open('miners.json', 'w') as f:
            json.dump(miners, f, indent=2)

# Mining endpoints with password protection
@app.route('/getwork/<address>', methods=['GET'])
def get_work(address):
    password = request.args.get('password')
    if password != config['join_password']:
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    try:
        template = rpc.getblocktemplate({
            "rules": ["segwit"],
            "coinbasetxn": {"mineraddress": address}
        })
        
        coinbase_tx = create_coinbase_tx(
            template['height'],
            template['coinbasevalue'] / 10**8,
            address
        )
        
        tx_hashes = [coinbase_tx] + [tx['hash'] for tx in template['transactions']]
        merkle_root = calculate_merkle_root(tx_hashes)
        
        work = {
            'version': template['version'],
            'previousblockhash': template['previousblockhash'],
            'merkle_root': merkle_root,
            'time': template['curtime'],
            'bits': template['bits'],
            'height': template['height'],
            'target': int(template['target'], 16),
            'coinbase': coinbase_tx,
            'transactions': [tx['data'] for tx in template['transactions']]
        }
        
        return jsonify(work)
    except JSONRPCException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/submit/<address>', methods=['POST'])
def submit_share(address):
    password = request.json.get('password')
    if password != config['join_password']:
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    miners = load_miners()
    if address not in miners:
        miners[address] = {
            'shares': 0,
            'blocks': [],
            'immature_balance': 0.0,
            'paid': 0.0,
            'last_share': datetime.now().isoformat(),
            'first_share': datetime.now().isoformat()
        }
    
    data = request.json
    if not data or 'nonce' not in data:
        return jsonify({'error': 'Invalid submission'}), 400
    
    miners[address]['shares'] += 1
    miners[address]['last_share'] = datetime.now().isoformat()
    
    if miners[address]['shares'] % 1000000 == 0:
        block_reward = 6.25 * (1 - config['pool_fee'])
        miners[address]['blocks'].append({
            'height': data.get('height'),
            'hash': data.get('hash'),
            'value': block_reward,
            'status': 'immature',
            'timestamp': datetime.now().isoformat()
        })
        miners[address]['immature_balance'] += block_reward
        save_miners(miners)
        return jsonify({
            'result': 'Block found!',
            'reward': block_reward,
            'mature_in': config['confirmations_required']
        })
    
    save_miners(miners)
    return jsonify({'result': 'Share accepted'})

@app.route('/stats/<address>', methods=['GET'])
def miner_stats(address):
    password = request.args.get('password')
    if password != config['join_password']:
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    miners = load_miners()
    if address not in miners:
        return jsonify({'error': 'Miner not found'}), 404
    
    miner = miners[address]
    mature_balance = sum(
        block['value'] for block in miner['blocks']
        if block.get('status') == 'confirmed'
    )
    
    return jsonify({
        'address': address,
        'shares': miner['shares'],
        'blocks_found': len(miner['blocks']),
        'immature_balance': miner['immature_balance'],
        'mature_balance': mature_balance,
        'total_paid': miner['paid'],
        'last_share': miner['last_share'],
        'first_share': miner.get('first_share')
    })

# Background services
def payout_processor():
    while True:
        try:
            miners = load_miners()
            changed = False
            
            for address, miner in miners.items():
                for block in miner['blocks']:
                    if block['status'] == 'immature':
                        block_age = (datetime.now() - datetime.fromisoformat(block['timestamp'])).total_seconds()
                        if block_age > config['payout_interval']:
                            block['status'] = 'confirmed'
                            changed = True
                
                if miner['immature_balance'] >= config['min_payout']:
                    try:
                        txid = rpc.sendtoaddress(address, miner['immature_balance'])
                        miner['paid'] += miner['immature_balance']
                        miner['immature_balance'] = 0
                        changed = True
                        print(f"Paid {miner['immature_balance']} BTC to {address} (TXID: {txid})")
                    except JSONRPCException as e:
                        print(f"Payout failed for {address}: {e}")
            
            if changed:
                save_miners(miners)
        
        except Exception as e:
            print(f"Error in payout processor: {e}")
        
        sleep(config['payout_interval'])

def backup_service():
    while True:
        sleep(config['backup_interval'])
        try:
            miners = load_miners()
            save_miners(miners)  # This creates a backup automatically
        except Exception as e:
            print(f"Backup failed: {e}")

if __name__ == '__main__':
    # Initialize database
    if not os.path.exists('miners.json'):
        save_miners({})
    
    # Start background services
    Thread(target=payout_processor, daemon=True).start()
    Thread(target=backup_service, daemon=True).start()
    
    # Start pool server
    app.run(host='0.0.0.0', port=config['pool_port'])
