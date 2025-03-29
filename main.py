import json
from flask import Flask, jsonify, request
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

app = Flask(__name__)

# Bitcoin RPC Configuration (MAINNET)
RPC_USER = "your_secure_username"
RPC_PASSWORD = "your_secure_password"
RPC_HOST = "127.0.0.1"
RPC_PORT = 8332  # Mainnet default RPC port

# Connect to Bitcoin Core
rpc = AuthServiceProxy(f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}")

# Mining pool settings
POOL_FEE = 0.01  # 1% fee
MIN_DIFFICULTY = 0x00000000FFFF0000000000000000000000000000000000000000000000000000  # Mainnet difficulty

# Track miners and shares
miners = {}
shares_submitted = 0
blocks_mined = 0

def get_block_template():
    """Get a new block template from Bitcoin Core (Mainnet)"""
    try:
        template = rpc.getblocktemplate({"rules": ["segwit"]})
        return {
            "version": template["version"],
            "prev_hash": template["previousblockhash"],
            "merkle_root": template["merkleroot"],
            "time": template["curtime"],
            "bits": template["bits"],
            "height": template["height"],
            "target": MIN_DIFFICULTY,
            "transactions": template["transactions"],
            "coinbase_value": template["coinbasevalue"] / 100000000,  # Convert to BTC
        }
    except JSONRPCException as e:
        print(f"RPC Error: {e}")
        return None

def validate_share(miner_address, nonce, extra_nonce):
    """Check if the share meets the pool's difficulty (simplified)"""
    # In reality, you must hash the block header and compare to target
    return True  # Accept all shares for testing

@app.route("/getwork", methods=["GET"])
def get_work():
    """Provide work to miners (Stratum-like)"""
    miner_address = request.args.get("address")
    if not miner_address:
        return jsonify({"error": "Miner address required"}), 400

    work = get_block_template()
    if not work:
        return jsonify({"error": "Failed to get block template"}), 500

    miners[miner_address] = {
        "work": work,
        "shares": 0,
        "balance": 0,
    }
    return jsonify(work)

@app.route("/submit", methods=["POST"])
def submit_share():
    """Handle submitted shares from miners"""
    data = request.json
    miner_address = data.get("address")
    nonce = data.get("nonce")
    extra_nonce = data.get("extra_nonce")

    if not all([miner_address, nonce, extra_nonce]):
        return jsonify({"error": "Missing data"}), 400

    if miner_address not in miners:
        return jsonify({"error": "Miner not registered"}), 403

    if not validate_share(miner_address, nonce, extra_nonce):
        return jsonify({"error": "Invalid share"}), 400

    miners[miner_address]["shares"] += 1
    miners[miner_address]["balance"] += (1 - POOL_FEE)  # Reward miner (minus fee)
    global shares_submitted
    shares_submitted += 1

    # Simulate a block found (1 in 1,000,000 shares for mainnet)
    if shares_submitted % 1000000 == 0:
        global blocks_mined
        blocks_mined += 1
        block_reward = miners[miner_address]["work"]["coinbase_value"]
        print(f"🎉 BLOCK FOUND! Reward: {block_reward} BTC")
        return jsonify({"result": "BLOCK FOUND!", "reward": block_reward})

    return jsonify({"result": "Share accepted"})

@app.route("/stats", methods=["GET"])
def stats():
    """Pool statistics"""
    return jsonify({
        "miners": len(miners),
        "shares": shares_submitted,
        "blocks": blocks_mined,
        "fee": POOL_FEE,
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
