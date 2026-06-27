import os
import json
import requests
from geopy.distance import geodesic
from notifier import send_telegram_message

CONFIG_FILE = "config.json"
STATE_FILE = "search_state.json"

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

def fetch_aggregated_stock():
    """
    Simuliert den Abruf der Live-Bestandsdaten für OBI, Bauhaus, Hornbach, 
    MediaMarkt, Saturn etc. im Frankfurter Raum.
    """
    return [
        {
            "store_chain": "OBI",
            "branch_name": "Wiesbaden",
            "coords": [50.0624, 8.2281],
            "product": "Midea PortaSplit 12000 BTU",
            "price": 699.00,
            "stock": 3,
            "link": "https://www.obi.de/de/search/portasplit"
        },
        {
            "store_chain": "Bauhaus",
            "branch_name": "Frankfurt-Hanauer Landstraße",
            "coords": [50.1132, 8.7341],
            "product": "Midea PortaSplit 12000 BTU",
            "price": 695.00,
            "stock": 1,
            "link": "https://www.bauhaus.info/"
        },
        {
            "store_chain": "MediaMarkt",
            "branch_name": "Eschborn",
            "coords": [50.1425, 8.5689],
            "product": "Midea PortaSplit 8000 BTU",  # Wird ignoriert
            "price": 499.00,
            "stock": 5,
            "link": "https://www.mediamarkt.de/"
        }
    ]

def main():
    print("Starte PortaSplit Stock Monitor...")
    config = load_config()
    old_state = load_state()
    new_state = {}
    
    home_coords = config["home_coords"]
    max_dist = config["max_distance_km"]
    
    all_markets_data = fetch_aggregated_stock()
    
    for item in all_markets_data:
        # Feature: 8000 BTU ignorieren
        if "12000" not in item["product"]:
            continue
            
        if item["stock"] <= 0:
            continue
            
        # Feature: Entfernung berechnen
        distance = round(geodesic(home_coords, item["coords"]).km, 1)
        if distance > max_dist:
            continue
            
        market_id = f"{item['store_chain']}_{item['branch_name']}".lower().replace(" ", "_")
        
        # Feature: Favoriten hervorheben
        is_fav = any(fav.lower() in item["branch_name"].lower() for fav in config["prioritized_stores"])
        fav_prefix = "❤️ [FAVORIT] " if is_fav else ""
        
        stock_text = f"{item['stock']} Stück" if item["stock"] > 1 else "🟢 Letztes Stück!"
        
        new_state[market_id] = {"stock": item["stock"], "price": item["price"]}
        
        # Smart Alert: Nur bei echten Änderungen funken
        should_notify = (market_id not in old_state) or \
                        (old_state[market_id]["stock"] != item["stock"]) or \
                        (old_state[market_id]["price"] != item["price"])
                
        if should_notify:
            msg = (
                f"🚨 {fav_prefix}PortaSplit gefunden!\n\n"
                f"📍 *{item['store_chain']} {item['branch_name']}*\n"
                f"🛣️ Entfernung: {distance} km\n"
                f"💰 Preis: {item['price']} €\n"
                f"📦 Bestand: {stock_text}\n\n"
                f"🔗 Link: {item['link']}"
            )
            send_telegram_message(msg)
            
    save_state(new_state)
    print("Check beendet.")

if __name__ == "__main__":
    main()
