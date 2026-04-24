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
    RECENT_LOSS_STREAK,
)
# KRW_RATE, SEED, DAILY_LOSS_LIMIT 은 런타임 변경 반영을 위해 config.X 로 직접 참조
from shared_state import BotState
from notifier import send, notify_error, notify_trade, notify_daily_stop, notify_kill_switch
import persistence


# binance create_order rate limit: 50 orders / 10s. recover_state 가 다중 자산
# (특히 testnet 사전 잔고) 정리 시 429 폭주를 막기 위한 매도 간 throttle.
RECOVER_SELL_THROTTLE_SEC = 0.3


async def _log_trade(symbol: str, side: str, qty: float, price: float,
                     fee: float, pnl: float) -> None:
    """체결 1건을 DB 에 비동기 기록. persistence 가 실패 격리를 내장 (N2)."""
    await persistence.record_trade(
        symbol, side, qty, price, fee, pnl, config.MODE,
    )


async def _log_event(event_type: str, severity: str, message: str,
                     context: dict | None = None) -> None:
    """봇 이벤트 1건을 DB 에 비동기 기록. persistence 가 실패 격리를 내장 (N2)."""
    await persistence.record_event(
        config.MODE, event_type, severity, message, context,
    )


async def snapshot_equity(exchange, state: BotState) -> None:
    """현재 잔고 + 포지션 평가액으로 equity snapshot 1건 기록.

    USDT 잔고는 cash, 비-USDT 자산은 현재가 × 수량으로 position_value 로 환산.
    realized_pnl 은 state.daily_pnl(원) 을 KRW_RATE 로 USDT 환산한 값.
    unrealized_pnl 은 엔진 외부에서 평균매수가를 알 수 없어 0 으로 기록."""
    try:
        balance = await _retry_api(exchange.fetch_balance)
        totals = balance.get("total") or {}
        cash = float(totals.get("USDT", 0.0) or 0.0)

        markets = getattr(exchange, "markets", {}) or {}
        position_value = 0.0
        for currency, amount in totals.items():
            if currency == "USDT" or not amount or amount <= 0:
                continue
            symbol = f"{currency}/USDT"
            if symbol not in markets:
                continue
            try:
                ticker = await _retry_api(exchange.fetch_ticker, symbol)
                price = ticker.get("last") or 0.0
                if price > 0:
                    position_value += float(amount) * float(price)
            except Exception:
                continue

        equity = cash + position_value
        realized_usdt = (state.daily_pnl / config.KRW_RATE
                         if config.KRW_RATE > 0 else 0.0)
        await persistence.record_equity_snapshot(
            mode=config.MODE, equity_usdt=equity, cash_usdt=cash,
            position_value_usdt=position_value,
            realized_pnl=realized_usdt, unrealized_pnl=0.0,
        )
    except Exception as e:
        await notify_error("persistence.equity_snapshot", e)


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

    # ── 공통 헬퍼 ─────────────────────────────────────
    def _calc_fee(self, price: float, qty: float) -> float:
        """수수료 계산 (USDT). price × qty × FEE_RATE."""
        return price * qty * FEE_RATE

    async def _get_current_price(self) -> float:
        """현재가 조회. fetch_ticker 래퍼."""
        ticker = await _retry_api(self.exchange.fetch_ticker, self.symbol)
        return ticker["last"]

    async def _record_trade(self, sell_price: float, qty: float) -> float:
        """매도 PnL 기록 + 승/패 카운터 갱신 + trades.db 로그. 반환: net_krw."""
        sell_fee_usdt = self._calc_fee(sell_price, qty)
        gross_usdt = (sell_price - self.avg_price) * qty
        net_usdt = gross_usdt - sell_fee_usdt
        net_krw = net_usdt * config.KRW_RATE

        self.state.daily_pnl += net_krw
        self.state.trade_count += 1
        if net_krw > 0:
            self.state.win_count += 1
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1
            check_loss_streak(self.state)

        await _log_trade(self.symbol, "SELL", qty, sell_price,
                         sell_fee_usdt, net_krw)
        return net_krw

    # ── 지정가 초기 매수 (미체결 시 재시도) ────────────
    async def _limit_buy_with_retry(self, buy_usdt: float,
                                     max_attempts: int = 3,
                                     timeout: int = 15) -> tuple[float, float]:
        """현재가 기준 지정가 매수. 미체결 시 가격 재조정 후 재시도.
        Returns: (fill_price, fill_qty). 실패 시 (0.0, 0.0)."""
        for attempt in range(max_attempts):
            if attempt > 0:
                self.base_price = await self._get_current_price()

            buy_price = self.base_price
            buy_qty = self._round_qty(buy_usdt / buy_price)

            order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "buy", buy_qty, buy_price,
            )

            # 즉시 체결 (현재가 지정가 → taker). filled=0 은 체결로 간주하지 않음.
            if order.get("status") == "closed" and (order.get("filled") or 0) > 0:
                return (order.get("average") or buy_price,
                        order.get("filled") or buy_qty)

            # 미체결 대기 — fetch_order 로 status/filled 를 직접 확인
            order_id = order["id"]
            external_cancel = False
            for _ in range(timeout):
                await asyncio.sleep(1)
                try:
                    fetched = await _retry_api(
                        self.exchange.fetch_order, order_id, self.symbol,
                    )
                except Exception:
                    continue

                status = fetched.get("status")
                filled = fetched.get("filled") or 0.0
                avg = fetched.get("average") or buy_price

                if status == "closed":
                    if filled > 0:
                        return (avg, filled)
                    # closed 인데 filled=0 → 취소로 처리하고 재시도
                    external_cancel = True
                    break
                if status == "canceled":
                    external_cancel = True
                    break
                # status == "open" / "partial" 등은 계속 대기

            # 타임아웃 또는 외부 취소 → 정리 후 재시도
            if not external_cancel:
                try:
                    await self.exchange.cancel_order(order_id, self.symbol)
                except Exception:
                    pass
            if attempt < max_attempts - 1:
                await send(
                    f"[그리드] 초기 매수 미체결 — 가격 재조정 "
                    f"({attempt + 1}/{max_attempts})"
                )

        return (0.0, 0.0)

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
        """지정가 50% 매수 → 매도 그리드 5개 + 매수 그리드 5개 배치."""
        # 0. 마켓 정보 로드 (stepSize / MIN_NOTIONAL 정밀도용)
        await self._load_market_info()

        # 1. 현재가 조회
        self.base_price = await self._get_current_price()

        # 2. 잔고 확인 & 포지션 사이징
        balance = await _retry_api(self.exchange.fetch_balance)
        usdt_free = balance["USDT"]["free"]
        max_invest = self.calc_position_size(usdt_free)

        # 3. 지정가 매수 (50%) — CLAUDE.md "지정가 우선" 원칙
        buy_usdt = max_invest * INITIAL_BUY_RATIO
        fill_price, fill_qty = await self._limit_buy_with_retry(buy_usdt)
        if fill_qty <= 0:
            await send(f"[그리드] {self.symbol} 초기 매수 실패 — 그리드 미배치")
            return
        self.total_qty = fill_qty
        self.avg_price = fill_price
        self.total_invested = fill_qty * fill_price

        # 초기 지정가 매수 수수료 즉시 PnL 반영 (양방향 수수료 일관성)
        buy_fee_usdt = self._calc_fee(fill_price, fill_qty)
        buy_fee_krw = buy_fee_usdt * config.KRW_RATE
        self.state.daily_pnl -= buy_fee_krw
        await _log_trade(self.symbol, "BUY", fill_qty, fill_price,
                         buy_fee_usdt, -buy_fee_krw)

        # 4. 매도 그리드 배치 (보유 물량 5등분, stepSize 반올림)
        # 마지막 레벨은 fill_qty - 기배치합계 잔량 사용 → Σsell_qty ≤ total_qty 보장
        # (반올림 누적으로 총합이 보유량을 초과해 insufficient balance가 나던 B3 결함 방지)
        sell_qty_each = self._round_qty(fill_qty / GRID_COUNT)
        placed_sell = 0.0
        for level in range(1, GRID_COUNT + 1):
            price = self.base_price * (1 + GRID_SPACING * level)
            qty = (self._round_qty(fill_qty - placed_sell)
                   if level == GRID_COUNT else sell_qty_each)
            if qty <= 0 or not self._check_min_notional(qty, price):
                continue  # MIN_NOTIONAL 미달·잔량 소진 레벨 스킵
            sell_order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "sell", qty, price,
            )
            self.sell_orders[sell_order["id"]] = {
                "price": price, "qty": qty, "grid_level": level,
            }
            placed_sell += qty

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

        # 매수 수수료 즉시 PnL 반영 (매도 시점에는 매도 수수료만 차감하기 위함)
        buy_fee_usdt = self._calc_fee(price, qty)
        buy_fee_krw = buy_fee_usdt * config.KRW_RATE
        self.state.daily_pnl -= buy_fee_krw
        await _log_trade(self.symbol, "BUY", qty, price,
                         buy_fee_usdt, -buy_fee_krw)

        # 위에 매도 주문 (stepSize 반올림, 보유량 초과 방지 상한 적용)
        sell_price = price * (1 + GRID_SPACING)
        placed_sell = sum(o["qty"] for o in self.sell_orders.values())
        available = self.total_qty - placed_sell
        sell_qty = self._round_qty(min(qty, available)) if available > 0 else 0.0
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

        # 수익 계산 (KRW). 매수 수수료는 _handle_buy_fill / setup_grid에서 이미 차감됨.
        net_krw = await self._record_trade(sell_price, qty)
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
        # 손실 기록 (매수 수수료는 매수 체결 시점에 이미 차감됨 → 매도 수수료만 반영)
        loss_krw = await self._record_trade(current_price, self.total_qty)

        await self.cancel_all()
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.total_invested = 0.0
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
            current_price = await self._get_current_price()
            order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "market", "sell", self.total_qty,
            )
            fill_price = order.get("average") or current_price
            net_krw = await self._record_trade(fill_price, self.total_qty)
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
            current_price = await self._get_current_price()
            await _retry_api(
                self.exchange.create_order,
                self.symbol, "market", "sell", self.total_qty,
            )
            await self._record_trade(current_price, self.total_qty)

        await self.cancel_all()
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.total_invested = 0.0
        self.is_active = False
        await self.setup_grid()
        await send(f"[리그리딩] {self.symbol} 새 그리드 배치 @ ${self.base_price:,.2f}")


