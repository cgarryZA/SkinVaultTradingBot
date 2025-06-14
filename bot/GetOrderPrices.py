import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import undetected_chromedriver as uc
import threading

# ---- PATCH OUT BAD DESTRUCTOR LOGGING ----
uc.Chrome.__del__ = lambda self: None

# Add the Price Scraper folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../Price Scraper')))
from pe_scrape_price import get_pe_price_for_item

# ---- CONFIG ----
INFILE = "OrderLog.csv"
OUTFILE = "BuyOrders.csv"
MAX_WORKERS = 6

# lock to serialize Chrome unpack/install
driver_lock = threading.Lock()

def fetch_price(row):
    skin = row['Skin']
    with driver_lock:
        driver = uc.Chrome()
    try:
        price_usd, market_name, market_price = get_pe_price_for_item(skin, driver)
    except Exception as e:
        print(f"[ERROR] {skin}: {e}")
        price_usd, market_name, market_price = "", "", ""
    finally:
        try: driver.quit()
        except: pass

    row['PriceUSD'] = price_usd
    row['RecommendedMarket'] = market_name
    row['RecommendedMarketPrice'] = market_price
    return row

def main():
    if not os.path.exists(INFILE):
        print(f"[ERROR] {INFILE} not found.")
        sys.exit(1)

    # only BUY orders
    with open(INFILE, encoding="utf-8") as f:
        buy_rows = [r for r in csv.DictReader(f) if r.get('Action','').upper()=='BUY']

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = { ex.submit(fetch_price, row): row for row in buy_rows }
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            print(f"[DONE] {r['Skin']} → {r['RecommendedMarketPrice']} via {r['RecommendedMarket']}")

    # sort cheapest → most expensive, by RecommendedMarketPrice
    def price_key(r):
        try:
            s = r.get('RecommendedMarketPrice','')
            return float(s.replace('$','').replace(',',''))
        except:
            return float('inf')

    results.sort(key=price_key)

    # write out
    fieldnames = ['Skin','Diff','Action','PriceUSD','RecommendedMarket','RecommendedMarketPrice']
    with open(OUTFILE,'w',encoding='utf-8',newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow({
                'Skin': r['Skin'],
                'Diff': r.get('Diff',''),
                'Action': r.get('Action',''),
                'PriceUSD': r.get('PriceUSD',''),
                'RecommendedMarket': r.get('RecommendedMarket',''),
                'RecommendedMarketPrice': r.get('RecommendedMarketPrice',''),
            })

    print(f"\nWrote {len(results)} buy orders sorted by market price (cheapest→expensive) to {OUTFILE}")

if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, help='Max parallel threads')
    args = parser.parse_args()
    MAX_WORKERS = args.workers
    main()
