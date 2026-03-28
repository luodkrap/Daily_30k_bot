import os
import ccxt
import requests
from dotenv import load_dotenv

load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

exchange = ccxt.binance({
    "apiKey": BINANCE_API_KEY,
    "secret": BINANCE_SECRET_KEY,
    "enableRateLimit": True,
})


def get_btc_price():
    ticker = exchange.fetch_ticker("BTC/USDT")
    price = ticker["last"]
    return f"{price:,.2f}"


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    print("바이낸스 연결 중...")
    btc_price = get_btc_price()
    print(f"현재 BTC 가격: ${btc_price}")

    message = f"도울 님, 연결 성공! 현재 비트코인 가격은 ${btc_price}입니다."
    send_telegram_message(message)
    print("텔레그램 메시지 전송 완료!")
