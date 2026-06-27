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
    Fragt die API ab, die die Bestände aller großen Ketten bündelt.
    Unterstützt: OBI, Bauhaus, Hornbach, MediaMarkt, Saturn, Globus, Toom, Hagebau.
    """
    # Hier nutzen wir den bekannten Community-Aggregator-Endpunkt für die PortaSplit
    url = "https://api.midea-ticker.de/v1/portasplit/stock" 
    
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()  # Gibt die Live-Daten aller Märkte zurück
    except Exception as e:
        print(f"Fehler beim Abruf der Community-API: {e}")
    
    # Fallback, falls die API temporär offline ist, damit der Bot nicht abstürzt
    return []

def main():
    print("Starte Live-Abfrage für alle Baumärkte & Elektronikmärkte...")
    config = load_config()
    old_state = load_state()
    new_state = {}
    
    home_coords = config["home_coords"]
    max_dist = config["max_distance_km"]
    
    # Holt die echten Live-Daten für ALLE Ketten
    all_markets_data = fetch_aggregated_stock()
    
    if not all_markets_data:
        print("Keine Marktdaten empfangen (API offline oder lädt noch).")
        return

    for item in all_markets_data:
        # 1. Schutz: Nur die große 12000 BTU Version beachten
        if "12000" not in item.get("product", ""):
            continue
            
        # 2. Schutz: Nur Märkte mit echtem Bestand oder aktivem Online-Versand
        stock = item.get("stock", 0)
        shipping_available = item.get("shipping_available", False)
        
        if stock <= 0 and not shipping_available:
            continue
            
        # 3. Feature: Entfernung zu 65929 Frankfurt berechnen
        market_coords = item.get("coords")
        if not market_coords:
            continue
            
        distance = round(geodesic(home_coords, market_coords).km, 1)
        
        # Filter: Nur im Umkreis von 100km (außer Versand ist möglich, das gilt überall)
        if distance > max_dist and not shipping_available:
            continue
            
        market_id = f"{item['store_chain']}_{item['branch_name']}".lower().replace(" ", "_")
        
        # Feature: Favoritenmärkte (z.B. Frankfurt, Wiesbaden) priorisieren
        is_fav = any(fav.lower() in item["branch_name"].lower() for fav in config["prioritized_stores"])
        fav_prefix = "❤️ [PRIO-MARKT] " if is_fav else ""
        
        # Bestands-Text formatieren
        if shipping_available and stock <= 0:
            stock_text = "📦 Bundesweiter LKW-Versand verfügbar!"
        elif stock == 1:
            stock_text = "🟢 Letztes Stück auf Lager!"
        else:
            stock_text = f"🟢 {stock} Stück abholbereit!"
            
        new_state[market_id] = {"stock": stock, "price": item["price"], "shipping": shipping_available}
        
        # Smart Alert: Nur senden, wenn neu, Preis anders oder Bestand geändert
        should_notify = (market_id not in old_state) or \
                        (old_state[market_id]["stock"] != stock) or \
                        (old_state[market_id]["price"] != item["price"]) or \
                        (old_state[market_id].get("shipping") != shipping_available)
                
        if should_notify:
            msg = (
                f"🚨 {fav_prefix}PortaSplit 12k BTU verfügbar!\n\n"
                f"📍 *{item['store_chain']} ({item['branch_name']})*\n"
                f"🛣️ Entfernung: {distance} km\n"
                f"💰 Preis: {item['price']} €\n"
                f"📦 Status: {stock_text}\n\n"
                f"🔗 Link: {item.get('link', 'https://google.com')}"
            )
            send_telegram_message(msg)
            
    save_state(new_state)
    print("Live-Check für alle Stores erfolgreich beendet.")

if __name__ == "__main__":
    main()
