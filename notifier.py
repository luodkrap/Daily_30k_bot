"""
notifier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  텔레그램 API를 통해 봇 이벤트(거래, 킬 스위치, 오류, 상태)를
  실시간으로 사용자에게 알리는 비동기 알림 모듈.

함수:
  - send(text): 기본 메시지 전송 (중복 억제 + 발송 간격 스로틀)
  - notify_trade(): 진입/청산 알림
  - notify_daily_stop(): 수익/손실로 인한 일일 중단
  - notify_kill_switch(): 킬 스위치 발동
  - notify_error(): 오류 발생 즉시 보고
  - notify_scan_result(): 스캐너 타겟 선정 결과 보고
  - notify_status(): /status 커맨드에 대한 현황 보고

특징:
  - aiohttp로 비동기 처리 (블로킹 없음)
  - 모든 함수는 asyncio 코루틴
  - H2 플러드 방지: 동일 메시지 60초 이내 중복 억제, 전체 발송 최소 1초 간격

사용처:
  main.py, screener.py, executor.py (Phase 4), 텔레그램 봇 핸들러
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import time
import aiohttp
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# TCP+TLS 연결을 재사용하여 메시지당 ~600ms 지연 제거
_session: aiohttp.ClientSession | None = None

# H2 플러드 방지 상태
_DEDUP_WINDOW_SEC = 60.0
_MIN_SEND_INTERVAL_SEC = 1.0
_recent_messages: dict[str, float] = {}
_last_send_ts: float = 0.0
_send_lock = asyncio.Lock()


async def init_session() -> None:
    """앱 시작 시 1회 호출 — 이후 모든 알림이 이 세션을 공유."""
    global _session
    _session = aiohttp.ClientSession()


async def close_session() -> None:
    """앱 종료 시 1회 호출."""
    global _session
    if _session:
        await _session.close()
        _session = None


async def _deliver(text: str) -> None:
    """실제 텔레그램 HTTP 전송. 테스트에서 몽키패치하여 동작 검증."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    if _session is None or _session.closed:
        # 세션이 없으면 임시 생성 (init_session 미호출 방어)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
    else:
        async with _session.post(url, json=payload) as resp:
            resp.raise_for_status()


async def send(text: str) -> None:
    global _last_send_ts

    # 중복 억제 사전 체크 (락 획득 없이 빠른 경로)
    now = time.monotonic()
    last = _recent_messages.get(text)
    if last is not None and now - last < _DEDUP_WINDOW_SEC:
        return

    async with _send_lock:
        # 락 획득 후 재확인 (경쟁 상태 방어)
        now = time.monotonic()
        last = _recent_messages.get(text)
        if last is not None and now - last < _DEDUP_WINDOW_SEC:
            return

        # 전체 발송 최소 간격 강제
        gap = now - _last_send_ts
        if gap < _MIN_SEND_INTERVAL_SEC:
            await asyncio.sleep(_MIN_SEND_INTERVAL_SEC - gap)

        # 실패해도 스로틀은 유지 (실패 루프가 API 를 때리는 것을 막기 위함)
        attempt_ts = time.monotonic()
        _last_send_ts = attempt_ts

        try:
            await _deliver(text)
        except Exception as e:
            print(f"[Notifier] 텔레그램 전송 실패: {e}")
            return

        _recent_messages[text] = attempt_ts
        cutoff = attempt_ts - _DEDUP_WINDOW_SEC
        for k in [k for k, v in _recent_messages.items() if v < cutoff]:
            _recent_messages.pop(k, None)


def _reset_flood_state() -> None:
    """테스트 전용 — 중복 억제·스로틀 상태 초기화."""
    global _last_send_ts
    _recent_messages.clear()
    _last_send_ts = 0.0


async def notify_trade(coin: str, side: str, price: float, pnl: float) -> None:
    emoji = "+" if pnl >= 0 else "-"
    await send(f"[거래] {coin} {side} @ {price:,.0f}\n손익: {emoji}{abs(pnl):,.0f}원")


async def notify_daily_stop(reason: str, daily_pnl: float) -> None:
    await send(f"[중단] {reason}\n오늘 수익: {daily_pnl:,.0f}원")


async def notify_kill_switch() -> None:
    await send("[킬 스위치] 봇이 긴급 중단됩니다. 모든 주문을 취소합니다.")


async def notify_error(context: str, error: Exception) -> None:
    await send(f"[오류] {context}\n{type(error).__name__}: {error}")


async def notify_scan_result(candidate: dict) -> None:
    msg = (
        f"[스캐너] 타겟 선정\n"
        f"코인: {candidate['symbol']}\n"
        f"점수: {candidate['score']:.3f}\n"
        f"ATR 비율: {candidate['atr_rate']*100:.2f}%\n"
        f"24h 거래량: ${candidate['volume']:,.0f}\n"
        f"현재가: ${candidate['last']:,.4f}"
    )
    await send(msg)


async def notify_status(state) -> None:
    from config import DAILY_TARGET
    pnl_pct = (state.daily_pnl / DAILY_TARGET * 100) if DAILY_TARGET else 0
    msg = (
        f"[상태]\n"
        f"타겟 코인: {state.target_coin or '없음'}\n"
        f"일일 손익: {state.daily_pnl:,.0f}원 ({pnl_pct:.1f}%)\n"
        f"거래 횟수: {state.trade_count}회 (승률 {state.win_rate*100:.0f}%)\n"
        f"시장 상태: {'정상' if state.is_market_healthy else '악화'}"
    )
    await send(msg)
