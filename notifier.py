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
