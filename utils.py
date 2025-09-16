"""
Utility functions for the mining pool
"""

import re
import hashlib
import struct
import time


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


def difficulty_to_bits(difficulty):
    """Convert difficulty to bits representation"""
    # Simplified conversion for pool difficulty
    # This is not the same as network difficulty bits
    if difficulty < 1:
        difficulty = 1
    
    # Calculate target from difficulty
    max_target = 0x00000000ffff0000000000000000000000000000000000000000000000000000
    target = int(max_target / difficulty)
    
    # Convert to compact bits format
    # Find the most significant byte
    size = (target.bit_length() + 7) // 8
    if size <= 3:
        compact = target << (8 * (3 - size))
    else:
        compact = target >> (8 * (size - 3))
    
    # Ensure the high bit isn't set (would be negative)
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    
    # Combine size and compact target
    bits = (size << 24) | (compact & 0x00ffffff)
    
    return f"{bits:08x}"


def difficulty_to_bits(difficulty):
    """Convert difficulty to bits representation"""
    # Simplified conversion for pool difficulty
    # This is not the same as network difficulty bits
    if difficulty < 1:
        difficulty = 1
    
    # Calculate target from difficulty
    max_target = 0x00000000ffff0000000000000000000000000000000000000000000000000000
    target = int(max_target / difficulty)
    
    # Convert to compact bits format
    # Find the most significant byte
    size = (target.bit_length() + 7) // 8
    if size <= 3:
        compact = target << (8 * (3 - size))
    else:
        compact = target >> (8 * (size - 3))
    
    # Ensure the high bit isn't set (would be negative)
    if compact & 0x00800000:
        compact >>= 8
        size += 1
    
    # Combine size and compact target
    bits = (size << 24) | (compact & 0x00ffffff)
    
    return f"{bits:08x}"


def build_merkle_root(coinbase_hash, transactions):
    """Build merkle root from coinbase and transactions"""
    merkle_root = coinbase_hash
    for tx in transactions:
        tx_hash = bytes.fromhex(tx['hash'])[::-1]  # Reverse for little-endian
        merkle_root = double_sha256(merkle_root + tx_hash)
    return merkle_root