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
    """Schreibt einen Eintrag mit aktuellem Zeitstempel in die Log-Datei."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

def fetch_aggregated_stock():
    """Fragt die API ab, die die Bestände aller großen Ketten bündelt."""
    url = "https://api.midea-ticker.de/v1/portasplit/stock" 
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Fehler beim Abruf der Community-API: {e}")
    return []

def main():
    print("Starte Live-Abfrage für alle Händler...")
    config = load_config()
    old_state = load_state()
    new_state = {}
    
    home_coords = config["home_coords"]
    max_dist = config["max_distance_km"]
    
    all_markets_data = fetch_aggregated_stock()
    
    if not all_markets_data:
        write_to_log("WARNUNG: Keine Marktdaten von der API empfangen (API evtl. offline).")
        return

    found_any_in_range = 0
    alerts_sent = 0

    for item in all_markets_data:
        # 1. Schutz: Nur 12000 BTU
        if "12000" not in item.get("product", ""):
            continue
            
        # 2. Schutz: Nur mit Bestand oder Versand
        stock = item.get("stock", 0)
        shipping_available = item.get("shipping_available", False)
        if stock <= 0 and not shipping_available:
            continue
            
        # 3. Entfernung berechnen
        market_coords = item.get("coords")
        if not market_coords:
            continue
            
        distance = round(geodesic(home_coords, market_coords).km, 1)
        
        # Filter: 100km Umkreis (außer Versand ist möglich)
        if distance > max_dist and not shipping_available:
            continue
            
        found_any_in_range += 1
        market_id = f"{item['store_chain']}_{item['branch_name']}".lower().replace(" ", "_")
        
        # Favoriten markieren
        is_fav = any(fav.lower() in item["branch_name"].lower() for fav in config["prioritized_stores"])
        fav_prefix = "❤️ [PRIO-MARKT] " if is_fav else ""
        
        if shipping_available and stock <= 0:
            stock_text = "📦 Bundesweiter LKW-Versand verfügbar!"
        elif stock == 1:
            stock_text = "🟢 Letztes Stück auf Lager!"
        else:
            stock_text = f"🟢 {stock} Stück abholbereit!"
            
        new_state[market_id] = {"stock": stock, "price": item["price"], "shipping": shipping_available}
        
        # Smart Alert Logik
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
            alerts_sent += 1
            write_to_log(f"ALERT: {item['store_chain']} {item['branch_name']} gemeldet (Bestand: {stock}, Preis: {item['price']}€).")

    save_state(new_state)
    
    # Zusammenfassung in das Log schreiben
    log_msg = f"Erfolgreich durchgelaufen. Märkte im Umkreis mit Bestand: {found_any_in_range}. Gesendete Telegram-Alarme: {alerts_sent}."
    write_to_log(log_msg)
    print("Live-Check beendet und protokolliert.")

if __name__ == "__main__":
    main()
