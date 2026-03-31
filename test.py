import os
import asyncio
import ccxt
import ccxt.async_support as ccxt_async
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


# ─────────────────────────────────────────────────────────
# Phase 3 단위 테스트 (오프라인 — API 호출 없음)
# ─────────────────────────────────────────────────────────

def _make_ohlcv(prices: list[float], volumes: list[float] = None) -> list:
    """테스트용 OHLCV mock 데이터 생성 (high=close*1.005, low=close*0.995)."""
    if volumes is None:
        volumes = [1_000_000.0] * len(prices)
    return [
        [i * 3600000, p * 0.995, p * 1.005, p * 0.995, p, v]
        for i, (p, v) in enumerate(zip(prices, volumes))
    ]


def test_calc_atr():
    from screener import _calc_atr

    # 15개 캔들, 모두 같은 가격 → TR ≈ 0, ATR ≈ 0
    ohlcv = _make_ohlcv([100.0] * 15)
    atr = _calc_atr(ohlcv)
    assert atr < 0.01 * 100, f"평탄 캔들 ATR 오류: {atr}"

    # 가격 변동이 있는 캔들 → ATR > 0
    prices = [100 + i % 3 for i in range(15)]  # 100, 101, 102 반복
    ohlcv2 = _make_ohlcv(prices)
    atr2 = _calc_atr(ohlcv2)
    assert atr2 > 0, f"변동 캔들 ATR이 0: {atr2}"

    print(f"  [PASS] _calc_atr: 평탄={atr:.4f}, 변동={atr2:.4f}")


def test_is_pumped():
    from screener import _is_pumped

    # 시나리오 A: 정상 (급등 없음) → False
    prices = [100.0] * 15
    ohlcv_normal = _make_ohlcv(prices)
    assert _is_pumped(ohlcv_normal) is False, "정상 케이스에서 True 반환"

    # 시나리오 B: 최근 3h 8% 급등 → True
    prices_pump3h = [100.0] * 11 + [101.0, 102.0, 107.0, 109.0]
    # high를 급등 가격으로 조정
    ohlcv_pump3h = _make_ohlcv(prices_pump3h)
    for i in range(-3, 0):
        ohlcv_pump3h[i][2] = prices_pump3h[i] * 1.05  # high를 더 높게
    assert _is_pumped(ohlcv_pump3h) is True, "3h 급등 케이스에서 False 반환"

    # 시나리오 C: 거래량 스파이크 6배 → True
    volumes_spike = [1_000_000.0] * 14 + [6_000_000.0]
    ohlcv_vol = _make_ohlcv([100.0] * 15, volumes_spike)
    assert _is_pumped(ohlcv_vol) is True, "거래량 스파이크 케이스에서 False 반환"

    print("  [PASS] _is_pumped: 정상/3h급등/거래량스파이크 3가지 케이스")


def test_pre_filter():
    from screener import _pre_filter

    mock_tickers = {
        "BTC/USDT":    {"quoteVolume": 500_000_000, "last": 50000},  # 통과
        "ETH/USDT":    {"quoteVolume": 300_000_000, "last": 2000},   # 통과
        "USDC/USDT":   {"quoteVolume": 200_000_000, "last": 1.0},    # 스테이블 → 제외
        "ETHUP/USDT":  {"quoteVolume": 200_000_000, "last": 5.0},    # 레버리지 → 제외
        "XRP/BTC":     {"quoteVolume": 200_000_000, "last": 0.5},    # USDT 아님 → 제외
        "DOGE/USDT":   {"quoteVolume": 5_000_000,   "last": 0.1},    # 거래량 미달 → 제외
        "SHIB/USDT":   {"quoteVolume": 150_000_000, "last": None},   # 가격 없음 → 제외
        "NIGHT/USDT":  {"quoteVolume": 200_000_000, "last": 0.05},   # 저가 코인 → 제외
    }
    result = _pre_filter(mock_tickers)
    assert "BTC/USDT" in result, "BTC/USDT가 필터에서 제외됨"
    assert "ETH/USDT" in result, "ETH/USDT가 필터에서 제외됨"
    assert "USDC/USDT" not in result, "스테이블코인이 통과됨"
    assert "ETHUP/USDT" not in result, "레버리지 토큰이 통과됨"
    assert "XRP/BTC" not in result, "비USDT 페어가 통과됨"
    assert "DOGE/USDT" not in result, "거래량 미달 코인이 통과됨"
    assert "SHIB/USDT" not in result, "가격 없는 코인이 통과됨"
    assert "NIGHT/USDT" not in result, "저가 코인($0.05)이 통과됨"
    print(f"  [PASS] _pre_filter: {len(result)}개 통과 ({result})")


# ─────────────────────────────────────────────────────────
# Phase 3 통합 테스트 (온라인 — 실제 바이낸스 API 호출)
# ─────────────────────────────────────────────────────────

async def test_scan_online():
    """실제 바이낸스 API를 사용한 스캐너 통합 테스트."""
    from screener import _scan

    print("\n[통합 테스트] 바이낸스 실시간 스캔 시작 (수십 초 소요)...")
    ex = ccxt_async.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET_KEY,
        "enableRateLimit": True,
    })
    try:
        candidates = await _scan(ex)
        print(f"  후보 {len(candidates)}개:")
        for c in candidates:
            print(f"    {c['symbol']}: score={c['score']:.3f}, "
                  f"ATR={c['atr_rate']*100:.2f}%, "
                  f"거래량=${c['volume']:,.0f}, "
                  f"현재가=${c['last']:,.4f}")

        # 체크리스트
        if candidates:
            for c in candidates:
                from config import ATR_MIN_RATE, ATR_MAX_RATE
                assert ATR_MIN_RATE <= c["atr_rate"] <= ATR_MAX_RATE, \
                    f"{c['symbol']} ATR 범위 초과: {c['atr_rate']}"
            print("  [PASS] 모든 후보의 ATR 비율 범위 내")
        else:
            print("  [INFO] 조건 충족 코인 없음 (시장 상황에 따라 정상)")
    finally:
        await ex.close()


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "basic"

    if mode == "unit":
        # 단위 테스트만 실행 (오프라인)
        print("=== Phase 3 단위 테스트 ===")
        test_calc_atr()
        test_is_pumped()
        test_pre_filter()
        print("모든 단위 테스트 통과!")

    elif mode == "scan":
        # 통합 테스트 실행 (온라인)
        asyncio.run(test_scan_online())

    else:
        # 기존 기본 테스트 (바이낸스 연결 + 텔레그램)
        print("바이낸스 연결 중...")
        btc_price = get_btc_price()
        print(f"현재 BTC 가격: ${btc_price}")

        message = f"도울 님, 연결 성공! 현재 비트코인 가격은 ${btc_price}입니다."
        send_telegram_message(message)
        print("텔레그램 메시지 전송 완료!")
