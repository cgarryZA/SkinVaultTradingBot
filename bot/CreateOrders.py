import csv
import os
import sys

# -------- CONFIG --------
MANIFEST_CSV = './Manifests/CombinedManifest.csv'
INVENTORY_CSV = 'Inventory.csv'
OUTPUT_CSV = 'OrderLog.csv'

# load manifest
manifest = {}
with open(MANIFEST_CSV, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        manifest[row['Skin']] = float(row['TotalWeighting'])

# load inventory
inventory = {}
try:
    with open(INVENTORY_CSV, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            inventory[row['Skin']] = int(row['QTY'])
except FileNotFoundError:
    print(f"{INVENTORY_CSV} not found, assuming empty inventory.")

# build orders
orders = []

# First, any SKUs in inventory but not in manifest → SELL all
for skin, qty in inventory.items():
    if skin not in manifest and qty > 0:
        orders.append([skin, qty, 0, -qty, 'SELL'])

# Next, iterate manifest SKUs
for skin, weight in manifest.items():
    current = inventory.get(skin, 0)
    target = 1  # or your proportional target
    diff = target - current
    if diff < 0:
        orders.append([skin, current, target, diff, 'SELL'])
    elif diff > 0:
        orders.append([skin, current, target, diff, 'BUY'])
    # if diff == 0 → skip

# group sells first, then buys
sells = [o for o in orders if o[4] == 'SELL']
buys  = [o for o in orders if o[4] == 'BUY']
ordered = sells + buys

# write out
with open(OUTPUT_CSV, 'w', encoding='utf-8', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Skin', 'Current', 'Target', 'Diff', 'Action'])
    for row in ordered:
        writer.writerow(row)

print(f"Output written to {OUTPUT_CSV}")
