"""
Surveillance de stock Pokémon (version GitHub Actions).
Une exécution = un passage sur tous les produits. Le workflow le relance
toutes les ~5 minutes. Le token Telegram vient des "Secrets" GitHub.
"""
import json
import os
import random
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CONFIG = json.loads(Path("config.json").read_text(encoding="utf-8"))
STATE_FILE = Path("state.json")
TG_TOKEN = os.environ["TELEGRAM_TOKEN"]
TG_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def alert(message: str) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data={"chat_id": TG_CHAT_ID, "text": message},
            timeout=15,
        )
    except requests.RequestException as e:
        print(f"[telegram] erreur : {e}")


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def jsonld_in_stock(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for node in walk(data):
            offers = node.get("offers") if isinstance(node, dict) else None
            if not offers:
                continue
            for offer in offers if isinstance(offers, list) else [offers]:
                availability = str(offer.get("availability", ""))
                if availability:
                    return availability.endswith(("InStock", "LimitedAvailability"))
    return None


def check_product(product: dict):
    r = requests.get(product["url"], headers=HEADERS, timeout=20)
    if r.status_code in (403, 429):
        raise RuntimeError(f"bloqué ({r.status_code})")
    r.raise_for_status()
    return jsonld_in_stock(r.text)


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    for p in CONFIG["products"]:
        key = p["url"]
        try:
            in_stock = check_product(p)
        except Exception as e:
            print(f"[{p['retailer']}] {p['name']} : {e}")
            time.sleep(random.uniform(2, 5))
            continue

        print(f"[{p['retailer']}] {p['name']} -> {in_stock}")
        if in_stock and not state.get(key):
            alert(f"🔥 EN STOCK : {p['name']}\n{p['retailer']}\n{p['url']}")
        if in_stock is not None:
            state[key] = in_stock
        time.sleep(random.uniform(2, 5))

    STATE_FILE.write_text(json.dumps(state, indent=1))


if __name__ == "__main__":
    main()
