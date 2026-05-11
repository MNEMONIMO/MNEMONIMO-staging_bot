import os
import time
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from collections import OrderedDict

# --- Конфигурация ---
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY")
TARGET_ASSET_ID = os.getenv("TARGET_ASSET_ID", "")
VOLUME_THRESHOLD_USD = float(os.getenv("VOLUME_THRESHOLD_USD", 5000))
FRESH_WALLET_HOURS = float(os.getenv("FRESH_WALLET_HOURS", 24))
TOP_MARKETS_COUNT = int(os.getenv("TOP_MARKETS_COUNT", 10))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", 10))

POLYMARKET_GAMMA_URL = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_URL = "https://clob.polymarket.com"
POLYGONSCAN_API_URL = "https://api.polygonscan.com/api"

class LRUCache:
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity

    def get(self, key):
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def put(self, key, value):
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    def __contains__(self, key):
        return key in self.cache

# Простой кэш для кошельков: адрес -> datetime первого tx
wallet_cache = LRUCache(2000)
# Кэш обработанных сделок (чтобы не дублировать)
processed_trades = LRUCache(5000)

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending TG message: {e}")

def get_wallet_age(wallet_address):
    cached_age = wallet_cache.get(wallet_address)
    if cached_age:
        return cached_age

    if not POLYGONSCAN_API_KEY:
        return datetime.now(timezone.utc) - timedelta(days=365) # fallback old

    params = {
        "module": "account",
        "action": "txlist",
        "address": wallet_address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 1,
        "sort": "asc",
        "apikey": POLYGONSCAN_API_KEY
    }
    try:
        resp = requests.get(POLYGONSCAN_API_URL, params=params, timeout=10)
        data = resp.json()
        if data.get("status") == "1" and data.get("result"):
            first_tx = data["result"][0]
            first_tx_time = datetime.fromtimestamp(int(first_tx["timeStamp"]), tz=timezone.utc)
            wallet_cache.put(wallet_address, first_tx_time)
            return first_tx_time
    except Exception as e:
        print(f"Error fetching wallet age: {e}")

    # If we couldn't fetch, mark as old to avoid false alerts
    default_age = datetime.now(timezone.utc) - timedelta(days=365)
    wallet_cache.put(wallet_address, default_age)
    return default_age

def classify_trade(wallet_address, trade_volume):
    first_tx_time = get_wallet_age(wallet_address)
    now = datetime.now(timezone.utc)
    age = now - first_tx_time

    # 1. WHALE check
    if trade_volume > VOLUME_THRESHOLD_USD * 2:
        return "🐋 WHALE"

    # 2. Age checks
    if age < timedelta(hours=12):
        return "🔥 NEW BORN"
    if age < timedelta(hours=FRESH_WALLET_HOURS):
        return "🚨 FRESH"
    if age < timedelta(days=3):
        return "👶 YOUNG"

    if trade_volume > VOLUME_THRESHOLD_USD:
        return "💰 BIG TRADE"

    return "REGULAR"

def fetch_top_markets():
    try:
        resp = requests.get(f"{POLYMARKET_GAMMA_URL}/events", params={"limit": TOP_MARKETS_COUNT, "active": "true"}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def fetch_trades(token_id):
    """Fetch recent trades for a specific token_id via CLOB API."""
    try:
        resp = requests.get(f"{POLYMARKET_CLOB_URL}/prices-history", params={"market": token_id, "interval": "1m"}, timeout=10)
        # However, for actual trades (maker/taker) we need the trades endpoint.
        resp = requests.get(f"{POLYMARKET_CLOB_URL}/trades", params={"market": token_id}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])
    except Exception as e:
        # Avoid spamming output too much if an endpoint doesn't exist or rate limits
        return []

def process_trade(trade):
    trade_id = trade.get("id") or trade.get("transactionHash")
    if not trade_id or trade_id in processed_trades:
        return

    processed_trades.put(trade_id, True)

    try:
        volume = float(trade.get("size", 0)) * float(trade.get("price", 0))
    except ValueError:
        volume = 0.0

    wallet = trade.get("maker", trade.get("taker", "0x0"))

    if volume > 10:
        print(f"Pulse: Trade ${volume:.2f} by {wallet}")

    if volume > VOLUME_THRESHOLD_USD:
        classification = classify_trade(wallet, volume)
        if classification != "REGULAR":
            msg = f"{classification} Alert!\n\n"
            msg += f"Volume: ${volume:.2f}\n"
            msg += f"Wallet: {wallet}\n"
            send_telegram_message(msg)

def get_tokens_from_market(market):
    """Extract token_ids (condition IDs or tokens) from a market to query CLOB."""
    tokens = []
    markets = market.get("markets", [])
    if isinstance(markets, list):
        for m in markets:
            clob_token_id = m.get("clobTokenIds", [])
            if isinstance(clob_token_id, list):
                try:
                    tokens.extend([json.loads(t) if isinstance(t, str) and t.startswith('[') else t for t in clob_token_id])
                except:
                    pass
                for t in clob_token_id:
                    if isinstance(t, str) and not t.startswith('['):
                        tokens.append(t)
    return tokens

def main():
    print("🚀 Starting Polymarket Ultra Bot v4.0...")
    while True:
        try:
            if TARGET_ASSET_ID:
                trades = fetch_trades(TARGET_ASSET_ID)
                for t in trades:
                    process_trade(t)
            else:
                events = fetch_top_markets()
                for event in events:
                    # An event contains markets. We need to get the tokens to fetch CLOB trades.
                    tokens = get_tokens_from_market(event)
                    for t_id in tokens:
                        trades = fetch_trades(t_id)
                        for t in trades:
                            process_trade(t)

            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