async def update_market_filter(state: BotState, exchange) -> None:
    """BTC 200MA + 연속 손실 필터 갱신. 30분마다 호출."""
    try:
        ohlcv = await _retry_api(exchange.fetch_ohlcv, "BTC/USDT", "1d", limit=201)
        if len(ohlcv) < 201:
            return
        closes = [c[4] for c in ohlcv]
        ma_200 = sum(closes[:-1]) / 200
        current = closes[-1]
        ma_healthy = current >= ma_200

        was_healthy = state.is_market_healthy
        state.is_market_healthy = ma_healthy
        if was_healthy != ma_healthy:
            if was_healthy and not ma_healthy:
                await send(f"[시장 필터] BTC 200MA 하회 — 신규 진입 차단\n"
                           f"BTC: ${current:,.0f} < MA200: ${ma_200:,.0f}")
            await _log_event(
                "MARKET_FILTER",
                "WARNING" if not ma_healthy else "INFO",
                f"BTC 200MA {'하회' if not ma_healthy else '회복'}",
                {"btc": current, "ma200": ma_200, "healthy": ma_healthy},
            )
    except Exception as e:
        await notify_error("MarketFilter", e)


async def recover_state(exchange) -> dict:
    """재시작 시 이전 세션 잔존물(미체결 주문 + 비-USDT 포지션) 정리.

    Clean slate 방식: 이전 그리드 상태를 복원하지 않고 전량 정리 후 스캐너가
    재선정하도록 위임. 디스크 영속화 없이 이중 포지션 위험을 제거.

    정리 대상:
      - 모든 심볼의 미체결 주문 → cancel
      - USDT·BNB·주요 스테이블코인 외 free 잔고 → {CUR}/USDT 시장가 매도
      - MIN_NOTIONAL 미달(dust) 또는 USDT 페어 없는 자산 → 스킵

    Returns: {"canceled": int, "liquidated": list[str], "skipped": list[str]}
    """
    # 0. 마켓 정보 로드 (MIN_NOTIONAL·stepSize 확인용)
    try:
        if not getattr(exchange, "markets", None):
            await _retry_api(exchange.load_markets)
    except Exception:
        pass

    markets = getattr(exchange, "markets", {}) or {}
    result = {"canceled": 0, "liquidated": [], "skipped": []}

    # 1. 미체결 주문 전부 취소
    try:
        open_orders = await _retry_api(exchange.fetch_open_orders)
    except Exception as e:
        await notify_error("Recover.fetch_open_orders", e)
        open_orders = []

    for order in open_orders:
        try:
            await exchange.cancel_order(order["id"], order["symbol"])
            result["canceled"] += 1
        except Exception:
            continue

    # 2. 잔고 조회 — 실패 시 복구 중단 (안전: 무엇을 들고 있는지 모르면 거래 금지)
    try:
        balance = await _retry_api(exchange.fetch_balance)
    except Exception as e:
        await notify_error("Recover.fetch_balance", e)
        await send("[상태 복구] 실패 — 잔고 조회 불가. 수동 점검 필요.")
        raise

    # 3. 비-스테이블/비-BNB 자산을 USDT로 매도
    SKIP_CURRENCIES = {"USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD", "BNB"}
    free_map = balance.get("free") or {}

    for currency, free_amount in free_map.items():
        if currency in SKIP_CURRENCIES:
            continue
        if not free_amount or free_amount <= 0:
            continue

        symbol = f"{currency}/USDT"
        if symbol not in markets:
            result["skipped"].append(f"{currency}={free_amount:.6f} (pair없음)")
            continue

        try:
            ticker = await _retry_api(exchange.fetch_ticker, symbol)
            price = ticker.get("last") or 0.0
            if price <= 0:
                result["skipped"].append(f"{currency}={free_amount:.6f} (가격없음)")
                continue

            min_cost = (markets[symbol].get("limits", {})
                        .get("cost", {}).get("min", 10.0))
            if free_amount * price < min_cost:
                result["skipped"].append(f"{currency}={free_amount:.6f} (dust)")
                continue

            try:
                sell_qty = float(exchange.amount_to_precision(symbol, free_amount))
            except Exception:
                sell_qty = free_amount
            if sell_qty <= 0:
                continue

            order = await _retry_api(
                exchange.create_order, symbol, "market", "sell", sell_qty,
            )
            fill_price = order.get("average") or price
            result["liquidated"].append(
                f"{currency} {sell_qty:.6f}@${fill_price:,.4f}"
            )
            # N5: 청산 거래도 trades 테이블에 기록 (수수료/손익은 산출 불가 → 0)
            await _log_trade(symbol, "SELL", sell_qty, fill_price, 0.0, 0.0)
            # N5b: 다중 자산 청산 시 binance 50 orders/10s 제한 회피
            await asyncio.sleep(RECOVER_SELL_THROTTLE_SEC)
        except Exception as e:
            await notify_error(f"Recover.sell.{currency}", e)
            # 실패한 create_order 도 rate window 에 잡히므로 동일하게 throttle
            await asyncio.sleep(RECOVER_SELL_THROTTLE_SEC)

    # 4. 결과 보고
    lines = ["[상태 복구] 재시작 정리 완료",
             f"취소된 주문: {result['canceled']}건"]
    if result["liquidated"]:
        lines.append(f"청산된 포지션: {len(result['liquidated'])}개")
        for item in result["liquidated"]:
            lines.append(f"  - {item}")
    else:
        lines.append("청산된 포지션: 없음")
    if result["skipped"]:
        lines.append(f"스킵: {', '.join(result['skipped'])}")
    await send("\n".join(lines))
    await _log_event(
        "RECOVER_STATE", "INFO",
        f"재시작 정리 완료 — 취소 {result['canceled']}, 청산 {len(result['liquidated'])}",
        {"canceled": result["canceled"],
         "liquidated": result["liquidated"],
         "skipped": result["skipped"]},
    )
    return result


