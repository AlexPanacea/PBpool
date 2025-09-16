"""
Flask HTTP API Routes for the mining pool
"""

import time
from flask import Flask, request, jsonify

from config import get_config, get_rpc
from utils import validate_bitcoin_address, create_coinbase_tx
from models import process_share, get_miner_stats
from bitcoin_rpc import get_block_template

app = Flask(__name__)


@app.route('/getwork/<address>', methods=['GET'])
def get_work(address):
    """Get work for HTTP mining clients"""
    config = get_config()
    password = request.args.get('password')
    
    if password != config.get('join_password'):
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    try:
        rpc = get_rpc()
        if rpc:
            template = get_block_template(address)
            
            work = {
                'version': template['version'],
                'previousblockhash': template['previousblockhash'],
                'time': template['curtime'],
                'bits': template['bits'],
                'height': template['height'],
                'target': int(template['target'], 16),
                'coinbase': create_coinbase_tx(
                    template['height'], 
                    template['coinbasevalue'] / 10**8, 
                    address
                ),
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
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/submit/<address>', methods=['POST'])
def submit_share(address):
    """Submit a share via HTTP"""
    config = get_config()
    data = request.get_json()
    
    if not data or data.get('password') != config.get('join_password'):
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    if 'nonce' not in data:
        return jsonify({'error': 'Missing nonce'}), 400
    
    # Process the share
    result = process_share(
        address, 
        data.get('nonce'), 
        data.get('height', 1),
        config.get('pool_fee', 0.02)
    )
    
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
    config = get_config()
    password = request.args.get('password')
    
    if password != config.get('join_password'):
        return jsonify({'error': 'Invalid password'}), 401
    
    if not validate_bitcoin_address(address):
        return jsonify({'error': 'Invalid Bitcoin address'}), 400
    
    stats = get_miner_stats(address)
    if not stats:
        return jsonify({'error': 'Miner not found'}), 404
    
    return jsonify(stats)