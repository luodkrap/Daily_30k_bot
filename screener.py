"""
screener.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  매 시간(SCANNER_INTERVAL_SEC)마다 바이낸스 전 거래쌍을 스캔하여
  거래량, 변동성, 펌프앤덤프 필터를 적용하고
  조건 충족 코인들을 state.target_coin으로 업데이트하는 스캐너 엔진.

파이프라인:
  fetch_tickers()       → 전체 티커 1회 수신
  _pre_filter()         → USDT 페어, 스테이블/레버리지 제거, $100M 필터
  _fetch_candles_bulk() → asyncio.Semaphore 병렬 캔들 수집
  _apply_filters()      → ATR 필터 + 펌프앤덤프 역필터
  _score_and_rank()     → 점수 계산 → 상위 N개 반환

사용처:
  main.py에서 asyncio.gather()로 스크리너·엔진·텔레그램 봇 동시 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import ccxt.async_support as ccxt_async
from config import (
    SCANNER_INTERVAL_SEC,
    MIN_VOLUME_USD, MIN_PRICE_USD,
    ATR_MIN_RATE, ATR_MAX_RATE,
    SCANNER_SEMAPHORE, SCANNER_CANDLE_LIMIT, SCANNER_TOP_N,
    PUMP_THRESHOLD_3H, PUMP_THRESHOLD_6H, PUMP_VOLUME_SPIKE,
)
from shared_state import BotState
from notifier import notify_error, notify_scan_result

# 스테이블코인 base 목록 (USDT 페어로 상장되어 있으나 실제 거래 대상 아님)
_STABLECOINS = frozenset({
    "USDC", "BUSD", "DAI", "TUSD", "USDP", "FDUSD",
    "USDD", "FRAX", "LUSD", "GUSD", "EURC", "PYUSD",
})

# 레버리지 토큰 키워드 (suffix 방식으로만 판단)
_LEVERAGE_KEYWORDS = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "2L", "2S")


# ─── 메인 루프 ────────────────────────────────────────────

async def run_screener(state: BotState, exchange: ccxt_async.binance) -> None:
    """스캐너 엔진 — 매 SCANNER_INTERVAL_SEC마다 바이낸스 전 종목 스캔."""
    print("[Screener] 시작")
    while not state.kill_event.is_set():
        try:
            candidates = await _scan(exchange)
            state.screener_candidates = candidates
            if candidates:
                state.target_coin = candidates[0]["symbol"]
                print(f"[Screener] 타겟 선정: {state.target_coin} "
                      f"(후보 {len(candidates)}개)")
                await notify_scan_result(candidates[0])
            else:
                state.target_coin = ""
                print("[Screener] 조건 충족 코인 없음")
        except Exception as e:
            await notify_error("Screener", e)

        # 킬 이벤트 감지하면서 대기 (sleep 도중에도 즉시 반응)
        try:
            await asyncio.wait_for(
                state.kill_event.wait(),
                timeout=SCANNER_INTERVAL_SEC
            )
        except asyncio.TimeoutError:
            pass  # 정상 — 타임아웃 = 다음 스캔 주기

    print("[Screener] 종료")


# ─── 스캔 메인 함수 ───────────────────────────────────────

async def _scan(exchange: ccxt_async.binance) -> list[dict]:
    """바이낸스 전 종목 스캔 후 필터링·점수 계산된 후보 리스트 반환."""
    # 1단계: 전체 티커 수신 (1회 API 호출)
    tickers = await exchange.fetch_tickers()

    # 2단계: CPU 사전 필터 (USDT 페어, 스테이블/레버리지 제거, $100M, 최소 가격)
    symbols = _pre_filter(tickers)
    if not symbols:
        return []

    # 3단계: 병렬 캔들 수집
    candle_map = await _fetch_candles_bulk(symbols, exchange)

    # 4단계: ATR + 펌프앤덤프 필터 적용
    passed = []
    for symbol, ohlcv in candle_map.items():
        price = ohlcv[-1][4]  # 마지막 캔들 종가
        if price <= 0:
            continue

        atr = _calc_atr(ohlcv)
        atr_rate = atr / price

        if not (ATR_MIN_RATE <= atr_rate <= ATR_MAX_RATE):
            continue
        if _is_pumped(ohlcv):
            continue

        passed.append({
            "symbol":   symbol,
            "atr_rate": atr_rate,
            "volume":   tickers[symbol].get("quoteVolume") or 0,
            "last":     price,
            "ohlcv":    ohlcv,
        })

    if not passed:
        return []

    # 5단계: 점수 계산 및 정렬
    return _score_and_rank(passed)


# ─── 헬퍼 함수들 ─────────────────────────────────────────

def _pre_filter(tickers: dict) -> list[str]:
    """CPU 사전 필터 — API 호출 없이 심볼 목록을 대폭 축소."""
    result = []
    for symbol, ticker in tickers.items():
        # USDT 페어만
        if not symbol.endswith("/USDT"):
            continue

        # 스테이블코인 제외
        base = symbol.split("/")[0]
        if base in _STABLECOINS:
            continue

        # 레버리지 토큰 제외 (base 코인 suffix 기준)
        if any(base.endswith(kw) for kw in _LEVERAGE_KEYWORDS):
            continue

        # 거래량 $100M 이상
        volume = ticker.get("quoteVolume") or 0
        if volume < MIN_VOLUME_USD:
            continue

        # 현재가 유효성
        last = ticker.get("last") or 0
        if last <= 0:
            continue

        # 최소 가격 필터 — $0.10 미만 저가 코인은 그리드 매매 부적합
        if last < MIN_PRICE_USD:
            continue

        result.append(symbol)
    return result


async def _fetch_candles_bulk(
    symbols: list[str],
    exchange: ccxt_async.binance,
) -> dict[str, list]:
    """asyncio.Semaphore로 병렬 캔들 수집 (동시 최대 SCANNER_SEMAPHORE개)."""
    sem = asyncio.Semaphore(SCANNER_SEMAPHORE)

    async def fetch_one(symbol: str):
        async with sem:
            try:
                ohlcv = await exchange.fetch_ohlcv(
                    symbol, "1h", limit=SCANNER_CANDLE_LIMIT
                )
                return symbol, ohlcv
            except Exception:
                return symbol, None

    results = await asyncio.gather(*[fetch_one(s) for s in symbols])
    return {
        sym: data
        for sym, data in results
        if data and len(data) >= SCANNER_CANDLE_LIMIT
    }


def _calc_atr(ohlcv: list) -> float:
    """ATR(14) 계산 — Wilder's Smoothing (EMA 방식).

    ohlcv 인덱스: [0]timestamp [1]open [2]high [3]low [4]close [5]volume
    """
    # True Range 계산
    tr_list = []
    for i in range(1, len(ohlcv)):
        high  = ohlcv[i][2]
        low   = ohlcv[i][3]
        prev_close = ohlcv[i - 1][4]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)

    if len(tr_list) < 14:
        return 0.0

    # 초기값: 첫 14개 단순 평균
    atr = sum(tr_list[:14]) / 14

    # Wilder's Smoothing
    for tr in tr_list[14:]:
        atr = (atr * 13 + tr) / 14

    return atr


def _is_pumped(ohlcv: list) -> bool:
    """펌프앤덤프 감지 — 아래 조건 중 하나라도 True이면 제외 대상."""
    closes  = [c[4] for c in ohlcv]
    highs   = [c[2] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]

    # 최근 3h 급등 감지
    if len(closes) >= 4:
        base_3h = closes[-4]
        peak_3h = max(highs[-3:])
        if base_3h > 0 and (peak_3h / base_3h) > (1 + PUMP_THRESHOLD_3H):
            return True

    # 최근 6h 급등 감지
    if len(closes) >= 7:
        base_6h = closes[-7]
        peak_6h = max(highs[-6:])
        if base_6h > 0 and (peak_6h / base_6h) > (1 + PUMP_THRESHOLD_6H):
            return True

    # 거래량 스파이크 감지 (마지막 캔들 vs 나머지 평균)
    if len(volumes) >= 2:
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
        if avg_vol > 0 and (volumes[-1] / avg_vol) > PUMP_VOLUME_SPIKE:
            return True

    return False


def _score_and_rank(passed: list[dict]) -> list[dict]:
    """점수 계산 후 내림차순 정렬, 상위 SCANNER_TOP_N개 반환.

    score = atr_score*0.5 + vol_score*0.3 + stability_score*0.2
      - atr_score       : ATR 범위 중앙값(2.75%)에 가까울수록 높음
      - vol_score       : 후보군 내 거래량 min-max 정규화
      - stability_score : 후보군 내 종가 CV min-max 정규화 (낮을수록 박스권)
    """
    atr_mid  = (ATR_MIN_RATE + ATR_MAX_RATE) / 2   # 2.75%
    atr_half = (ATR_MAX_RATE - ATR_MIN_RATE) / 2   # 2.25%

    vols  = [c["volume"] for c in passed]
    v_min = min(vols)
    v_max = max(vols)
    v_range = max(v_max - v_min, 1)

    # 1차: 각 코인의 종가 CV 사전 계산
    for coin in passed:
        closes = [c[4] for c in coin["ohlcv"]]
        mean_p = sum(closes) / len(closes)
        if mean_p > 0:
            std_p = (sum((c - mean_p) ** 2 for c in closes) / len(closes)) ** 0.5
            coin["_cv"] = std_p / mean_p
        else:
            coin["_cv"] = float("inf")

    finite_cvs = [c["_cv"] for c in passed if c["_cv"] != float("inf")]
    if finite_cvs:
        cv_min = min(finite_cvs)
        cv_max = max(finite_cvs)
        cv_range = max(cv_max - cv_min, 1e-9)
    else:
        cv_min = 0.0
        cv_range = 1.0

    # 2차: 점수 합산
    for coin in passed:
        atr_score = max(0.0, 1.0 - abs(coin["atr_rate"] - atr_mid) / atr_half)
        vol_score = (coin["volume"] - v_min) / v_range

        cv = coin.pop("_cv")
        if cv == float("inf"):
            stability_score = 0.0
        else:
            stability_score = 1.0 - (cv - cv_min) / cv_range

        coin["score"] = atr_score * 0.5 + vol_score * 0.3 + stability_score * 0.2

    # ohlcv 데이터는 반환값에서 제거 (메모리 절약)
    ranked = sorted(passed, key=lambda c: c["score"], reverse=True)
    for coin in ranked:
        coin.pop("ohlcv", None)

    return ranked[:SCANNER_TOP_N]
