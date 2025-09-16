#!/usr/bin/env python3
"""
Bitcoin Mining Pool Server
Supports both HTTP REST API and Stratum protocol
"""

import json
import os
import hashlib
import struct
import re
import shutil
import socket
import time
from datetime import datetime
from threading import Thread, Lock
from time import sleep
from flask import Flask, request, jsonify

try:
    from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
    HAS_BITCOIN_RPC = True
except ImportError:
    print("Warning: bitcoinrpc not available, running in test mode")
    HAS_BITCOIN_RPC = False
    class JSONRPCException(Exception):
        pass

app = Flask(__name__)
miners_lock = Lock()

# Global variables
config = {}
rpc = None
stratum_server = None

def load_config():
    """Load configuration from config.json"""
    global config, rpc
    
    try:
        with open('config.json') as f:
            config = json.load(f)
        print("✅ Configuration loaded successfully")
    except FileNotFoundError:
        print("❌ config.json not found!")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config.json: {e}")
        return False
    
    # Initialize Bitcoin RPC connection
    if HAS_BITCOIN_RPC:
        try:
            rpc = AuthServiceProxy(
                f"http://{config['rpc_user']}:{config['rpc_password']}@"
                f"{config['rpc_host']}:{config['rpc_port']}"
            )
            # Test connection
            rpc.getblockchaininfo()
            print("✅ Bitcoin RPC connection established")
        except Exception as e:
            print(f"⚠️  Bitcoin RPC connection failed: {e}")
            print("   Running in test mode without Bitcoin Core")
            rpc = None
    else:
        rpc = None
    
    return True

def validate_bitcoin_address(address):
    """Validate both mainnet and testnet Bitcoin addresses"""
    pattern = r'^(bc1|tb1|[13mn2])[a-zA-HJ-NP-Z0-9]{25,62}$'
    return re.match(pattern, address) is not None

def double_sha256(data):
    """Double SHA256 hash"""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def create_coinbase_tx(height, value, address):
    """Create a coinbase transaction"""
    value_sat = int(value * 10**8)
    
    # Simple coinbase for testing
    tx = struct.pack('<L', 1)  # version
    tx += b'\x01'  # input count
    tx += b'\x00' * 32  # prev hash (null for coinbase)
    tx += b'\xff' * 4  # prev index (0xffffffff for coinbase)
    tx += struct.pack('<B', 4) + struct.pack('<L', height)  # script sig
    tx += b'\xff' * 4  # sequence
    tx += b'\x01'  # output count
    tx += struct.pack('<Q', value_sat)  # value
    tx += b'\x19'  # script length (25 bytes for P2PKH)
    tx += b'\x76\xa9\x14' + b'\x00' * 20 + b'\x88\xac'  # P2PKH script
    tx += b'\x00' * 4  # lock time
    
    return tx.hex()

# Database functions
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

# Flask HTTP API Routes
@app.route('/getwork/<address>', methods=['GET'])
def get_work(address):
    """Get work for HTTP mining clients"""
    password = request.args.get('password')
    if password != config.get('join_password'):
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    try:
        if rpc:
            template = rpc.getblocktemplate({
                "rules": ["segwit"],
                "coinbasetxn": {"mineraddress": address}
            })
            
            work = {
                'version': template['version'],
                'previousblockhash': template['previousblockhash'],
                'time': template['curtime'],
                'bits': template['bits'],
                'height': template['height'],
                'target': int(template['target'], 16),
                'coinbase': create_coinbase_tx(template['height'], template['coinbasevalue'] / 10**8, address),
                'transactions': [tx['data'] for tx in template['transactions']]
            }
        else:
            # Test work
            work = {
                'version': 536870912,
                'previousblockhash': '0' * 64,
                'time': int(time.time()),
                'bits': '207fffff',
                'height': 1,
                'target': 0x7fffff0000000000000000000000000000000000000000000000000000000000,
                'coinbase': create_coinbase_tx(1, 6.25, address),
                'transactions': []
            }
        
        return jsonify(work)
    except JSONRPCException as e:
        return jsonify({'error': str(e)}), 500

