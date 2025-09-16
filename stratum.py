"""
Stratum Protocol Server Implementation
"""

import socket
import json
import struct
import time
from threading import Thread
import traceback

from utils import double_sha256, difficulty_to_bits, build_merkle_root
from models import process_share
from bitcoin_rpc import get_block_template, submit_block


class StratumServer:
    def __init__(self, host='0.0.0.0', port=3333, config=None):
        self.host = host
        self.port = port
        self.config = config or {}
        self.clients = {}
        self.socket = None
        self.running = False
        self.target_share_time = 30  # Target 30 seconds per share
        
    def start(self):
        """Start the Stratum server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            
            print(f"Stratum server listening on {self.host}:{self.port}")
            
            # Start job broadcaster
            job_thread = Thread(target=self.job_broadcaster, daemon=True)
            job_thread.start()
            
            while self.running:
                try:
                    client_socket, address = self.socket.accept()
                    print(f"New Stratum client connected from {address}")
                    
                    client_thread = Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except Exception as e:
                    if self.running:
                        print(f"Error accepting Stratum connection: {e}")
                        
        except Exception as e:
            print(f"Failed to start Stratum server: {e}")
    
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
                            print(f"Stratum request from {client_id}: {request}")
                            response = self.handle_stratum_request(client_id, request)
                            
                            if response:
                                response_str = json.dumps(response) + '\n'
                                client_socket.send(response_str.encode('utf-8'))
                                print(f"Stratum response to {client_id}: {response}")
                                
                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON from {client_id}: {line}")
                        except Exception as e:
                            print(f"Error processing message from {client_id}: {e}")
        
        except Exception as e:
            print(f"Stratum client {client_id} disconnected: {e}")
        
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
                        print(f"Authorized {worker_name} from {client_id}")
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
                
                print(f"Share submitted by {worker_name}: job={job_id}, nonce={nonce}")
                self.validate_and_submit_block(client_id, worker_name, job_id, extra_nonce2, ntime, nonce)
                
                # Process the share
                result = process_share(worker_name, nonce)
                self.adjust_client_difficulty(client_id)
                
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
    
    def validate_and_submit_block(self, client_id, worker_name, job_id, extra_nonce2, ntime, nonce):
        """Validate if share is a block and submit it to Bitcoin network"""
        try:
            # Get the current block template to validate against
            template = get_block_template()
            
            if not template:
                print("No template available for block validation")
                return False
            
            # Reconstruct the block header
            extranonce1 = f"{hash(client_id) & 0xffffffff:08x}"
            
            # Build coinbase transaction
            coinbase_tx = self.build_coinbase_tx(template, extranonce1, bytes.fromhex(extra_nonce2), worker_name)
            coinbase_hash = double_sha256(coinbase_tx)
            
            # Calculate merkle root
            merkle_root = build_merkle_root(coinbase_hash, template.get('transactions', []))
            
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
            
            print(f"Checking block hash: {block_hash_hex[:32]}...")
            print(f"   Network target: {network_target:064x}")
            print(f"   Block hash int: {block_hash_int:064x}")
            
            if block_hash_int < network_target:
                print(f"VALID BLOCK FOUND! Hash meets network difficulty!")
                
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
                print(f"Submitting block {block_hash_hex} to Bitcoin network...")
                print(f"   Block size: {len(full_block)} bytes")
                
                return submit_block(block_hex)
            else:
                print(f"Valid share but not a block (doesn't meet network difficulty)")
                return False
                
        except Exception as e:
            print(f"Error validating block: {e}")
            traceback.print_exc()
            return False
    
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
            print(f"ULTRA FAST share ({time_diff:.2f}s)! ASIC detected - Increasing difficulty: {current_difficulty:.0f} -> {new_difficulty:.0f}")
        elif time_diff < 5:  # Very fast (< 5 seconds)
            multiplier = max(5.0, 30.0 / max(time_diff, 0.1))
            new_difficulty = current_difficulty * multiplier
            print(f"VERY FAST share ({time_diff:.1f}s)! Increasing difficulty: {current_difficulty:.0f} -> {new_difficulty:.0f}")
        elif time_diff < 15:  # Fast
            new_difficulty = current_difficulty * 2.0
            print(f"Fast share ({time_diff:.1f}s)! Increasing difficulty: {current_difficulty:.0f} -> {new_difficulty:.0f}")
        elif time_diff > 60:  # Slow
            new_difficulty = max(1000.0, current_difficulty * 0.7)  # Don't go below 1000 for ASIC
            print(f"Slow share ({time_diff:.1f}s)! Decreasing difficulty: {current_difficulty:.0f} -> {new_difficulty:.0f}")
        elif 15 <= time_diff <= 45:  # Good
            print(f"Good timing ({time_diff:.1f}s)! Keeping difficulty {current_difficulty:.0f}")
        
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
                print(f"Failed to send message to {client_id}: {e}")
                return False
        return False
    
    def send_job_to_client(self, client_id):
        """Send real Bitcoin mining job to specific client"""
        if client_id not in self.clients:
            return
            
        client = self.clients[client_id]
        difficulty = client['difficulty']
        worker_address = client.get('worker', 'tb1q8e8sddh2yx8j795k5up2tgchlgyj0z2mxuna67')  # fallback
        
        try:
            # Get real block template (simplified call for regtest)
            template = get_block_template()
            
            # Use template's bits or override with client difficulty
            nbits = template.get('bits', difficulty_to_bits(difficulty))
            
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
            
            print(f"Sending job to {client_id}:")
            print(f"   Height: {template.get('height')}")
            print(f"   Difficulty: {difficulty:.1f}")
            print(f"   Previous Hash: {template.get('previousblockhash', 'N/A')[:16]}...")
            print(f"   Transactions: {len(template.get('transactions', []))}")
            
            self.send_to_client(client_id, job)
            
        except Exception as e:
            print(f"Error building job for {client_id}: {e}")
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
                    difficulty_to_bits(difficulty),
                    f"{int(time.time()):08x}",
                    True
                ]
            }
            print(f"Sending fallback job to {client_id}")
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
                    print(f"Broadcasting jobs to {len(authorized_clients)} clients")
                    
                    for client_id in authorized_clients:
                        try:
                            self.send_job_to_client(client_id)
                        except Exception as e:
                            print(f"Failed to send job to {client_id}: {e}")
                        
            except Exception as e:
                print(f"Error broadcasting jobs: {e}")