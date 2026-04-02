"""
executor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  스캐너가 선정한 타겟 코인에 그리드 매매를 실행하는 트레이딩 엔진.
  GridEngine이 단일 코인의 그리드 생명주기를 관리하고,
  run_executor가 동적 스위칭·안전장치를 총괄하는 오케스트레이터.

클래스:
  - GridEngine: 그리드 배치, 체결 감지, 손절, 리그리딩
함수:
  - run_executor(): 메인 루프 (main.py에서 호출)
  - update_market_filter(): BTC 200MA 시장 필터

사용처:
  main.py → asyncio.gather(run_executor(...))
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import asyncio
import time

import config
from config import (
    GRID_COUNT, GRID_SPACING, FEE_RATE, INITIAL_BUY_RATIO,
    MIN_PROFIT_RATIO, REGRID_ENABLED,
    MAX_POSITION_RATE, STOP_LOSS_RATE,
)
# KRW_RATE, SEED, DAILY_LOSS_LIMIT 은 런타임 변경 반영을 위해 config.X 로 직접 참조
from shared_state import BotState
from notifier import send, notify_error, notify_trade, notify_daily_stop, notify_kill_switch


async def _retry_api(fn, *args, max_retries=3, **kwargs):
    """API 호출 재시도 (지수 백오프: 1s → 2s → 4s)."""
    for attempt in range(max_retries):
        try:
            return await fn(*args, **kwargs)
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)


class GridEngine:
    """단일 코인의 그리드 매매 생명주기를 관리."""

    def __init__(self, symbol: str, exchange, state: BotState):
        self.symbol = symbol
        self.exchange = exchange
        self.state = state

        self.base_price: float = 0.0
        self.qty_per_grid: float = 0.0
        self.buy_orders: dict = {}    # {order_id: {"price", "qty", "grid_level"}}
        self.sell_orders: dict = {}   # {order_id: {"price", "qty", "grid_level"}}
        self.total_invested: float = 0.0
        self.total_qty: float = 0.0
        self.avg_price: float = 0.0
        self.is_active: bool = False

    # ── LOT_SIZE / MIN_NOTIONAL 헬퍼 ─────────────────
    async def _load_market_info(self) -> None:
        """거래소 마켓 정보 로드 (미로드 시에만 실행)."""
        try:
            if not getattr(self.exchange, "markets", None):
                await _retry_api(self.exchange.load_markets)
        except Exception:
            pass  # 마켓 정보 없으면 정밀도 처리를 스킵 (fallback)

    def _round_qty(self, qty: float) -> float:
        """바이낸스 stepSize에 맞게 수량 반올림. 실패 시 원본 반환."""
        try:
            return float(self.exchange.amount_to_precision(self.symbol, qty))
        except Exception:
            return qty

    def _check_min_notional(self, qty: float, price: float) -> bool:
        """최소 주문금액(MIN_NOTIONAL) 충족 여부. 실패 시 True(안전)."""
        try:
            markets = getattr(self.exchange, "markets", {}) or {}
            market = markets.get(self.symbol, {})
            min_cost = market.get("limits", {}).get("cost", {}).get("min", 10.0)
            return qty * price >= min_cost
        except Exception:
            return True

    # ── 수수료 검증 ──────────────────────────────────
    def validate_fees(self) -> bool:
        """그리드 간격이 왕복 수수료 + 최소 수익을 초과하는지 확인."""
        net = GRID_SPACING - (FEE_RATE * 2)
        return net >= MIN_PROFIT_RATIO

    # ── 포지션 사이징 ────────────────────────────────
    def calc_position_size(self, usdt_balance: float) -> float:
        """1% Rule: 최대 투입 가능 USDT 계산."""
        seed_usdt = config.SEED / config.KRW_RATE
        max_loss_usdt = seed_usdt * MAX_POSITION_RATE
        max_invest = max_loss_usdt / STOP_LOSS_RATE
        return min(max_invest, usdt_balance)

    # ── 그리드 초기 설정 ─────────────────────────────
    async def setup_grid(self) -> None:
        """시장가 50% 매수 → 매도 그리드 5개 + 매수 그리드 5개 배치."""
        # 0. 마켓 정보 로드 (stepSize / MIN_NOTIONAL 정밀도용)
        await self._load_market_info()

        # 1. 현재가 조회
        ticker = await _retry_api(self.exchange.fetch_ticker, self.symbol)
        self.base_price = ticker["last"]

        # 2. 잔고 확인 & 포지션 사이징
        balance = await _retry_api(self.exchange.fetch_balance)
        usdt_free = balance["USDT"]["free"]
        max_invest = self.calc_position_size(usdt_free)

        # 3. 시장가 매수 (50%)
        buy_usdt = max_invest * INITIAL_BUY_RATIO
        buy_qty = self._round_qty(buy_usdt / self.base_price)

        order = await _retry_api(
            self.exchange.create_order,
            self.symbol, "market", "buy", buy_qty,
        )
        fill_price = order["average"] or self.base_price
        fill_qty = order["filled"]
        self.total_qty = fill_qty
        self.avg_price = fill_price
        self.total_invested = fill_qty * fill_price

        # 4. 매도 그리드 배치 (보유 물량 5등분, stepSize 반올림)
        sell_qty_each = self._round_qty(fill_qty / GRID_COUNT)
        for level in range(1, GRID_COUNT + 1):
            price = self.base_price * (1 + GRID_SPACING * level)
            if not self._check_min_notional(sell_qty_each, price):
                continue  # MIN_NOTIONAL 미달 레벨 스킵
            sell_order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "sell", sell_qty_each, price,
            )
            self.sell_orders[sell_order["id"]] = {
                "price": price, "qty": sell_qty_each, "grid_level": level,
            }

        # 5. 매수 그리드 배치 (나머지 50% 5등분, stepSize 반올림)
        remaining_usdt = max_invest - buy_usdt
        for level in range(1, GRID_COUNT + 1):
            price = self.base_price * (1 - GRID_SPACING * level)
            qty = self._round_qty((remaining_usdt / GRID_COUNT) / price)
            if not self._check_min_notional(qty, price):
                continue  # MIN_NOTIONAL 미달 레벨 스킵
            buy_order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "buy", qty, price,
            )
            self.buy_orders[buy_order["id"]] = {
                "price": price, "qty": qty, "grid_level": level,
            }

        self.is_active = True
        await send(
            f"[그리드] {self.symbol} 배치 완료\n"
            f"기준가: ${self.base_price:,.2f} | 보유: {self.total_qty:.4f}\n"
            f"매도 {len(self.sell_orders)}개 | 매수 {len(self.buy_orders)}개"
        )

    # ── 주문 모니터링 ────────────────────────────────
    async def monitor_orders(self) -> None:
        """1초 폴링: 미체결 목록과 비교하여 체결된 주문 감지."""
        open_orders = await _retry_api(self.exchange.fetch_open_orders, self.symbol)
        open_ids = {o["id"] for o in open_orders}

        # 폴링 시점 스냅샷 — 처리 중 새로 생성된 주문은 이번 사이클에서 제외
        buy_snapshot = list(self.buy_orders)
        sell_snapshot = list(self.sell_orders)

        # 매수 체결 감지
        for oid in buy_snapshot:
            if oid not in open_ids and oid in self.buy_orders:
                await self._handle_buy_fill(oid, self.buy_orders[oid])

        # 매도 체결 감지
        for oid in sell_snapshot:
            if oid not in open_ids and oid in self.sell_orders:
                await self._handle_sell_fill(oid, self.sell_orders[oid])

    async def _handle_buy_fill(self, order_id: str, info: dict) -> None:
        """매수 체결 → 보유량 갱신 + 위에 매도 주문."""
        del self.buy_orders[order_id]
        qty = info["qty"]
        price = info["price"]

        # 평균 매수가 갱신
        old_cost = self.avg_price * self.total_qty
        self.total_qty += qty
        self.avg_price = (old_cost + price * qty) / self.total_qty if self.total_qty > 0 else 0

        # 위에 매도 주문 (stepSize 반올림)
        sell_price = price * (1 + GRID_SPACING)
        sell_qty = self._round_qty(qty)
        if sell_qty > 0 and self._check_min_notional(sell_qty, sell_price):
            order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "sell", sell_qty, sell_price,
            )
            self.sell_orders[order["id"]] = {
                "price": sell_price, "qty": sell_qty, "grid_level": info["grid_level"],
            }

    async def _handle_sell_fill(self, order_id: str, info: dict) -> None:
        """매도 체결 → 수익 기록 + 아래에 매수 재배치."""
        del self.sell_orders[order_id]
        qty = info["qty"]
        sell_price = info["price"]

        self.total_qty -= qty

        # 수익 계산 (KRW)
        gross_usdt = (sell_price - self.avg_price) * qty
        fee_usdt = (sell_price * qty + self.avg_price * qty) * FEE_RATE
        net_usdt = gross_usdt - fee_usdt
        net_krw = net_usdt * config.KRW_RATE

        self.state.daily_pnl += net_krw
        self.state.trade_count += 1
        if net_krw > 0:
            self.state.win_count += 1
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1

        await notify_trade(self.symbol, "SELL", sell_price, net_krw)

        # 아래에 매수 재배치 (stepSize 반올림)
        buy_price = sell_price * (1 - GRID_SPACING)
        buy_qty = self._round_qty(qty)
        if buy_qty > 0 and self._check_min_notional(buy_qty, buy_price):
            order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "buy", buy_qty, buy_price,
            )
            self.buy_orders[order["id"]] = {
                "price": buy_price, "qty": buy_qty, "grid_level": info["grid_level"],
            }

    # ── 손절매 ───────────────────────────────────────
    async def check_stop_loss(self, current_price: float) -> bool:
        """현재가 < 평균매수가 × (1 - STOP_LOSS_RATE) → 전량 시장가 매도."""
        if self.total_qty <= 0 or self.avg_price <= 0:
            return False
        if current_price >= self.avg_price * (1 - STOP_LOSS_RATE):
            return False

        # 전량 시장가 매도
        await _retry_api(
            self.exchange.create_order,
            self.symbol, "market", "sell", self.total_qty,
        )
        # 손실 기록
        loss_usdt = (current_price - self.avg_price) * self.total_qty
        fee_usdt = current_price * self.total_qty * FEE_RATE
        loss_krw = (loss_usdt - fee_usdt) * config.KRW_RATE

        self.state.daily_pnl += loss_krw
        self.state.trade_count += 1
        self.state.consecutive_losses += 1

        await self.cancel_all()
        self.total_qty = 0.0
        self.is_active = False

        await send(
            f"[손절매] {self.symbol} 전량 매도 @ ${current_price:,.2f}\n"
            f"손실: {loss_krw:,.0f}원"
        )
        return True

    # ── 긴급 전량 매도 ───────────────────────────────
    async def emergency_sell(self, reason: str) -> float:
        """보유 물량 전량 시장가 매도 + PnL 기록. 킬 스위치·수익 중단·스위칭 공통."""
        if self.total_qty > 0:
            ticker = await _retry_api(self.exchange.fetch_ticker, self.symbol)
            current_price = ticker["last"]
            order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "market", "sell", self.total_qty,
            )
            fill_price = order.get("average") or current_price
            gross_usdt = (fill_price - self.avg_price) * self.total_qty
            fee_usdt = fill_price * self.total_qty * FEE_RATE
            net_usdt = gross_usdt - fee_usdt
            net_krw = net_usdt * config.KRW_RATE
            self.state.daily_pnl += net_krw
            self.state.trade_count += 1
            if net_krw > 0:
                self.state.win_count += 1
                self.state.consecutive_losses = 0
            else:
                self.state.consecutive_losses += 1
            await send(
                f"[긴급 매도] {reason} — {self.symbol} @ ${fill_price:,.2f}\n"
                f"손익: {net_krw:,.0f}원"
            )
        await self.cancel_all()
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.is_active = False
        return self.state.daily_pnl

    # ── 전 주문 취소 ─────────────────────────────────
    async def cancel_all(self) -> None:
        """미체결 주문 전부 취소."""
        for oid in list(self.buy_orders):
            try:
                await self.exchange.cancel_order(oid, self.symbol)
            except Exception:
                pass
        for oid in list(self.sell_orders):
            try:
                await self.exchange.cancel_order(oid, self.symbol)
            except Exception:
                pass
        self.buy_orders.clear()
        self.sell_orders.clear()

    # ── 리그리딩 ─────────────────────────────────────
    async def regrid(self) -> None:
        """현재가 기준으로 그리드 새로 배치. 기존 보유 물량은 먼저 시장가 매도."""
        # 기존 보유 물량 시장가 매도 (이중 포지션 방지)
        if self.total_qty > 0:
            ticker = await _retry_api(self.exchange.fetch_ticker, self.symbol)
            current_price = ticker["last"]
            await _retry_api(
                self.exchange.create_order,
                self.symbol, "market", "sell", self.total_qty,
            )
            gross_usdt = (current_price - self.avg_price) * self.total_qty
            fee_usdt = current_price * self.total_qty * FEE_RATE
            net_usdt = gross_usdt - fee_usdt
            net_krw = net_usdt * config.KRW_RATE
            self.state.daily_pnl += net_krw
            self.state.trade_count += 1
            if net_krw > 0:
                self.state.win_count += 1
                self.state.consecutive_losses = 0
            else:
                self.state.consecutive_losses += 1

        await self.cancel_all()
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.total_invested = 0.0
        self.is_active = False
        await self.setup_grid()
        await send(f"[리그리딩] {self.symbol} 새 그리드 배치 @ ${self.base_price:,.2f}")


async def update_market_filter(state: BotState, exchange) -> None:
    """BTC 200MA 필터 갱신. 30분마다 호출."""
    try:
        ohlcv = await _retry_api(exchange.fetch_ohlcv, "BTC/USDT", "1d", limit=201)
        if len(ohlcv) < 201:
            return
        closes = [c[4] for c in ohlcv]
        ma_200 = sum(closes[:-1]) / 200
        current = closes[-1]
        was_healthy = state.is_market_healthy
        state.is_market_healthy = current >= ma_200
        if was_healthy and not state.is_market_healthy:
            await send(f"[시장 필터] BTC 200MA 하회 — 신규 진입 차단\n"
                       f"BTC: ${current:,.0f} < MA200: ${ma_200:,.0f}")
    except Exception as e:
        await notify_error("MarketFilter", e)


async def update_krw_rate() -> None:
    """업비트 공개 API로 USDT/KRW 실시간 환율 갱신. 30분마다 호출."""
    import config
    try:
        import aiohttp
        url = "https://api.upbit.com/v1/ticker?markets=KRW-USDT"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        new_rate = data[0].get("trade_price")
                        if new_rate and 1000 < new_rate < 2000:
                            old_rate = config.KRW_RATE
                            config.KRW_RATE = new_rate
                            if abs(old_rate - new_rate) > 10:
                                await send(f"[환율] KRW/USDT 갱신: {old_rate:,.0f} → {new_rate:,.0f}")
    except Exception as e:
        # 환율 갱신 실패 시 기존 값 유지 (안전)
        print(f"[KRW] 환율 갱신 실패 (기존값 유지): {e}")


async def run_executor(state: BotState, exchange) -> None:
    """트레이딩 엔진 메인 루프. 안전장치 → 그리드 매매 → 1초 폴링."""
    import datetime
    engine: GridEngine | None = None
    last_ma_check: float = 0
    today: datetime.date = datetime.date.today()

    print("[Executor] 시작")
    while not state.kill_event.is_set():
        try:
            # ── 1. 킬 이벤트 재확인 ──
            if state.kill_event.is_set():
                break

            # ── 1-b. 자정 일일 리셋 ──
            now_date = datetime.date.today()
            if now_date != today:
                today = now_date
                state.reset_daily()
                await send(f"[리셋] {today} 일일 집계 초기화")

            # ── 2. 일일 손실 한도 초과 → 킬 스위치 ──
            if state.daily_pnl <= -config.DAILY_LOSS_LIMIT:
                await notify_kill_switch()
                if engine:
                    await engine.emergency_sell("일일 손실 한도 초과")
                state.kill_event.set()
                break

            # ── 3. 일일 목표 수익 달성 → 하드 스탑 ──
            if state.should_stop_profit:
                reason = "목표 수익 달성" if state.daily_pnl >= 0 else "조기 중단 (시장 악화)"
                await notify_daily_stop(reason, state.daily_pnl)
                if engine:
                    await engine.emergency_sell(reason)
                state.kill_event.set()
                break

            # ── 4. 200MA 체크 + 환율 갱신 (30분마다) ──
            now = time.time()
            if now - last_ma_check > 1800:
                await update_market_filter(state, exchange)
                await update_krw_rate()
                last_ma_check = now

            # ── 5. 타겟 코인 없으면 대기 ──
            if not state.target_coin:
                await asyncio.sleep(1)
                continue

            # ── 6. 동적 코인 스위칭 ──
            if engine and engine.symbol != state.target_coin:
                await send(f"[스위칭] {engine.symbol} → {state.target_coin}")
                await engine.emergency_sell(f"코인 스위칭 → {state.target_coin}")
                engine = None

            # ── 7. 시장 악화 시 신규 진입 차단 ──
            if engine is None and not state.is_market_healthy:
                await asyncio.sleep(1)
                continue

            # ── 8. 엔진 생성 & 그리드 셋업 ──
            if engine is None:
                engine = GridEngine(state.target_coin, exchange, state)
                if not engine.validate_fees():
                    await send("[Executor] 수수료 검증 실패 — 그리드 간격 부족")
                    engine = None
                    await asyncio.sleep(60)
                    continue
                await engine.setup_grid()

            # ── 9. 손절 체크 ──
            ticker = await _retry_api(exchange.fetch_ticker, engine.symbol)
            current_price = ticker["last"]
            if await engine.check_stop_loss(current_price):
                engine = None
                continue

            # ── 10. 주문 체결 감지 ──
            await engine.monitor_orders()

            # ── 11. 리그리딩 체크 ──
            if engine.is_active and engine.total_qty <= 0 and not engine.sell_orders:
                if REGRID_ENABLED:
                    await engine.regrid()
                else:
                    engine = None

        except Exception as e:
            await notify_error("Executor", e)

        await asyncio.sleep(1)

    # 종료 정리
    if engine:
        try:
            await engine.emergency_sell("봇 종료")
        except Exception:
            pass
    print("[Executor] 종료")
