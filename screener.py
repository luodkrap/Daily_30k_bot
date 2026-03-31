import asyncio
import ccxt.async_support as ccxt_async
from config import SCANNER_INTERVAL_SEC
from shared_state import BotState
from notifier import notify_error


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


async def _scan(exchange: ccxt_async.binance) -> list[dict]:
    """
    바이낸스 전 종목 스캔 후 필터링된 후보 리스트 반환.
    Phase 3에서 실제 필터 로직 구현 예정.
    현재는 뼈대만 존재.
    """
    # TODO Phase 3: 거래량 필터 ($100M 이상)
    # TODO Phase 3: ATR 변동성 필터
    # TODO Phase 3: 펌프앤덤프 역필터
    return []
