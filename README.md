# **HCMLXOX Solo Mining Pool - Installation and Usage Guide**

## **📋 Table of Contents**
1. [Requirements](#-requirements)
2. [Installation](#-installation)
3. [Configuration](#-configuration)
4. [Running the Pool](#-running-the-pool)
5. [Connecting Miners](#-connecting-miners)
6. [Monitoring](#-monitoring)
7. [Troubleshooting](#-troubleshooting)

## **⚙️ Requirements**

### **System Requirements**
- Linux/Windows server (2GB RAM minimum)
- Python 3.8 or higher
- Bitcoin Core (fully synced)
- Root/administrator access (for Bitcoin Core configuration)

### **Python Packages**
The following packages will be automatically installed:

| Package | Purpose |
|---------|---------|
| `flask` | Web server for pool interface |
| `python-bitcoinrpc` | Bitcoin Core RPC communication |
| `requests` | HTTP client for API calls |
| `hashlib` | Cryptographic hashing (built-in) |

## **📥 Installation**

### **1. Clone the Repository**
```bash
git clone https://github.com/yourusername/hcmlxox-solo-pool.git
cd hcmlxox-solo-pool
```

### **2. Install Python Dependencies**
```bash
pip install -r requirements.txt
```

### **3. Set Up Bitcoin Core**
1. Edit your `bitcoin.conf` (usually found in `~/.bitcoin/bitcoin.conf`):
   ```ini
   server=1
   rpcuser=your_username
   rpcpassword=your_password
   rpcallowip=127.0.0.1
   txindex=1
   ```
   
2. Restart Bitcoin Core:
   ```bash
   bitcoind -daemon
   ```

## **⚙️ Configuration**

Edit `config.json` with your preferred settings:

```json
{
  "rpc_user": "your_username",
  "rpc_password": "your_password",
  "rpc_host": "127.0.0.1",
  "rpc_port": 8332,
  "pool_fee": 0.01,
  "min_payout": 0.001,
  "pool_port": 3333,
  "join_password": "Support_HCMLXOX",
  "difficulty": 1024,
  "confirmations_required": 100,
  "payout_interval": 3600,
  "backup_interval": 300
}
```

## **🚀 Running the Pool**

Start the mining pool server:
```bash
python solo_pool.py
```

The pool will start on port 3333 by default. For production use, consider running it as a service:

```bash
nohup python solo_pool.py > pool.log 2>&1 &
```

## **⛏️ Connecting Miners**

### **For ASIC Miners**
Configure your miner with these settings:
```
Pool URL: http://your-server-ip:3333/getwork/YOUR_BITCOIN_ADDRESS?password=Support_HCMLXOX
Worker: ANY_STRING
Password: x
```

### **Using the Example Python Miner**
Edit `miner_client.py`:
```python
POOL_URL = "http://your-server-ip:3333"
MINER_ADDRESS = "your_bitcoin_address_here"
POOL_PASSWORD = "Support_HCMLXOX"
```

Then run:
```bash
python miner_client.py
```

## **📊 Monitoring**

### **Check Pool Status**
```bash
curl http://localhost:3333/stats/YOUR_BITCOIN_ADDRESS?password=Support_HCMLXOX
```

### **View Logs**
```bash
tail -f pool.log
```

## **🔧 Troubleshooting**

### **Common Issues**

1. **Bitcoin Core not responding**
   - Verify Bitcoin Core is running: `bitcoin-cli getblockchaininfo`
   - Check RPC credentials in `bitcoin.conf`

2. **Connection refused errors**
   - Ensure firewall allows the pool port (default: 3333)
   - Check if the pool is running: `netstat -tulnp | grep 3333`

3. **Miner not submitting shares**
   - Verify password is correct
   - Check miner logs for error messages

### **Recovering from Crashes**
The pool automatically maintains backups of miner data in `miners.json.bak`. To restore:

```bash
cp miners.json.bak miners.json
```

## **📈 Performance Tips**

- For high hashrate setups, consider increasing the difficulty in `config.json`
- Run Bitcoin Core on a separate machine for better performance
- Use a reverse proxy (Nginx) if exposing the pool to the internet

## **🛡️ Security Recommendations**

1. Change the default password in `config.json`
2. Use HTTPS if exposing the pool publicly
3. Regularly backup the `miners.json` file
4. Monitor server resources (CPU/RAM usage)

## **📚 Additional Resources**

- [Bitcoin Core Documentation](https://bitcoincore.org/en/doc/)
- [Stratum Mining Protocol](https://en.bitcoin.it/wiki/Stratum_mining_protocol)
- [Python Flask Documentation](https://flask.palletsprojects.com/)


## ** Donations

If you find this project useful, consider supporting it with a Bitcoin donation:

**Bitcoin Address**: `bc1qt7a6vl28czf00vmuse9j7xwpyr7jjt83m2hljh`

[![Donate Bitcoin](https://img.shields.io/badge/Donate-Bitcoin-orange?logo=bitcoin)](bitcoin:bc1qt7a6vl28czf00vmuse9j7xwpyr7jjt83m2hljh)


**Happy Mining!** ⛏️💰
