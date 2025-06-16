#!/usr/bin/env python3
import os
import csv
from datetime import datetime, timezone
import requests
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configuration
ETH_RPC_URL         = os.getenv('ETH_RPC_URL')
SKINDEX_ADDRESS     = os.getenv('SKINDEX_CONTRACT_ADDRESS')
OUTPUT_CSV          = 'skindex_price_history.csv'

# Minimal ABI for getNavPerToken()
SKINDEX_ABI = [
    {
        "inputs": [],
        "name": "getNavPerToken",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

def fetch_eth_price():
    """Fetch current ETH price in USD from CoinGecko."""
    url = 'https://api.coingecko.com/api/v3/simple/price'
    params = {'ids': 'ethereum', 'vs_currencies': 'usd'}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return float(data['ethereum']['usd'])

def fetch_skindex_nav_per_token(w3, contract):
    """Call getNavPerToken() and convert from 18-decimal uint to float ETH price."""
    raw = contract.functions.getNavPerToken().call()
    return raw / 1e18

def ensure_csv_header(path):
    """Create CSV file with header if it doesn't exist."""
    if not os.path.exists(path):
        with open(path, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Price in USD', 'Price in ETH', 'ETH/USD'])

def append_price_snapshot(path, timestamp, price_usd, price_eth, eth_usd):
    """Append one row of price data to CSV."""
    with open(path, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp,
            f"{price_usd:.2f}",
            f"{price_eth:.6f}",
            f"{eth_usd:.2f}"
        ])

def main():
    # Validate environment
    if not ETH_RPC_URL:
        print("[ERROR] ETH_RPC_URL not set in .env")
        return
    if not SKINDEX_ADDRESS:
        print("[ERROR] SKINDEX_CONTRACT_ADDRESS not set in .env")
        return

    # Initialize Web3 & contract
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        print("[ERROR] Could not connect to Ethereum RPC at", ETH_RPC_URL)
        return

    contract = w3.eth.contract(address=w3.to_checksum_address(SKINDEX_ADDRESS), abi=SKINDEX_ABI)

    # Fetch prices
    try:
        eth_usd = fetch_eth_price()
    except Exception as e:
        print("[ERROR] Failed to fetch ETH price:", e)
        return

    try:
        price_eth = fetch_skindex_nav_per_token(w3, contract)
    except Exception as e:
        print("[ERROR] Failed to fetch SKINDEX NAV per token:", e)
        return

    price_usd = price_eth * eth_usd
    timestamp = datetime.now(timezone.utc).isoformat()

    # Write to CSV
    ensure_csv_header(OUTPUT_CSV)
    append_price_snapshot(OUTPUT_CSV, timestamp, price_usd, price_eth, eth_usd)
    print(f"[{timestamp}] SKINDEX = {price_usd:.2f} USD | {price_eth:.6f} ETH (ETH/USD = {eth_usd:.2f})")

if __name__ == '__main__':
    main()
