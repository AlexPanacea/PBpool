"""
Background services for the mining pool
"""

from datetime import datetime
from time import sleep

from config import get_config
from models import load_miners, save_miners
from bitcoin_rpc import send_to_address


def payout_processor():
    """Process payouts in background"""
    while True:
        config = get_config()
        
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
                    try:
                        txid = send_to_address(address, miner['immature_balance'])
                        print(f"Paid {miner['immature_balance']} BTC to {address} (TXID: {txid})")
                        miner['paid'] = miner.get('paid', 0.0) + miner['immature_balance']
                        miner['immature_balance'] = 0
                        changed = True
                    except Exception as e:
                        print(f"Payout failed for {address}: {e}")
            
            if changed:
                save_miners(miners)
        
        except Exception as e:
            print(f"Error in payout processor: {e}")
        
        sleep(config.get('payout_interval', 3600))


def backup_service():
    """Backup service"""
    config = get_config()
    
    while True:
        sleep(config.get('backup_interval', 1800))
        try:
            miners = load_miners()
            save_miners(miners)
            print("Backup completed")
        except Exception as e:
            print(f"Backup failed: {e}")