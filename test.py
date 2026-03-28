import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def get_btc_price():
    # TODO: 바이낸스 API 키 발급 후 아래 주석 해제, 더미 데이터 제거
    # url = "https://api.binance.com/api/v3/ticker/price"
    # response = requests.get(url, params={"symbol": "BTCUSDT"})
    # response.raise_for_status()
    # price = float(response.json()["price"])
    # return f"{price:,.2f}"
    return "99,999.00"  # 더미 데이터


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
