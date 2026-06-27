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

def fetch_obi_direct(coords, radius_km):
    """Fragt die OBI-Schnittstelle direkt nach der PortaSplit 12000 im Umkreis ab."""
    # OBI Artikelnummer für die Midea PortaSplit 12000 BTU
    art_num = "3932829" 
    lat, lon = coords[0], coords[1]
    
    # Offizielle OBI-Schnittstelle für Marktverfügbarkeiten
    url = f"https://www.obi.de/api/v1/products/{art_num}/availability"
    params = {
        "lat": lat,
        "lon": lon,
        "radius": radius_km,
        "storeCount": 15
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            markets = []
            
            # Auswertung der lokalen Märkte im Radius
            for store in data.get("stores", []):
                availability = store.get("availability", {})
                stock = availability.get("quantity", 0)
                
                # Nur Märkte mit echtem Bestand listen
                if stock > 0:
                    markets.append({
                        "store_chain": "OBI",
                        "branch_name": store.get("name", "Unbekannter Markt"),
                        "coords": [store.get("lat"), store.get("lon")],
                        "product": "Midea PortaSplit 12000 BTU",
                        "price": 699.00,  # OBI Standardpreis
                        "stock": int(stock),
                        "shipping_available": False,
                        "link": f"https://www.obi.de/p/{art_num}"
                    })
            return markets
    except Exception as e:
        print(f"Fehler beim direkten OBI-Abruf: {e}")
    return []

def main():
    print("Starte direkte OBI-Live-Abfrage...")
    config = load_config()
    old_state = load_state()
    new_state = {}
    
    home_coords = config["home_coords"]
    max_dist = config["max_distance_km"]
    
    # Holt die Daten ohne den fehlerhaften Umweg direkt von OBI
    all_markets_data = fetch_obi_direct(home_coords, max_dist)
    
    found_any_in_range = len(all_markets_data)
    alerts_sent = 0

    for item in all_markets_data:
        market_id = f"{item['store_chain']}_{item['branch_name']}".lower().replace(" ", "_")
        distance = round(geodesic(home_coords, item["coords"]).km, 1)
        
        is_fav = any(fav.lower() in item["branch_name"].lower() for fav in config["prioritized_stores"])
        fav_prefix = "❤️ [PRIO-MARKT] " if is_fav else ""
        
        stock_text = "🟢 Letztes Stück!" if item["stock"] == 1 else f"🟢 {item['stock']} Stück abholbereit!"
        new_state[market_id] = {"stock": item["stock"], "price": item["price"]}
        
        should_notify = (market_id not in old_state) or (old_state[market_id]["stock"] != item["stock"])
                
        if should_notify:
            msg = (
                f"🚨 {fav_prefix}PortaSplit 12k BTU direkt bei OBI!\n\n"
                f"📍 *{item['store_chain']} {item['branch_name']}*\n"
                f"🛣️ Entfernung: {distance} km\n"
                f"💰 Preis: {item['price']} €\n"
                f"📦 Bestand: {stock_text}\n\n"
                f"🔗 Link: {item['link']}"
            )
            send_telegram_message(msg)
            alerts_sent += 1
            write_to_log(f"ALERT: {item['store_chain']} {item['branch_name']} gemeldet (Bestand: {item['stock']}).")

    save_state(new_state)
    
    log_msg = f"Direkt-Check beendet. Märkte mit Bestand im {max_dist}km-Radius: {found_any_in_range}. Alarme gesendet: {alerts_sent}."
    write_to_log(log_msg)
    print("Check beendet.")

if __name__ == "__main__":
    main()
