# PythonBitcoinMiningPool

*A fully functional Bitcoin mining pool that connects to Bitcoin Core (mainnet) and integrates with the [PythonBitcoinMiner](https://github.com/HugoXOX3/PythonBitcoinMiner).*  

---

## **🚀 Features**
- **Bitcoin Mainnet Support** (Real BTC mining)  
- **RPC Integration** (Works with Bitcoin Core)  
- **Simulated & Real Mining** (Supports [PythonBitcoinMiner](https://github.com/HugoXOX3/PythonBitcoinMiner))  
- **Pool Statistics & Fee System**  

---

## **📥 Installation**
### **1. Prerequisites**
- **Bitcoin Core** ([Download](https://bitcoincore.org/en/download/))  
- **Python 3.8+** ([Download](https://www.python.org/downloads/))  

### **2. Configure Bitcoin Core**
Edit `bitcoin.conf` (located in Bitcoin's data directory):  
- **Linux/macOS**: `~/.bitcoin/bitcoin.conf`  
- **Windows**: `C:\Users\<YourUsername>\AppData\Roaming\Bitcoin\bitcoin.conf`  

Add these settings:
```ini
server=1
rpcuser=your_secure_username  # Change this!
rpcpassword=your_secure_password  # Change this!
rpcallowip=127.0.0.1
txindex=1  # Required for getblocktemplate
```

### **3. Start Bitcoin Core**
```sh
bitcoind -daemon
```
Wait for full sync (check progress with `bitcoin-cli getblockchaininfo`).  

### **4. Install Required Python Packages**
```sh
pip install python-bitcoinrpc flask requests
```

### **5. Clone This Repository**
```sh
git clone https://github.com/yourusername/bitcoin-mining-pool.git
cd bitcoin-mining-pool
```

---

## **🛠️ Usage**
### **1. Run the Mining Pool Server**
```sh
python mainnet_pool.py
```
- The pool runs on `http://127.0.0.1:5000`.  

### **2. Connect Miners**
SHA256 Miner ([PythonBitcoinMiner](https://github.com/HugoXOX3/PythonBitcoinMiner))**
1. **Install the miner**:
   ```sh
   git clone https://github.com/HugoXOX3/PythonBitcoinMiner.git
   cd PythonBitcoinMiner
   ```
2. **Configure it to connect to your pool**:
   Edit `miner.py` and replace the pool URL with:
   ```python
   POOL_URL = "http://127.0.0.1:5000" #or replace the 127.0.0.1 into the ip of you mining pool device
   ```
3. **Run the miner**:
   ```sh
   python miner.py
   ```

---

## **📊 Pool Statistics**
- Check mining stats at:  
  ```sh
  curl http://127.0.0.1:5000/stats #or replace the 127.0.0.1 into the ip of you mining pool device
  ```
- Example output:
  ```json
  {
    "miners": 5,
    "shares": 1243,
    "blocks": 0,
    "fee": 0.01
  }
  ```

---

## **🔧 Customization**
- **Change Pool Fee**: Edit `POOL_FEE` in `mainnet_pool.py`.  
- **Adjust Difficulty**: Modify `MIN_DIFFICULTY` in `mainnet_pool.py`.  
- **Stratum Protocol**: Replace HTTP with Stratum for better performance.  

---

## **⚠️ Warnings**
- **Do not use in production** without proper security hardening.  
- **Mining on mainnet requires ASICs** (this code simulates mining for testing).  
- **You are responsible for any losses** if used incorrectly.  

---

## **📜 License**
MIT License.  

---

## **🚀 Next Steps**
- [ ] **Implement Stratum Protocol**  
- [ ] **Add Real ASIC Support**  
- [ ] **Automatic Payout System**  

---

**🎉 Happy Mining!**  
*For questions, open an issue or contact the developer.*