@app.route('/submit/<address>', methods=['POST'])
def submit_share(address):
    """Submit a share via HTTP"""
    data = request.get_json()
    if not data or data.get('password') != config.get('join_password'):
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    if 'nonce' not in data:
        return jsonify({'error': 'Missing nonce'}), 400
    
    # Process the share
    result = process_share(address, data.get('nonce'), data.get('height', 1))
    
    if result.get('block_found'):
        return jsonify({
            'result': 'Block found!',
            'reward': result['reward'],
            'mature_in': config.get('confirmations_required', 100)
        })
    else:
        return jsonify({'result': 'Share accepted'})

@app.route('/stats/<address>', methods=['GET'])
def miner_stats(address):
    """Get miner statistics"""
    password = request.args.get('password')
    if password != config.get('join_password'):
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
        'total_paid': miner.get('paid', 0.0),
        'last_share': miner['last_share'],
        'first_share': miner.get('first_share')
    })

def process_share(worker_address, nonce, height=1):
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
        block_reward = 3.125 * (1 - config.get('pool_fee', 0.02))
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
        print(f"🎉 BLOCK FOUND by {worker_address}! Reward: {block_reward} BTC")
    
    save_miners(miners)
    return {'block_found': block_found, 'reward': reward}

# Stratum Server Implementation
class StratumServer:
    def __init__(self, host='0.0.0.0', port=3333, config=None):
        self.host = host
        self.port = port
        self.config = config or {}
        self.clients = {}
        self.socket = None
        self.running = False
        self.target_share_time = 30  # Target 30 seconds per share
        
    def validate_and_submit_block(self, client_id, worker_name, job_id, extra_nonce2, ntime, nonce):
        """Validate if share is a block and submit it to Bitcoin network"""
        try:
            # Get the current block template to validate against
            template = self.get_block_template()
            
            if not template:
                print("❌ No template available for block validation")
                return False
            
            # Reconstruct the block header
            extranonce1 = f"{hash(client_id) & 0xffffffff:08x}"
            
            # Build coinbase transaction
            coinbase_tx = self.build_coinbase_tx(template, extranonce1, bytes.fromhex(extra_nonce2), worker_name)
            coinbase_hash = double_sha256(coinbase_tx)
            
            # Calculate merkle root
            merkle_root = coinbase_hash
            for tx in template.get('transactions', []):
                tx_hash = bytes.fromhex(tx['hash'])[::-1]  # Reverse for little-endian
                merkle_root = double_sha256(merkle_root + tx_hash)
            
            # Build block header
            header = struct.pack('<L', template['version'])  # version
            header += bytes.fromhex(template['previousblockhash'])[::-1]  # prev block hash (reversed)
            header += merkle_root[::-1]  # merkle root (reversed)
            header += struct.pack('<L', int(ntime, 16))  # timestamp
            header += bytes.fromhex(template['bits'])[::-1]  # bits (reversed) 
            header += struct.pack('<L', int(nonce, 16))  # nonce
            
            # Calculate block hash
            block_hash = double_sha256(header)
            block_hash_hex = block_hash[::-1].hex()  # Reverse for display
            
            # Check if this hash meets the NETWORK difficulty (not just pool difficulty)
            network_target = int(template.get('target', '0' * 64), 16)
            block_hash_int = int.from_bytes(block_hash, 'big')
            
            print(f"🔍 Checking block hash: {block_hash_hex[:32]}...")
            print(f"   Network target: {network_target:064x}")
            print(f"   Block hash int: {block_hash_int:064x}")
            
            if block_hash_int < network_target:
                print(f"🎯 VALID BLOCK FOUND! Hash meets network difficulty!")
                
                # Construct full block
                full_block = header  # Block header
                
                # Add transaction count (varint)
                tx_count = len(template.get('transactions', [])) + 1  # +1 for coinbase
                if tx_count < 0xfd:
                    full_block += struct.pack('<B', tx_count)
                elif tx_count < 0x10000:
                    full_block += b'\xfd' + struct.pack('<H', tx_count)
                else:
                    full_block += b'\xfe' + struct.pack('<L', tx_count)
                
                # Add coinbase transaction
                full_block += coinbase_tx
                
                # Add all other transactions
                for tx in template.get('transactions', []):
                    full_block += bytes.fromhex(tx['data'])
                
                # Submit block to network
                block_hex = full_block.hex()
                print(f"📤 Submitting block {block_hash_hex} to Bitcoin network...")
                print(f"   Block size: {len(full_block)} bytes")
                
                """Submit found block to Bitcoin network"""
                if not rpc:
                    print("⚠️  Would submit block to network (test mode)")
                    return True
                    
                try:
                    result = rpc.submitblock(block_hex)
                    if result is None:
                        print("🎉 BLOCK ACCEPTED BY NETWORK!")
                        return True
                    else:
                        print(f"❌ Block rejected: {result}")
                        return False
                except Exception as e:
                    print(f"❌ Block submission failed: {e}")
                    return False
            else:
                print(f"📊 Valid share but not a block (doesn't meet network difficulty)")
                return False
                
        except Exception as e:
            print(f"❌ Error validating block: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start(self):
        """Start the Stratum server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            
            print(f"✅ Stratum server listening on {self.host}:{self.port}")
            
            # Start job broadcaster
            job_thread = Thread(target=self.job_broadcaster, daemon=True)
            job_thread.start()
            
            while self.running:
                try:
                    client_socket, address = self.socket.accept()
                    print(f"📱 New Stratum client connected from {address}")
                    
                    client_thread = Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        print(f"❌ Error accepting Stratum connection: {e}")
                        
        except Exception as e:
            print(f"❌ Failed to start Stratum server: {e}")
    
    def handle_client(self, client_socket, address):
        """Handle individual client connections"""
        client_id = f"{address[0]}:{address[1]}"
        self.clients[client_id] = {
            'socket': client_socket,
            'address': address,
            'subscribed': False,
            'authorized': False,
            'worker': None,
            'difficulty': 10000.0,  # Higher starting difficulty for ASIC compatibility
            'share_times': [],
            'last_share_time': time.time()
        }
        
        try:
            buffer = b''
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    if line.strip():
                        try:
                            request = json.loads(line.decode('utf-8'))
                            print(f"📨 Stratum request from {client_id}: {request}")
                            response = self.handle_stratum_request(client_id, request)
                            
                            if response:
                                response_str = json.dumps(response) + '\n'
                                client_socket.send(response_str.encode('utf-8'))
                                print(f"📤 Stratum response to {client_id}: {response}")
                                
                        except json.JSONDecodeError as e:
                            print(f"❌ Invalid JSON from {client_id}: {line}")
                        except Exception as e:
                            print(f"❌ Error processing message from {client_id}: {e}")
        
        except Exception as e:
            print(f"🔌 Stratum client {client_id} disconnected: {e}")
        
        finally:
            if client_id in self.clients:
                del self.clients[client_id]
            try:
                client_socket.close()
            except:
                pass

    def handle_stratum_request(self, client_id, request):
        """Handle Stratum protocol requests"""
        method = request.get('method')
        params = request.get('params', [])
        req_id = request.get('id')
        
        if method == 'mining.subscribe':
            self.clients[client_id]['subscribed'] = True
            extranonce1 = f"{hash(client_id) & 0xffffffff:08x}"
            
            return {
                'id': req_id,
                'result': [
                    [
                        ["mining.set_difficulty", "subscription_id"],
                        ["mining.notify", "notification_id"]
                    ],
                    extranonce1,
                    4  # extra_nonce2_size
                ],
                'error': None
            }
        
        elif method == 'mining.authorize':
            if len(params) >= 2:
                worker_name = params[0]
                password = params[1]
                
                if password == self.config.get('join_password'):
                    self.clients[client_id]['authorized'] = True
                    self.clients[client_id]['worker'] = worker_name
                    
                    # Send authorization response immediately
                    auth_response = {
                        'id': req_id,
                        'result': True,
                        'error': None
                    }
                    
                    try:
                        response_str = json.dumps(auth_response) + '\n'
                        self.clients[client_id]['socket'].send(response_str.encode('utf-8'))
                        print(f"✅ Authorized {worker_name} from {client_id}")
                    except Exception as e:
                        print(f"Failed to send auth response: {e}")
                    
                    # Send initial difficulty and job
                    time.sleep(0.1)
                    self.send_difficulty(client_id, 10000.0)  # Higher for ASIC
                    self.send_job_to_client(client_id)
                    
                    return None  # Already sent response
                else:
                    return {
                        'id': req_id,
                        'result': False,
                        'error': [21, "Unauthorized worker", None]
                    }
        
        elif method == 'mining.submit':
            if len(params) >= 5 and self.clients[client_id]['authorized']:
                worker_name = params[0]
                job_id = params[1]
                extra_nonce2 = params[2]
                ntime = params[3]
                nonce = params[4]
                
                print(f"💎 Share submitted by {worker_name}: job={job_id}, nonce={nonce}")
                self.validate_and_submit_block(client_id, worker_name, job_id, extra_nonce2, ntime, nonce)
                
                # Process the share
                result = process_share(worker_name, nonce)
                self.adjust_client_difficulty(client_id)
                
                # Check if this might be a valid block (regtest has low difficulty)
                if rpc:
                    try:
                        # In regtest, shares might actually be blocks!
                        # TODO: Implement proper block validation and submission
                        template = self.get_block_template()
                        if template.get('height', 0) > 0:
                            print(f"📋 Regtest block template height: {template['height']}")
                            # For regtest, you might want to submit every valid share as a block
                    except Exception as e:
                        print(f"❌ Error checking block template: {e}")
                
                return {
                    'id': req_id,
                    'result': True,
                    'error': None
                }
            else:
                return {
                    'id': req_id,
                    'result': False,
                    'error': [23, "Unauthorized or invalid share", None]
                }
        
        else:
            return {
                'id': req_id,
                'result': None,
                'error': [20, "Method not found", None]
            }
    
    def get_block_template(self):
        """Get real block template from Bitcoin Core"""
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
            template = rpc.getblocktemplate({
                "rules": ["segwit"],
                "capabilities": ["coinbasetxn", "workid", "coinbase/append"]
            })
            print(f"📋 Got real block template for height {template['height']}")
            return template
        except Exception as e:
            print(f"❌ Failed to get block template: {e}")
            print("   Using fallback template")
            # Return dummy template on error
            return {
                'version': 536870912,
                'previousblockhash': '0' * 64,
                'transactions': [],
                'coinbasevalue': 625000000,
                'curtime': int(time.time()),
                'bits': '207fffff',
                'height': 1
            }
    
    def build_coinbase_tx(self, template, extranonce1, extranonce2, worker_address):
        """Build coinbase transaction with proper format"""
        height = template['height']
        coinbase_value = template['coinbasevalue']
        
        # Build height serialization (BIP 34)
        if height < 17:
            height_bytes = struct.pack('<B', height)
        elif height < 128:
            height_bytes = struct.pack('<BB', 1, height)
        elif height < 32768:
            height_bytes = struct.pack('<BH', 2, height)
        else:
            height_bytes = struct.pack('<BI', 4, height)
        
        # Coinbase input script: height + extranonce1 + extranonce2 + arbitrary data
        arbitrary_data = b'/stratum/'
        coinbase_script = height_bytes + extranonce1.encode() + extranonce2 + arbitrary_data
        
        # Build coinbase transaction
        coinbase_tx = struct.pack('<L', 1)  # version
        coinbase_tx += b'\x01'  # input count
        coinbase_tx += b'\x00' * 32  # prev hash (null)
        coinbase_tx += b'\xff' * 4  # prev index
        coinbase_tx += struct.pack('<B', len(coinbase_script)) + coinbase_script
        coinbase_tx += b'\xff' * 4  # sequence
        coinbase_tx += b'\x01'  # output count
        coinbase_tx += struct.pack('<Q', coinbase_value)  # output value
        
        # Output script (P2PKH to worker address - simplified)
        if worker_address.startswith(('bc1', 'tb1')):
            # Bech32 address - simplified P2WPKH
            script = b'\x19\x76\xa9\x14' + b'\x00' * 20 + b'\x88\xac'
        else:
            # Legacy P2PKH
            script = b'\x19\x76\xa9\x14' + b'\x00' * 20 + b'\x88\xac'
        
        coinbase_tx += struct.pack('<B', len(script)) + script
        coinbase_tx += b'\x00' * 4  # lock time
        
        return coinbase_tx
    
    def calculate_merkle_branch(self, transactions):
        """Calculate merkle branch for coinbase"""
        if not transactions:
            return []
        
        # Get transaction hashes
        tx_hashes = [bytes.fromhex(tx['hash'])[::-1] for tx in transactions]
        merkle_branch = []
        
        # Build merkle tree and extract branch
        level = tx_hashes[:]
        while len(level) > 1:
            if len(level) % 2:
                level.append(level[-1])
            
            merkle_branch.append(level[1].hex())  # Save right node for branch
            
            next_level = []
            for i in range(0, len(level), 2):
                combined = level[i] + level[i + 1]
                next_level.append(double_sha256(combined))
            level = next_level
        
        return merkle_branch[::-1]  # Reverse for proper order
    
    def adjust_client_difficulty(self, client_id):
        """Adjust difficulty based on share submission timing - ASIC optimized"""
        if client_id not in self.clients:
            return
            
        client = self.clients[client_id]
        current_time = time.time()
        
        # Calculate time since last share
        time_diff = current_time - client['last_share_time']
        client['share_times'].append(time_diff)
        client['last_share_time'] = current_time
        
        # Keep only last 5 share times
        if len(client['share_times']) > 5:
            client['share_times'] = client['share_times'][-5:]
        
        current_difficulty = client['difficulty']
        new_difficulty = current_difficulty
        
        # ASIC-optimized difficulty adjustment (much more aggressive)
        if time_diff < 1:  # Ultra fast (< 1 second) - likely ASIC
            multiplier = max(10.0, 30.0 / max(time_diff, 0.01))
            new_difficulty = current_difficulty * multiplier
            print(f"🚀 ULTRA FAST share ({time_diff:.2f}s)! ASIC detected - Increasing difficulty: {current_difficulty:.0f} → {new_difficulty:.0f}")
        elif time_diff < 5:  # Very fast (< 5 seconds)
            multiplier = max(5.0, 30.0 / max(time_diff, 0.1))
            new_difficulty = current_difficulty * multiplier
            print(f"⚡ VERY FAST share ({time_diff:.1f}s)! Increasing difficulty: {current_difficulty:.0f} → {new_difficulty:.0f}")
        elif time_diff < 15:  # Fast
            new_difficulty = current_difficulty * 2.0
            print(f"📈 Fast share ({time_diff:.1f}s)! Increasing difficulty: {current_difficulty:.0f} → {new_difficulty:.0f}")
        elif time_diff > 60:  # Slow
            new_difficulty = max(1000.0, current_difficulty * 0.7)  # Don't go below 1000 for ASIC
            print(f"📉 Slow share ({time_diff:.1f}s)! Decreasing difficulty: {current_difficulty:.0f} → {new_difficulty:.0f}")
        elif 15 <= time_diff <= 45:  # Good
            print(f"✅ Good timing ({time_diff:.1f}s)! Keeping difficulty {current_difficulty:.0f}")
        
        # Cap maximum difficulty to prevent overflow
        new_difficulty = min(new_difficulty, 100000000)  # 100M max
        
        client['difficulty'] = new_difficulty
        
        # Send new difficulty if changed significantly
        if abs(new_difficulty - current_difficulty) > current_difficulty * 0.05:
            self.send_difficulty(client_id, new_difficulty)
            time.sleep(0.1)
            self.send_job_to_client(client_id)
    
    def send_difficulty(self, client_id, difficulty):
        """Send difficulty to client"""
        message = {
            'id': None,
            'method': 'mining.set_difficulty',
            'params': [difficulty]
        }
        self.send_to_client(client_id, message)
    
    def send_to_client(self, client_id, message):
        """Send message to specific client"""
        if client_id in self.clients:
            try:
                message_str = json.dumps(message) + '\n'
                self.clients[client_id]['socket'].send(message_str.encode('utf-8'))
                return True
            except Exception as e:
                print(f"❌ Failed to send message to {client_id}: {e}")
                return False
        return False
    
    def get_block_template(self):
        """Get real block template from Bitcoin Core"""
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
            template = rpc.getblocktemplate({
                "rules": ["segwit"],
                "capabilities": ["coinbasetxn", "workid", "coinbase/append"]
            })
            print(f"📋 Got real block template for height {template['height']}")
            return template
        except Exception as e:
            print(f"❌ Failed to get block template: {e}")
            print("   Using fallback template")
            return self.get_block_template()  # Recursion with rpc=None fallback
    
    def send_job_to_client(self, client_id):
        """Send real Bitcoin mining job to specific client"""
        if client_id not in self.clients:
            return
            
        client = self.clients[client_id]
        difficulty = client['difficulty']
        worker_address = client.get('worker', 'tb1q8e8sddh2yx8j795k5up2tgchlgyj0z2mxuna67')  # fallback
        
        try:
            # Get real block template from Bitcoin Core
            template = self.get_block_template()
            
            # Use template's bits or override with client difficulty
            if rpc and 'bits' in template:
                nbits = template['bits']
            else:
                nbits = self.difficulty_to_bits(difficulty)
            
            # Build coinbase transaction parts
            extranonce1 = f"{hash(client_id) & 0xffffffff:08x}"
            extranonce2 = b'\x00' * 4  # Will be filled by miner
            
            # Build coinbase tx
            coinbase_tx = self.build_coinbase_tx(template, extranonce1, extranonce2, worker_address)
            coinbase_hex = coinbase_tx.hex()
            
            # Split coinbase into two parts (before and after extranonces)
            # This is a simplified split - for production you'd be more precise
            if len(coinbase_hex) > 90:
                coinb1 = coinbase_hex[:90]  # Everything before extranonce
                coinb2 = coinbase_hex[106:] if len(coinbase_hex) > 106 else ""
            else:
                # Fallback for short coinbase
                coinb1 = coinbase_hex
                coinb2 = ""
            
            # Calculate merkle branch
            merkle_branch = self.calculate_merkle_branch(template.get('transactions', []))
            
            job_id = f"job_{template.get('height', int(time.time()))}"
            
            job = {
                'id': None,
                'method': 'mining.notify',
                'params': [
                    job_id,
                    template.get('previousblockhash', '0' * 64),
                    coinb1,
                    coinb2,
                    merkle_branch,
                    f"{template.get('version', 536870912):08x}",
                    nbits,
                    f"{template.get('curtime', int(time.time())):08x}",
                    True  # clean_jobs
                ]
            }
            
            if rpc:
                print(f"📤 Sending REAL Bitcoin job to {client_id}:")
                print(f"   Height: {template.get('height')}")
                print(f"   Difficulty: {difficulty:.1f}")
                print(f"   Previous Hash: {template.get('previousblockhash', 'N/A')[:16]}...")
                print(f"   Transactions: {len(template.get('transactions', []))}")
            else:
                print(f"📤 Sending test job to {client_id} with difficulty {difficulty:.1f}")
            
            self.send_to_client(client_id, job)
            
        except Exception as e:
            print(f"❌ Error building job for {client_id}: {e}")
            # Send a simple fallback job
            job = {
                'id': None,
                'method': 'mining.notify', 
                'params': [
                    f"job_{int(time.time())}",
                    "0" * 64,
                    "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff4d04",
                    "ffffffff01405dc600000000001976a9140389035a9225b3839e2bbf32d826a2b28a5ad5f988ac00000000",
                    [],
                    "20000000", 
                    self.difficulty_to_bits(difficulty),
                    f"{int(time.time()):08x}",
                    True
                ]
            }
            print(f"📤 Sending fallback job to {client_id}")
            self.send_to_client(client_id, job)
    
    def job_broadcaster(self):
        """Broadcast real Bitcoin jobs every 30 seconds"""
        while self.running:
            time.sleep(30)
            try:
                authorized_clients = [
                    client_id for client_id, client_info in self.clients.items() 
                    if client_info.get('authorized', False)
                ]
                
                if authorized_clients:
                    if rpc:
                        print(f"📡 Broadcasting real Bitcoin jobs to {len(authorized_clients)} clients")
                    else:
                        print(f"📡 Broadcasting test jobs to {len(authorized_clients)} clients")
                    
                    for client_id in authorized_clients:
                        try:
                            self.send_job_to_client(client_id)
                        except Exception as e:
                            print(f"Failed to send job to {client_id}: {e}")
                        
            except Exception as e:
                print(f"Error broadcasting jobs: {e}")

def start_stratum_server(config):
    """Start Stratum server in background thread"""
    global stratum_server
    stratum_server = StratumServer(port=config.get('stratum_port', 3333), config=config)
    stratum_thread = Thread(target=stratum_server.start, daemon=True)
    stratum_thread.start()
    return stratum_server

def payout_processor():
    """Process payouts in background"""
    while True:
        try:
            miners = load_miners()
            changed = False
            
            for address, miner in miners.items():
                # Mark blocks as confirmed after time
                for block in miner['blocks']:
                    if block['status'] == 'immature':
                        block_age = (datetime.now() - datetime.fromisoformat(block['timestamp'])).total_seconds()
                        if block_age > config.get('payout_interval', 3600):
                            block['status'] = 'confirmed'
                            changed = True
                
                # Process payouts if minimum reached
                if miner['immature_balance'] >= config.get('min_payout', 0.001):
                    if rpc:
                        try:
                            txid = rpc.sendtoaddress(address, miner['immature_balance'])
                            miner['paid'] = miner.get('paid', 0.0) + miner['immature_balance']
                            miner['immature_balance'] = 0
                            changed = True
                            print(f"💰 Paid {miner['immature_balance']} BTC to {address} (TXID: {txid})")
                        except Exception as e:
                            print(f"❌ Payout failed for {address}: {e}")
                    else:
                        print(f"ℹ️  Would pay {miner['immature_balance']} BTC to {address} (test mode)")
            
            if changed:
                save_miners(miners)
        
        except Exception as e:
            print(f"❌ Error in payout processor: {e}")
        
        sleep(config.get('payout_interval', 3600))

def backup_service():
    """Backup service"""
    while True:
        sleep(config.get('backup_interval', 1800))
        try:
            miners = load_miners()
            save_miners(miners)
            print("💾 Backup completed")
        except Exception as e:
            print(f"❌ Backup failed: {e}")

def main():
    """Main function"""
    print("🚀 Starting Bitcoin Mining Pool Server...")
    
    # Load configuration
    if not load_config():
        print("❌ Failed to load configuration. Exiting.")
        return
    
    if rpc:
        print("✅ Real Bitcoin Core integration active!")
        print("   - Using live block templates")
        print("   - Real transaction data") 
        print("   - Network block submission")
    else:
        print("⚠️  Running in TEST MODE (no Bitcoin Core)")
        print("   - Using dummy block templates")
        print("   - For ASIC mining, Bitcoin Core is required!")
    
    # Initialize database
    if not os.path.exists('miners.json'):
        save_miners({})
        print("📊 Initialized miners database")
    
    # Start Stratum server
    start_stratum_server(config)
    
    # Start background services
    Thread(target=payout_processor, daemon=True).start()
    Thread(target=backup_service, daemon=True).start()
    
    print("✅ All services started successfully")
    print(f"📡 Stratum server: 0.0.0.0:{config.get('stratum_port', 3333)}")
    print(f"🌐 HTTP server: 0.0.0.0:{config.get('pool_port', 5000)}")
    print("🎯 Pool is ready for miners!")
    
    # Start Flask HTTP server (blocking)
    try:
        app.run(
            host='0.0.0.0', 
            port=config.get('pool_port', 5000),
            debug=False
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down pool server...")
        if stratum_server:
            stratum_server.running = False

if __name__ == '__main__':
    main()