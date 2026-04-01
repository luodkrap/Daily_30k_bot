"""
main.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  Daily 30K 봇의 진입점.
  3개 컴포넌트(스캐너, 엔진, 텔레그램 봇)를 asyncio.gather()로 동시 실행.
  킬 이벤트 하나로 모든 루프를 즉시 중단시키는 마스터 컨트롤러.

3개 코루틴:
  1. run_screener(): 매시간 전 종목 스캔 → state.target_coin 업데이트
  2. run_executor(): 스캐너가 지정한 코인의 그리드 매매 실행 (Phase 4 구현)
  3. run_telegram_bot(): /status, /stop, /seed 명령어 처리

특징:
  - BINANCE_API_KEY, SECRET_KEY로 바이낸스 비동기 exchange 초기화
  - state = BotState() 단일 인스턴스로 3개 컴포넌트가 상태 공유
  - Exception 시 notify_error로 즉시 텔레그램 보고
  - finally에서 exchange.close() 정리

실행:
  python main.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import ccxt.async_support as ccxt_async
from config import BINANCE_API_KEY, BINANCE_SECRET_KEY
from shared_state import BotState
from screener import run_screener
from notifier import send, notify_error, init_session, close_session


async def run_executor(state: BotState, exchange: ccxt_async.binance) -> None:
    """트레이딩 엔진 — Phase 4에서 구현 예정."""
    print("[Executor] 시작 (뼈대)")
    while not state.kill_event.is_set():
        try:
            if state.should_stop_profit:
                from notifier import notify_daily_stop
                reason = "목표 수익 달성" if state.daily_pnl >= 0 else "시장 악화"
                await notify_daily_stop(reason, state.daily_pnl)
                state.kill_event.set()
                break
            # TODO Phase 4: 그리드 매매 로직
        except Exception as e:
            await notify_error("Executor", e)
        await asyncio.sleep(5)
    print("[Executor] 종료")


async def run_telegram_bot(state: BotState) -> None:
    """텔레그램 봇 — /status, /stop, /seed 처리."""
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes
    from config import TELEGRAM_TOKEN

    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from notifier import notify_status
        await notify_status(state)

    async def stop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from notifier import notify_kill_switch
        await notify_kill_switch()
        state.kill_event.set()
        await update.message.reply_text("킬 스위치 발동. 봇을 중단합니다.")

    async def seed_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        import config
        from dotenv import set_key
        from pathlib import Path

        if not ctx.args:
            await update.message.reply_text(
                f"현재 시드: {config.SEED:,}원\n"
                f"변경하려면: /seed 5000000"
            )
            return

        try:
            new_seed = int(ctx.args[0])
        except ValueError:
            await update.message.reply_text("숫자를 입력해주세요. 예: /seed 5000000")
            return

        if new_seed < 100_000:
            await update.message.reply_text("시드는 최소 100,000원 이상이어야 합니다.")
            return

        # 바이낸스 실제 잔고와 비교해서 경고
        try:
            balance = await state.exchange.fetch_balance()
            usdt = balance.get("USDT", {}).get("free", 0)
            krw_approx = usdt * 1350  # 대략적인 환율
            if new_seed > krw_approx * 1.1:
                await update.message.reply_text(
                    f"경고: 설정 시드({new_seed:,}원)가 "
                    f"바이낸스 잔고 추정치({krw_approx:,.0f}원)보다 큽니다.\n"
                    f"그래도 변경하려면 /seed {new_seed} confirm"
                )
                if not (len(ctx.args) > 1 and ctx.args[1] == "confirm"):
                    return
        except Exception:
            pass  # 잔고 조회 실패해도 변경은 허용

        old_seed = config.SEED
        env_path = Path(__file__).parent / ".env"
        set_key(str(env_path), "SEED", str(new_seed))

        # 런타임에서 config 모듈 수치 갱신
        config.SEED = new_seed
        config.DAILY_TARGET     = new_seed * 0.010
        config.DAILY_MIN_PROFIT = new_seed * 0.005
        config.DAILY_LOSS_LIMIT = new_seed * 0.030

        await update.message.reply_text(
            f"시드 변경 완료.\n"
            f"이전: {old_seed:,}원 → 신규: {new_seed:,}원\n"
            f"목표: {config.DAILY_TARGET:,.0f}원 / "
            f"조기중단: {config.DAILY_MIN_PROFIT:,.0f}원 / "
            f"킬스위치: {config.DAILY_LOSS_LIMIT:,.0f}원"
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("seed", seed_cmd))
    app.bot_data["state"] = state

    print("[Telegram] 시작")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    await state.kill_event.wait()  # 킬 신호 올 때까지 대기

    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    print("[Telegram] 종료")


async def main() -> None:
    state = BotState()
    state.is_running = True
    exchange = ccxt_async.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET_KEY,
        "enableRateLimit": True,
    })
    state.exchange = exchange

    try:
        await init_session()
        await send("Daily 30K Bot 시작!")
        await asyncio.gather(
            run_screener(state, exchange),
            run_executor(state, exchange),
            run_telegram_bot(state),
        )
    except Exception as e:
        await notify_error("main", e)
    finally:
        await exchange.close()
        await close_session()
        print("[Main] 봇 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())
