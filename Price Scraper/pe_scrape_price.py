# pe_scrape_price.py
import re
import time
import undetected_chromedriver as uc
from pe_utils import pricempire_url  # Assuming you have this already

DEBUG_MODE = False  # ← Enable detailed logging

def get_cs2_wear_order():
    return [
        "factory new", "minimal wear", "field-tested", "well-worn", "battle-scarred"
    ]

def parse_wear(skin):
    matches = re.findall(r'\(([^)]+)\)', skin)
    if matches:
        return matches[-1]
    return ""

def pick_price_from_variants(elements, want_stattrak, variant_name):
    for el in elements:
        label = el.text.lower().replace('\r', '').strip()
        try:
            price = el.find_element("css selector", "span.font-bold.text-theme-200").text.strip()
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] Could not find price in variant: {label}, error: {e}")
            continue

        if variant_name.lower() in label:
            if DEBUG_MODE:
                print(f"[DEBUG] Selected variant '{label}' → ${price}")
            return price

    if DEBUG_MODE:
        print(f"[DEBUG] No matching variant '{variant_name}' found. Returning empty price.")
    return ""

def get_pe_price_for_item(skin, driver=None):
    skin = skin.replace("&", "-")
    created_driver = False
    if driver is None:
        driver = uc.Chrome()
        created_driver = True

    try:
        want_stattrak = 'stattrak' in skin.lower()
        variant_name = parse_wear(skin)
        url = pricempire_url(skin)

        if DEBUG_MODE:
            print(f"[DEBUG] Loading URL: {url}")
            print(f"[DEBUG] Target wear: '{variant_name}' (StatTrak: {want_stattrak})")

        driver.get(url)
        time.sleep(1)

        elements = driver.find_elements("css selector", "a[role='listitem']")
        if DEBUG_MODE:
            print(f"[DEBUG] Found {len(elements)} variant entries.")

        price = pick_price_from_variants(elements, want_stattrak, variant_name)

        market_name = ""
        market_price = ""

        deal_links = driver.find_elements("css selector", "a[rel='nofollow noopener']")
        if DEBUG_MODE:
            print(f"[DEBUG] Found {len(deal_links)} market listings.")

        for link in deal_links:
            this_market_name = ""
            try:
                img = link.find_element("xpath", ".//preceding::img[1]")
                this_market_name = img.get_attribute("alt")
            except:
                pass

            this_market_price = ""
            try:
                price_span = link.find_element("xpath", ".//ancestor::div[contains(@class,'flex-col')][1]//span[contains(@class,'text-2xl')]")
                this_market_price = price_span.text.strip()
            except:
                pass

            if not this_market_price:
                try:
                    ancestor = link.find_element("xpath", ".//ancestor::div[contains(@class,'flex-col')][1]")
                    bolds = ancestor.find_elements("css selector", "span.font-bold")
                    for b in bolds:
                        t = b.text.strip()
                        if t.startswith("$") and len(t) > 1:
                            this_market_price = t
                            break
                except:
                    pass

            if this_market_price:
                market_name = this_market_name
                market_price = this_market_price
                break

        if DEBUG_MODE:
            print(f"[DEBUG] Final price: {price}, Market: {market_name}, Market price: {market_price}")

        return price, market_name, market_price

    except Exception as e:
        print(f"[ERROR] Exception scraping '{skin}': {e}")
        return "", "", ""

    finally:
        if created_driver:
            driver.quit()

# Optional CLI test
if __name__ == "__main__":
    import sys
    name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if name:
        print(get_pe_price_for_item(name))
