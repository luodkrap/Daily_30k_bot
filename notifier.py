"""
notifier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  텔레그램 API를 통해 봇 이벤트(거래, 킬 스위치, 오류, 상태)를
  실시간으로 사용자에게 알리는 비동기 알림 모듈.

함수:
  - send(text): 기본 메시지 전송
  - notify_trade(): 진입/청산 알림
  - notify_daily_stop(): 수익/손실로 인한 일일 중단
  - notify_kill_switch(): 킬 스위치 발동
  - notify_error(): 오류 발생 즉시 보고
  - notify_scan_result(): 스캐너 타겟 선정 결과 보고
  - notify_status(): /status 커맨드에 대한 현황 보고

특징:
  - aiohttp로 비동기 처리 (블로킹 없음)
  - 모든 함수는 asyncio 코루틴

사용처:
  main.py, screener.py, executor.py (Phase 4), 텔레그램 봇 핸들러
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import aiohttp
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID


async def send(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                resp.raise_for_status()
    except Exception as e:
        print(f"[Notifier] 텔레그램 전송 실패: {e}")


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
