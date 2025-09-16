# Bitcoin Mining Pool Server

A modular Bitcoin mining pool server that supports both HTTP REST API and Stratum protocol.

Heavily modified fork of HugoXOX3's [PBpool](https://github.com/HugoXOX3/PBpool)


## ToDo

Since this is a wortk in progress here are some open ToDo's for the project:

_Any help in the form of PRs is always very welcome :)_

- [x] RPC integration for real block-templates and block submission
- [x] Share difficulty adjustments.
- [ ] Full and correct stratum implementation
- [ ] Persistant storage in different way than .json files

## Installation

1. Install dependencies (would recommend using pyenv or some similair tool):
```bash
pip install -r requirements.txt
```

2. Copy and configure the config file:
```bash
cp config.sample.json config.json
# Edit config.json with your settings
```

3. Run the pool server:
```bash
python main.py
```

## Features

- **Dual Protocol Support**: HTTP REST API and Stratum protocol
- **ASIC-Optimized**: Dynamic difficulty adjustment for ASIC miners
- **Bitcoin Core Integration**: Pool is able to run in a real bitcoin network.
- **Test Mode**: Can run without Bitcoin Core for testing
- **Automatic Payouts**: Background service for miner payouts (needs some more work)
- **Data Persistence**: JSON-based (for now) miner database with backups

## API Endpoints

### HTTP REST API
- `GET /getwork/<address>?password=<password>` - Get mining work
- `POST /submit/<address>` - Submit a share
- `GET /stats/<address>?password=<password>` - Get miner statistics

### Stratum Protocol
- Port: 3333 (configurable)
- Standardish Stratum mining protocol support (needs some more work)

## Configuration

Edit `config.json` to customize:
- Pool ports (HTTP and Stratum)
- Pool fee percentage
- Minimum payout threshold
- Bitcoin Core RPC settings
- Payout and backup intervals

## Running Modes

1. **Production Mode**: With Bitcoin Core connection for real mining
2. **Test Mode**: Without Bitcoin Core for development/testing

## Background Services

- **Payout Processor**: Automatically processes miner payouts
- **Backup Service**: Regularly backs up miner database

## Security

- Password-protected pool access
- Bitcoin address validation
- Ratelimiting-system through difficulty adjustment

## Project Structure

```
bitcoin-mining-pool/
│
├── main.py           # Main entry point
├── config.py         # Configuration management
├── utils.py          # Utility functions (hashing, validation)
├── models.py         # Data models and database operations
├── api.py            # Flask HTTP API routes
├── stratum.py        # Stratum protocol server
├── bitcoin_rpc.py    # Bitcoin Core RPC integration
├── services.py       # Background services (payouts, backups)
├── config.json       # Pool configuration (create from config.sample.json)
├── miners.json       # Miner database (auto-created)
└── requirements.txt  # Python dependencies
```