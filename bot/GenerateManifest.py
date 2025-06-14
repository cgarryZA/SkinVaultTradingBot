import csv
import os
import re
from collections import defaultdict

def extract_pool_name_and_weight(filename):
    # Matches something like "Liquid30.csv" -> ("Liquid", 30)
    m = re.match(r"(.+?)(\d+)\.csv$", filename)
    if m:
        return m.group(1), int(m.group(2))
    else:
        raise ValueError(f"Invalid manifest filename: {filename}")

def read_manifest(filepath):
    skins = {}
    with open(filepath, newline='', encoding='utf-8-sig') as csvfile:  # Use utf-8-sig
        reader = csv.DictReader(csvfile)
        for row in reader:
            skin = row['Skin']
            weight = float(row['Weighting'])
            skins[skin] = weight
    return skins

def combine_manifests(manifest_dir):
    # Scan directory for all pool manifests
    pool_files = [
        f for f in os.listdir(manifest_dir)
        if f.endswith('.csv') and f.lower() != 'combinedmanifest.csv'
    ]
    pool_specs = []
    for fname in pool_files:
        pool_name, pool_weight = extract_pool_name_and_weight(fname)
        pool_specs.append((fname, pool_name, pool_weight))

    total_pool_weight = sum(w for _, _, w in pool_specs)
    if total_pool_weight == 0:
        raise Exception("No pools or all pool weights are zero.")

    # Read all manifests
    pool_skins = {}
    for fname, pool_name, pool_weight in pool_specs:
        skins = read_manifest(os.path.join(manifest_dir, fname))
        pool_skins[pool_name] = {
            'weight': pool_weight,
            'skins': skins
        }

    # Collect all unique skins
    all_skins = set()
    for pool in pool_skins.values():
        all_skins.update(pool['skins'].keys())

    # Calculate per-skin global weighting
    combined = {}
    for skin in all_skins:
        total = 0
        for pool in pool_skins.values():
            pool_percent = pool['weight'] / total_pool_weight
            skin_weight = pool['skins'].get(skin, 0)
            pool_skin_sum = sum(pool['skins'].values()) or 1
            # Weighting for this skin in this pool, normalized to pool allocation
            total += pool_percent * (skin_weight / pool_skin_sum)
        combined[skin] = total

    return combined, pool_skins

def write_combined_manifest(combined, out_file):
    with open(out_file, 'w', newline='', encoding='utf-8') as f:  # Specify utf-8 here!
        writer = csv.writer(f)
        writer.writerow(['Skin', 'TotalWeighting'])
        for skin, weight in sorted(combined.items(), key=lambda x: -x[1]):
            writer.writerow([skin, weight])

# USAGE
manifest_dir = "./manifests"  # Directory containing all pool CSVs
combined, pools = combine_manifests(manifest_dir)
write_combined_manifest(combined, "./Manifests/CombinedManifest.csv")

print("Combined manifest written to CombinedManifest.csv")
