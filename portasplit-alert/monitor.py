import os
import json
import requests
from datetime import datetime
from geopy.distance import geodesic
from notifier import send_telegram_message

CONFIG_FILE = "config.json"
STATE_FILE = "search_state.json"
LOG_FILE = "checker_log.txt"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def write_to_log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

# --- DIREKTE HÄNDLER-APIS ---

def fetch_obi(coords, radius_km):
    """Fragt die offizielle OBI Verfügbarkeits-API ab."""
    art_num = "3932829"  # Midea PortaSplit 12000 BTU bei OBI
    url = f"https://www.obi.de/api/v1/products/{art_num}/availability"
    params = {"lat": coords[0], "lon": coords[1], "radius": radius_km, "storeCount": 20}
    headers = {"User-Agent": "Mozilla/5.0"}
    
    markets = []
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code == 200:
            for store in res.json().get("stores", []):
                stock = store.get("availability", {}).get("quantity", 0)
                if stock > 0:
                    markets.append({
                        "chain": "OBI", "name": store.get("name"),
                        "coords": [store.get("lat"), store.get("lon")],
                        "stock": int(stock), "price": 699.00,
                        "link": f"https://www.obi.de/p/{art_num}"
                    })
    except Exception as e: print(f"OBI Fehler: {e}")
    return markets

def fetch_bauhaus(coords, radius_km):
    """Fragt die Bauhaus Stock-Schnittstelle ab."""
    art_num = "31343753"  # ID für PortaSplit 12000 bei Bauhaus
    url = f"https://www.bauhaus.info/api/v1/products/{art_num}/stock"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    markets = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            # Bauhaus liefert oft alle Märkte, wir filtern nach Distanz in main()
            for store in res.json().get("publicStockEntries", []):
                stock = store.get("stockInfo", {}).get("quantity", 0)
                if stock > 0:
                    markets.append({
                        "chain": "Bauhaus", "name": store.get("storeName"),
                        "coords": [store.get("latitude"), store.get("longitude")],
                        "stock": int(stock), "price": 695.00,
                        "link": f"https://www.bauhaus.info/p/{art_num}"
                    })
    except Exception as e: print(f"Bauhaus Fehler: {e}")
    return markets

def fetch_hornbach(coords, radius_km):
    """Fragt die Hornbach Bestands-API ab."""
    art_num = "10675342"  # Hornbach Artikelnummer für PortaSplit 12k
    url = f"https://www.hornbach.de/cms/de/de/api/product/{art_num}/availability"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    markets = []
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            for store in res.json().get("storeAvailabilities", []):
                stock = store.get("lineDisplayAvailability", {}).get("availableQuantity", 0)
                if stock > 0:
                    markets.append({
                        "chain": "Hornbach", "name": store.get("storeName"),
                        "coords": [store.get("latitude"), store.get("longitude")],
                        "stock": int(stock), "price": 689.00,
                        "link": f"https://www.hornbach.de/p/{art_num}"
                    })
    except Exception as e: print(f"Hornbach Fehler: {e}")
    return markets

# --- MAIN ENGINE ---

def main():
    print("Starte Multistore-Direktabfrage...")
    config = load_config()
    old_state = load_state()
    new_state = {}
    
    home_coords = config["home_coords"]
    max_dist = config["max_distance_km"]
    
    # Alle Händler parallel/nacheinander direkt abfragen
    all_raw_data = []
    all_raw_data.extend(fetch_obi(home_coords, max_dist))
    all_raw_data.extend(fetch_bauhaus(home_coords, max_dist))
    all_raw_data.extend(fetch_hornbach(home_coords, max_dist))
    
    found_in_range = 0
    alerts_sent = 0
    
    for item in all_raw_data:
        distance = round(geodesic(home_coords, item["coords"]).km, 1)
        
        # Rigoroser Umkreis-Filter (100km um Frankfurt)
        if distance > max_dist:
            continue
            
        found_in_range += 1
        market_id = f"{item['chain']}_{item['name']}".lower().replace(" ", "_")
        
        is_fav = any(fav.lower() in item["name"].lower() for fav in config["prioritized_stores"])
        fav_prefix = "❤️ [PRIO-MARKT] " if is_fav else ""
        stock_text = "🟢 Letztes Stück!" if item["stock"] == 1 else f"🟢 {item['stock']} Stück abholbereit!"
        
        new_state[market_id] = {"stock": item["stock"], "price": item["price"]}
        
        # Smart Alert: Nur melden wenn neu oder Bestand/Preis sich geändert hat
        should_notify = (market_id not in old_state) or \
                        (old_state[market_id]["stock"] != item["stock"]) or \
                        (old_state[market_id]["price"] != item["price"])
                        
        if should_notify:
            msg = (
                f"🚨 {fav_prefix}PortaSplit 12k BTU direkt gefunden!\n\n"
                f"📍 *{item['chain']} ({item['name']})*\n"
                f"🛣️ Entfernung: {distance} km\n"
                f"💰 Preis: {item['price']} €\n"
                f"📦 Bestand: {stock_text}\n\n"
                f"🔗 Link: {item['link']}"
            )
            send_telegram_message(msg)
            alerts_sent += 1
            write_to_log(f"ALERT: {item['chain']} {item['name']} gemeldet (Bestand: {item['stock']}).")
            
    save_state(new_state)
    
    log_msg = f"Multistore-Check beendet. Märkte mit Bestand im Radius: {found_in_range}. Alarme gesendet: {alerts_sent}."
    write_to_log(log_msg)
    print("Check erfolgreich beendet.")

if __name__ == "__main__":
    main()
