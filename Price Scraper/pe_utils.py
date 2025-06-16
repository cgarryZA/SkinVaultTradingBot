import re

def sanitize_for_url(text):
    text = text.lower()
    text = text.replace('★ ', '')
    text = text.replace('stattrak™', 'stattrak')
    text = text.replace(' | ', '-')
    text = text.replace(' ', '-')
    text = text.replace('&', 'and')
    text = text.replace('(', '').replace(')', '')
    text = re.sub(r'[^a-z0-9-]', '', text)
    while '--' in text:
        text = text.replace('--', '-')
    return text.strip('-')

def normalize_case_name(name):
    name = name.lower()
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

_CASE_CONTAINER_NAMES = set([
    normalize_case_name(x) for x in [
        "esports 2013 case", "esports 2013 winter case", "esports 2014 summer case",
        "csgo weapon case", "csgo weapon case 2", "csgo weapon case 3",
        "cs20 case", "horizon case", "danger zone case", "glove case",
        "revolver case", "gamma case", "gamma 2 case", "chroma case", "chroma 2 case",
        "chroma 3 case", "falchion case", "shadow case", "operation vanguard weapon case",
        "operation breakout weapon case", "operation phoenix weapon case", "operation hydra case",
        "operation bravo case", "operation wildfire case", "winter offensive weapon case",
        "huntsman weapon case", "breakout case", "spectrum case", "spectrum 2 case", "clutch case"
    ]
])

def is_case_or_container(skin):
    skin_norm = normalize_case_name(skin)
    if skin_norm.endswith(" case") or skin_norm.endswith(" weapon case") or skin_norm.endswith(" container") or " souvenir package" in skin_norm:
        return True
    return skin_norm in _CASE_CONTAINER_NAMES

def is_glove(skin):
    glove_types = [
        'hand wraps', 'moto gloves', 'specialist gloves', 'sport gloves', 'driver gloves',
        'hydra gloves', 'broken fang gloves', 'bloodhound gloves'
    ]
    lower = skin.lower()
    return any(gt in lower for gt in glove_types)

def flatten_skin_name(skin_name):
    m = re.match(r'^(.*)\s+\(([^()]*)\)\s*$', skin_name)
    if m:
        return sanitize_for_url(m.group(2))
    return sanitize_for_url(skin_name)

def pricempire_url(skin):
    skin = skin.strip()
    lower = skin.lower()

    # --- PINS ---
    parts = lower.split()
    if parts and parts[-1] == 'pin':
        slug = sanitize_for_url(skin)
        return f"https://pricempire.com/cs2-items/pin/{slug}"

    # --- GLOVES ---
    if is_glove(skin):
        name = skin.replace('★', '').replace('StatTrak™', '').replace('Souvenir', '').strip()
        m = re.match(r'([^\|]+)\s*\|\s*([^(]+(?:\([^)]+\))?)\s*\(([^)]+)\)', name)
        if m:
            weapon    = sanitize_for_url(m.group(1))
            skin_name = flatten_skin_name(m.group(2))
            wear      = sanitize_for_url(m.group(3))
            return f"https://pricempire.com/cs2-items/glove/{weapon}-{skin_name}/{wear}"
        else:
            return f"https://pricempire.com/cs2-items/glove/{sanitize_for_url(name)}"

    # --- CASES & CONTAINERS ---
    if is_case_or_container(skin):
        return f"https://pricempire.com/cs2-items/container/{sanitize_for_url(skin)}"

    # --- STICKERS ---
    if 'sticker' in lower:
        # tournament-sticker with finish
        m = re.match(r'Sticker\s*\|\s*([^(|]+)\s*\(([^)]+)\)\s*\|\s*([^\|]+)', skin, re.IGNORECASE)
        if m:
            team       = sanitize_for_url(m.group(1))
            finish     = sanitize_for_url(m.group(2))
            tournament = sanitize_for_url(m.group(3))
            return f"https://pricempire.com/cs2-items/tournament-sticker/sticker-{team}-{tournament}/{finish}"
        # tournament-sticker without finish
        m = re.match(r'Sticker\s*\|\s*([^\|]+)\|\s*([^\|]+)', skin, re.IGNORECASE)
        if m:
            team       = sanitize_for_url(m.group(1))
            tournament = sanitize_for_url(m.group(2))
            return f"https://pricempire.com/cs2-items/tournament-sticker/sticker-{team}-{tournament}"
        # plain sticker with subtype
        m = re.match(r'Sticker\s*\|\s*([^\(]+)\(([^)]+)\)', skin, re.IGNORECASE)
        if m:
            main = sanitize_for_url(m.group(1))
            sub  = sanitize_for_url(m.group(2))
            return f"https://pricempire.com/cs2-items/sticker/sticker-{main}/{sub}"
        # tournament-autograph sticker
        m = re.match(r'Sticker\s*\|\s*([^(|]+)\s*\(([^)]+)\)\s*\|\s*([^\|]+)', skin, re.IGNORECASE)
        if m:
            player     = sanitize_for_url(m.group(1))
            team       = sanitize_for_url(m.group(2))
            tournament = sanitize_for_url(m.group(3))
            return f"https://pricempire.com/cs2-items/tournament-autograph/sticker-{player}-{team}-{tournament}"
        # fallback
        return f"https://pricempire.com/cs2-items/sticker/{sanitize_for_url(skin)}"

    # --- STANDARD SKINS ---
    is_stattrak = 'stattrak' in lower
    is_souvenir = 'souvenir' in lower
    name = skin.replace('★', '').replace('StatTrak™', '').replace('Souvenir', '').strip()
    m = re.match(r'([^\|]+)\|\s*([^(]+(?:\([^)]+\))?)\s*\(([^)]+)\)', name)
    if m:
        weapon    = sanitize_for_url(m.group(1))
        skin_name = flatten_skin_name(m.group(2))
        wear      = sanitize_for_url(m.group(3))
        base      = f"https://pricempire.com/cs2-items/skin/{weapon}-{skin_name}"
        if is_stattrak:
            return f"{base}/stattrak-{wear}"
        elif is_souvenir:
            return f"{base}/souvenir-{wear}"
        else:
            return f"{base}/{wear}"
    else:
        return f"https://pricempire.com/cs2-items/skin/{sanitize_for_url(name)}"
