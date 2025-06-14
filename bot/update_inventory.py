import csv
import os
import sys
import requests
import undetected_chromedriver as uc
from datetime import datetime, timedelta, timezone
from web3 import Web3
import argparse
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Ensure stdout is UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---- SUPPRESS CHROME __del__ ERRORS ----
uc.Chrome.__del__ = lambda self: None

# -------- CONFIG --------
INVENTORY_CSV    = 'Inventory.csv'
HISTORY_CSV      = 'InventoryHistory.csv'
CONTRACT_ADDRESS = '0xb730CFc309AD720E9184C9F8BDb0A10874587d1e'
CONTRACT_ABI     = [
    {"inputs":[{"internalType":"uint256","name":"skinsValue","type":"uint256"}],
     "name":"setValSkins","outputs":[],"stateMutability":"nonpayable","type":"function"}
]

ETH_RPC_URL      = os.getenv('ETH_RPC_URL')
PRIVATE_KEY      = os.getenv('PRIVATE_KEY')

# import scraper
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../Price Scraper')))
from pe_scrape_price import get_pe_price_for_item
from web3.exceptions import TimeExhausted

def get_eth_usd_price():
    try:
        r = requests.get(
            'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',
            timeout=10
        )
        return float(r.json()['ethereum']['usd'])
    except:
        print("[ERROR] Couldn't fetch ETH price, assuming $3500.")
        return 3500.0

def get_last_eth_value():
    if not os.path.exists(HISTORY_CSV):
        return None
    with open(HISTORY_CSV, encoding='utf-8') as f:
        lines = f.readlines()
    if len(lines) < 2:
        return None
    last = lines[-1].strip().split(',')
    try:
        return float(last[2])
    except:
        return None

def set_val_skins_onchain(total_eth):
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        print("[ERROR] Could not connect to Ethereum RPC.")
        return False

    acct = w3.eth.account.from_key(PRIVATE_KEY)
    contract = w3.eth.contract(
        address=w3.to_checksum_address(CONTRACT_ADDRESS),
        abi=CONTRACT_ABI
    )
    wei = w3.to_wei(total_eth, 'ether')
    tx = contract.functions.setValSkins(wei).build_transaction({
        'from': acct.address,
        'nonce': w3.eth.get_transaction_count(acct.address),
        'gas': 100000,
        'gasPrice': w3.eth.gas_price,
    })
    signed = acct.sign_transaction(tx)
    txh = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"[CONTRACT] tx sent: {txh.hex()}")

    try:
        # wait up to 120s (default); adjust poll_latency if needed
        receipt = w3.eth.wait_for_transaction_receipt(txh, timeout=120)
        print(f"[CONTRACT] Confirmed in block {receipt.blockNumber}")
        return True
    except TimeExhausted:
        print(f"[ERROR] Transaction {txh.hex()} not confirmed within timeout.")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error waiting for receipt: {e}")
        return False

def save_history(date, usd, eth, eth_price):
    existed = os.path.exists(HISTORY_CSV)
    with open(HISTORY_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not existed:
            writer.writerow(['Date','USD','ETH','ETH/USD'])
        writer.writerow([date, f"{usd:.2f}", f"{eth:.6f}", f"{eth_price:.2f}"])
    print(f"[HISTORY] {date} USD={usd:.2f}, ETH={eth:.6f}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true', help='Force update all items')
    args = parser.parse_args()
    force = args.force

    # Load inventory CSV
    if not os.path.exists(INVENTORY_CSV):
        print(f"[ERROR] {INVENTORY_CSV} not found.")
        sys.exit(1)
    with open(INVENTORY_CSV, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    fieldnames = rows[0].keys()

    # Scrape & update prices
    driver = uc.Chrome()
    total_usd   = 0.0
    now         = datetime.now(timezone.utc)
    updated_any = False

    for row in rows:
        skin     = row['Skin']
        qty      = int(row.get('QTY', 0))
        last_str = row.get('LastUpdated', '').strip().upper()

        # existing price
        try:
            price_exist = float(row.get('Price','').replace('$','').replace(',',''))
        except:
            price_exist = 0.0

        # skip NEVER entries
        if last_str == 'NEVER':
            total_usd += price_exist * qty
            print(f"[SKIP] '{skin}' set to NEVER.")
            continue

        # parse last updated date
        last_dt = None
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
            except:
                last_dt = None

        needs = force or not last_dt or (now - last_dt) > timedelta(days=1) or price_exist <= 0.0
        if not needs:
            total_usd += price_exist * qty
            continue

        # fetch new price
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        price_str, _, _ = get_pe_price_for_item(skin, driver)
        driver.close()
        driver.switch_to.window(driver.window_handles[0])

        if price_str:
            price = float(price_str.replace('$','').replace(',',''))
            row['Price']       = f"{price:.2f}"
            row['LastUpdated'] = now.isoformat()
            updated_any        = True
        else:
            price = price_exist

        total_usd += price * qty
        print(f"{skin}: {qty}×${price:.2f} = ${price*qty:.2f}")

    driver.quit()

    # Write updated inventory CSV
    with open(INVENTORY_CSV, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Compute totals
    eth_price = get_eth_usd_price()
    total_eth = total_usd / eth_price
    print(f"Total USD=${total_usd:.2f}, ETH={total_eth:.6f} (ETH/USD={eth_price:.2f})")

    # Load previous on-chain ETH snapshot
    last_eth = get_last_eth_value()

    # Save new snapshot
    save_history(now.isoformat(), total_usd, total_eth, eth_price)

    # DEBUG output
    print(f"[DEBUG] updated_any = {updated_any}")
    print(f"[DEBUG] last_eth    = {last_eth}")
    print(f"[DEBUG] total_eth   = {total_eth:.6f}")
    if last_eth is not None:
        pct_change = (total_eth - last_eth) / last_eth * 100
        print(f"[DEBUG] pct_change = {pct_change:.2f}% (threshold = 1.0%)")
    else:
        print("[DEBUG] No prior ETH value; will update on-chain if force=True")

    # Decide on-chain update
    if force or last_eth is None or abs(total_eth - last_eth)/ (last_eth or 1) >= 0.01:
        print("[DEBUG] Conditions met → calling setValSkins on-chain")
        set_val_skins_onchain(total_eth)
    else:
        print("[DEBUG] Conditions NOT met → skipping on-chain update")
