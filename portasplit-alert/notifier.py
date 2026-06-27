import os
import json
import requests

def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            chat_id = config.get("telegram_chat_id")
    except Exception:
        print("Konnte config.json nicht lesen.")
        return

    if not token or not chat_id:
        print("Token oder Chat-ID fehlt.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload, timeout=10)