def check_loss_streak(state: BotState) -> None:
    """연속 손실 RECENT_LOSS_STREAK회 도달 시 시장 악화 판정.
    매도 체결·손절·긴급매도 직후 호출. is_market_healthy=False면 should_stop_profit이
    DAILY_MIN_PROFIT 기준으로 조기 중단을 트리거할 수 있게 해줌."""
    if state.consecutive_losses >= RECENT_LOSS_STREAK and state.is_market_healthy:
        state.is_market_healthy = False


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

    await _log_event("EXECUTOR_START", "INFO",
                     f"executor 시작 MODE={config.MODE}")

    # 재시작 상태 복구 (C2) — 이전 세션 잔존 주문·포지션 정리
    try:
        await recover_state(exchange)
    except Exception as e:
        await notify_error("Executor.recover_state", e)
        await _log_event("RECOVER_STATE_FAILED", "CRITICAL",
                         f"recover_state 실패 — 봇 종료: {e}")
        state.kill_event.set()
        return

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
                await _log_event(
                    "KILL_SWITCH", "CRITICAL",
                    "일일 손실 한도 초과",
                    {"daily_pnl_krw": state.daily_pnl,
                     "limit_krw": config.DAILY_LOSS_LIMIT},
                )
                if engine:
                    await engine.emergency_sell("일일 손실 한도 초과")
                state.kill_event.set()
                break

            # ── 3. 일일 목표 수익 달성 → 하드 스탑 ──
            if state.should_stop_profit:
                reason = "목표 수익 달성" if state.daily_pnl >= 0 else "조기 중단 (시장 악화)"
                await notify_daily_stop(reason, state.daily_pnl)
                await _log_event(
                    "DAILY_STOP", "INFO", reason,
                    {"daily_pnl_krw": state.daily_pnl},
                )
                if engine:
                    await engine.emergency_sell(reason)
                state.kill_event.set()
                break

            # ── 4. 200MA 체크 + 환율 갱신 + equity snapshot (30분마다) ──
            now = time.time()
            if now - last_ma_check > 1800:
                await update_market_filter(state, exchange)
                await update_krw_rate()
                await snapshot_equity(exchange, state)
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
                if not engine.is_active:
                    engine = None
                    await asyncio.sleep(60)
                    continue

            # ── 9. 손절 체크 ──
            current_price = await engine._get_current_price()
            if await engine.check_stop_loss(current_price):
                engine = None
                continue

            # ── 10. 주문 체결 감지 ──
            await engine.monitor_orders()

            # ── 11. 리그리딩 체크 ──
            # buy_orders 미체결 잔존 시 regrid 실행하면 이중 포지션 위험 → 모든 주문 비어있을 때만
            if (engine.is_active
                    and engine.total_qty <= 0
                    and not engine.sell_orders
                    and not engine.buy_orders):
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
