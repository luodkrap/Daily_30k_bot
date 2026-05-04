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
import sys
import ccxt.async_support as ccxt_async
import config
from config import BINANCE_API_KEY, BINANCE_SECRET_KEY, MODE
import persistence
from shared_state import BotState
from screener import run_screener
from executor import run_executor
from notifier import send, notify_error, init_session, close_session


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
            krw_approx = usdt * config.KRW_RATE
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


async def _supervise(
    name: str,
    coro_factory,
    state: BotState,
    max_restarts: int = 5,
    watchdog_timeout: float | None = None,
    heartbeat_attr: str | None = None,
) -> None:
    """컴포넌트 코루틴을 감시하고 예외 발생 시 재시작.

    재시작 한도(max_restarts) 초과 시 킬 이벤트를 set 하여 전체 안전 종료.

    N19 watchdog: ``watchdog_timeout`` 과 ``heartbeat_attr`` 가 주어지면
    ``getattr(state, heartbeat_attr)`` 가 ``watchdog_timeout`` 초 이상 무갱신일 때
    실행 중인 task 를 강제 cancel 하여 TimeoutError 로 변환 → 기존 재시작 경로 재사용.
    예외 없이 영원히 await 에 갇히는 silent hang(2026-04-28~05-04 사건) 대응.
    """
    import time
    import config
    restarts = 0
    while not state.kill_event.is_set():
        try:
            if watchdog_timeout and heartbeat_attr:
                # heartbeat 초기화 — 부팅 직후 stale 값으로 인한 즉시 발동 방지.
                setattr(state, heartbeat_attr, time.time())
                task = asyncio.create_task(coro_factory())
                # 폴링 주기는 watchdog_timeout/4 와 60초 중 작은 값 (반응성 vs CPU 균형).
                poll_interval = min(60.0, watchdog_timeout / 4)
                while not task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(task), timeout=poll_interval)
                        break  # task 정상 종료
                    except asyncio.TimeoutError:
                        last = getattr(state, heartbeat_attr, 0.0) or 0.0
                        idle = time.time() - last
                        if idle > watchdog_timeout:
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception):
                                pass
                            raise TimeoutError(
                                f"{name} watchdog: heartbeat {idle:.0f}s 무갱신 "
                                f"(임계 {watchdog_timeout:.0f}s) → 강제 재시작"
                            )
                # task.done() — 정상 종료 또는 내부 예외
                exc = task.exception() if not task.cancelled() else None
                if exc is not None:
                    raise exc
            else:
                await coro_factory()
            return  # 정상 종료 (자체 루프 break)
        except Exception as e:
            restarts += 1
            await notify_error(f"{name} (재시작 {restarts}/{max_restarts})", e)
            await persistence.record_event(
                config.MODE, "SUPERVISOR_RESTART",
                "CRITICAL" if restarts >= max_restarts else "WARNING",
                f"{name} 예외 재시작 {restarts}/{max_restarts}",
                {"component": name, "error": str(e), "restarts": restarts,
                 "is_watchdog": isinstance(e, TimeoutError)},
            )
            if restarts >= max_restarts:
                await send(f"[치명적] {name} 재시작 한도 초과 — 봇 종료")
                state.kill_event.set()
                return
            # executor가 죽으면 잔존 포지션 위험 → 다른 컴포넌트보다 짧은 백오프
            await asyncio.sleep(3 if name == "executor" else 5)


async def main() -> None:
    state = BotState()
    state.is_running = True
    exchange = ccxt_async.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET_KEY,
        "enableRateLimit": True,
    })
    if MODE == "testnet":
        exchange.set_sandbox_mode(True)
        # sandbox 적용 실패 시 실거래로 주문 나가는 참사 방지
        assert "testnet" in exchange.urls["api"]["public"], \
            "set_sandbox_mode 적용 실패 — testnet URL 미전환"
    state.exchange = exchange

    try:
        await init_session()
        backend_used = await persistence.init_db()
        # N22 (2026-05-04 사건 후): 부팅 시 backend 선택 결과를 journal 로 무조건 가시화.
        # 5/4 02:43 부팅 시 Supabase 일시 끊김으로 fallback 발동했으나 [DEGRADED]
        # 텔레그램 알림이 일시 NetworkError 로 누락 → 16시간 후에야 발견. journal 에
        # 흔적 남기는 것이 가장 신뢰성 높은 사후 진단 수단.
        print(f"[init_db] backend={backend_used}", flush=True)
        if backend_used == "sqlite_fallback":
            reason = persistence.get_fallback_reason() or "unknown"
            print(f"[init_db] FALLBACK reason={reason}", file=sys.stderr, flush=True)
            await send(
                f"[DEGRADED] Supabase 연결 실패 → SQLite fallback 로 기동\n"
                f"사유: {reason}\n"
                f"운영 대시보드(Supabase) 는 일시적으로 비어있으며, "
                f"로컬 {config.SQLITE_DB_PATH} 에 체결·이벤트가 기록됩니다."
            )
            await persistence.record_event(
                MODE, "DB_FALLBACK", "CRITICAL",
                f"SupabaseBackend.init 실패 — SQLite fallback",
                {"reason": reason},
            )
        await send(f"Daily 30K Bot 시작! [MODE={MODE.upper()}]")
        # 각 컴포넌트는 supervisor로 격리 — 한 개가 죽어도 나머지는 계속 동작
        # return_exceptions=True 는 supervisor 자체가 예외를 흘릴 가능성 대비 이중 안전망
        await asyncio.gather(
            _supervise("screener", lambda: run_screener(state, exchange), state),
            # N19: executor 만 watchdog 적용 (10분 무갱신 시 강제 재시작).
            # executor 메인 루프는 1초 간격으로 heartbeat 갱신하므로 600초 무갱신 = 명확한 hang.
            # recover_state 내부도 매 자산 처리 시작점에서 갱신하므로 다중 청산도 안전.
            _supervise("executor", lambda: run_executor(state, exchange), state,
                       watchdog_timeout=600.0, heartbeat_attr="executor_heartbeat"),
            _supervise("telegram", lambda: run_telegram_bot(state), state),
            return_exceptions=True,
        )
    except Exception as e:
        await notify_error("main", e)
    finally:
        # kill_event가 set되지 않았다면(예: gather가 정상 반환) 강제 set으로 정리 보장
        state.kill_event.set()
        await exchange.close()
        await close_session()
        print("[Main] 봇 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())
