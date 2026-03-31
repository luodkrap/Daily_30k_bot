"""
screener.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  매 시간(SCANNER_INTERVAL_SEC)마다 바이낸스 전 거래쌍을 스캔하여
  거래량, 변동성, 펌프앤덤프 필터를 적용하고
  조건 충족 코인들을 state.target_coin으로 업데이트하는 스캐너 엔진.

현재 상태:
  - Phase 2: 뼈대만 구현 (매시간 스캔 루프, 킬 이벤트 감지)
  - Phase 3: 실제 필터 로직 구현 예정
    * 거래량 필터: $100M 이상
    * ATR 변동성: min~max 범위
    * 펌프앤덤프 역필터: 이상 상승 탐지

구조:
  - run_screener(): 비동기 메인 루프
  - _scan(): 필터링 로직 (현재 빈 리스트 반환)

사용처:
  main.py에서 asyncio.gather()로 스크리너·엔진·텔레그램 봇 동시 실행
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
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
