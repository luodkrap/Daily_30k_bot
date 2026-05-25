import os
import asyncio
import ccxt.async_support as ccxt_async
from dotenv import load_dotenv

load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ─────────────────────────────────────────────────────────
# Phase 3 단위 테스트 (오프라인 — API 호출 없음)
# ─────────────────────────────────────────────────────────

def _make_ohlcv(prices: list[float], volumes: list[float] = None) -> list:
    """테스트용 OHLCV mock 데이터 생성 (high=close*1.005, low=close*0.995)."""
    if volumes is None:
        volumes = [1_000_000.0] * len(prices)
    return [
        [i * 3600000, p * 0.995, p * 1.005, p * 0.995, p, v]
        for i, (p, v) in enumerate(zip(prices, volumes))
    ]


def test_calc_atr():
    from screener import _calc_atr

    # 15개 캔들, 모두 같은 가격 → TR ≈ 0, ATR ≈ 0
    ohlcv = _make_ohlcv([100.0] * 15)
    atr = _calc_atr(ohlcv)
    assert atr < 0.01 * 100, f"평탄 캔들 ATR 오류: {atr}"

    # 가격 변동이 있는 캔들 → ATR > 0
    prices = [100 + i % 3 for i in range(15)]  # 100, 101, 102 반복
    ohlcv2 = _make_ohlcv(prices)
    atr2 = _calc_atr(ohlcv2)
    assert atr2 > 0, f"변동 캔들 ATR이 0: {atr2}"

    print(f"  [PASS] _calc_atr: 평탄={atr:.4f}, 변동={atr2:.4f}")


def test_is_pumped():
    from screener import _is_pumped

    # 시나리오 A: 정상 (급등 없음) → False
    prices = [100.0] * 15
    ohlcv_normal = _make_ohlcv(prices)
    assert _is_pumped(ohlcv_normal) is False, "정상 케이스에서 True 반환"

    # 시나리오 B: 최근 3h 8% 급등 → True
    prices_pump3h = [100.0] * 11 + [101.0, 102.0, 107.0, 109.0]
    # high를 급등 가격으로 조정
    ohlcv_pump3h = _make_ohlcv(prices_pump3h)
    for i in range(-3, 0):
        ohlcv_pump3h[i][2] = prices_pump3h[i] * 1.05  # high를 더 높게
    assert _is_pumped(ohlcv_pump3h) is True, "3h 급등 케이스에서 False 반환"

    # 시나리오 C: 거래량 스파이크 6배 → True
    volumes_spike = [1_000_000.0] * 14 + [6_000_000.0]
    ohlcv_vol = _make_ohlcv([100.0] * 15, volumes_spike)
    assert _is_pumped(ohlcv_vol) is True, "거래량 스파이크 케이스에서 False 반환"

    print("  [PASS] _is_pumped: 정상/3h급등/거래량스파이크 3가지 케이스")


def test_pre_filter():
    from screener import _pre_filter

    mock_tickers = {
        "BTC/USDT":    {"quoteVolume": 500_000_000, "last": 50000},  # 통과
        "ETH/USDT":    {"quoteVolume": 300_000_000, "last": 2000},   # 통과
        "USDC/USDT":   {"quoteVolume": 200_000_000, "last": 1.0},    # 스테이블 → 제외
        "ETHUP/USDT":  {"quoteVolume": 200_000_000, "last": 5.0},    # 레버리지 → 제외
        "XRP/BTC":     {"quoteVolume": 200_000_000, "last": 0.5},    # USDT 아님 → 제외
        "DOGE/USDT":   {"quoteVolume": 5_000_000,   "last": 0.1},    # 거래량 미달 → 제외
        "SHIB/USDT":   {"quoteVolume": 150_000_000, "last": None},   # 가격 없음 → 제외
        "NIGHT/USDT":  {"quoteVolume": 200_000_000, "last": 0.05},   # 저가 코인 → 제외
    }
    result = _pre_filter(mock_tickers)
    assert "BTC/USDT" in result, "BTC/USDT가 필터에서 제외됨"
    assert "ETH/USDT" in result, "ETH/USDT가 필터에서 제외됨"
    assert "USDC/USDT" not in result, "스테이블코인이 통과됨"
    assert "ETHUP/USDT" not in result, "레버리지 토큰이 통과됨"
    assert "XRP/BTC" not in result, "비USDT 페어가 통과됨"
    assert "DOGE/USDT" not in result, "거래량 미달 코인이 통과됨"
    assert "SHIB/USDT" not in result, "가격 없는 코인이 통과됨"
    assert "NIGHT/USDT" not in result, "저가 코인($0.05)이 통과됨"
    print(f"  [PASS] _pre_filter: {len(result)}개 통과 ({result})")


# ─────────────────────────────────────────────────────────
# Phase 4 단위 테스트 (오프라인 — MockExchange)
# ─────────────────────────────────────────────────────────

class MockExchange:
    """ccxt async exchange 모의 객체. Phase 4 테스트용."""

    def __init__(self, ticker_price=100.0, usdt_balance=2222.0):
        self._order_id = 0
        self._orders = {}
        self._ticker_price = ticker_price
        self._usdt_balance = usdt_balance
        self._open_order_ids = set()

    async def fetch_ticker(self, symbol):
        return {"last": self._ticker_price}

    async def fetch_balance(self):
        # ccxt 호환: 통화별 dict + free/used/total 집계 맵을 함께 제공
        free = {"USDT": self._usdt_balance}
        used = {"USDT": 0.0}
        total = {"USDT": self._usdt_balance}
        per_currency = {
            "USDT": {"free": self._usdt_balance, "used": 0.0, "total": self._usdt_balance},
        }
        return {**per_currency, "free": free, "used": used, "total": total}

    async def create_order(self, symbol, type_, side, amount, price=None):
        self._order_id += 1
        oid = str(self._order_id)
        fill_price = price if price else self._ticker_price
        # Limit order at/crossing current price fills immediately (taker)
        if type_ == "market":
            is_filled = True
        elif (type_ == "limit" and side == "buy"
              and price is not None and price >= self._ticker_price):
            is_filled = True
        elif (type_ == "limit" and side == "sell"
              and price is not None and price <= self._ticker_price):
            is_filled = True
        else:
            is_filled = False
        # 미체결(open) 주문은 filled=0 — 실제 거래소 동작과 일치시켜
        # 외부 취소 시 fetch_order 가 filled=0 을 반환하도록 (Codex F3 회귀 방지).
        order = {
            "id": oid,
            "symbol": symbol,
            "type": type_,
            "side": side,
            "amount": amount,
            "price": price,
            "filled": amount if is_filled else 0.0,
            "average": fill_price if is_filled else None,
            "status": "closed" if is_filled else "open",
        }
        self._orders[oid] = order
        if order["status"] == "open":
            self._open_order_ids.add(oid)
        return order

    async def fetch_open_orders(self, symbol=None):
        orders = [self._orders[oid] for oid in self._open_order_ids if oid in self._orders]
        if symbol is None:
            return orders
        return [o for o in orders if o.get("symbol") == symbol]

    async def fetch_order(self, order_id, symbol):
        return self._orders[order_id]

    async def cancel_order(self, order_id, symbol):
        if order_id in self._orders:
            self._orders[order_id]["status"] = "canceled"
            self._open_order_ids.discard(order_id)

    async def fetch_ohlcv(self, symbol, timeframe, limit=None):
        return [[i, 99, 101, 99, self._ticker_price, 1_000_000] for i in range(limit or 201)]

    def simulate_fill(self, order_id):
        """테스트 헬퍼: 지정가 주문을 체결 상태로 변경 (filled = amount)."""
        if order_id in self._orders:
            order = self._orders[order_id]
            order["status"] = "closed"
            order["filled"] = order["amount"]
            if order.get("average") is None:
                order["average"] = order.get("price") or self._ticker_price
            self._open_order_ids.discard(order_id)


def test_validate_fees():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange()
    engine = GridEngine("ETH/USDT", ex, state)

    # 기본 설정: GRID_SPACING=0.5%, FEE_RATE=0.1% → 순수익 0.3% > 0.1% → True
    assert engine.validate_fees() is True, "기본 설정에서 수수료 검증 실패"
    print("  [PASS] validate_fees: 기본 설정 통과")


def test_calc_position_size():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange()
    engine = GridEngine("ETH/USDT", ex, state)

    # SEED=3,000,000 KRW, KRW_RATE=1350 → seed_usdt=$2222
    # max_loss = $2222 * 0.01 = $22.22
    # max_invest = $22.22 / 0.02 = $1111
    size = engine.calc_position_size(usdt_balance=5000.0)
    assert 1100 < size < 1120, f"포지션 사이징 오류: {size}"

    # 잔고가 부족한 경우 잔고로 제한
    size_low = engine.calc_position_size(usdt_balance=500.0)
    assert size_low == 500.0, f"잔고 제한 실패: {size_low}"

    print(f"  [PASS] calc_position_size: 정상={size:.2f}, 잔고제한={size_low:.2f}")


def test_setup_grid():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_setup_grid_async(engine, ex))


async def _test_setup_grid_async(engine, ex):
    await engine.setup_grid()

    # 1. 그리드 활성화
    assert engine.is_active is True, "그리드 미활성"

    # 2. 초기 지정가 매수 실행됨 (보유량 > 0)
    assert engine.total_qty > 0, f"초기 매수 실패: qty={engine.total_qty}"

    # 3. 매도 주문 5개 배치
    assert len(engine.sell_orders) == 5, f"매도 주문 수: {len(engine.sell_orders)}"

    # 4. 매수 주문 5개 배치
    assert len(engine.buy_orders) == 5, f"매수 주문 수: {len(engine.buy_orders)}"

    # 5. 매도 가격 확인: base_price 위로 올라감
    for info in engine.sell_orders.values():
        assert info["price"] > engine.base_price, f"매도 가격이 기준가 이하: {info['price']}"

    # 6. 매수 가격 확인: base_price 아래
    for info in engine.buy_orders.values():
        assert info["price"] < engine.base_price, f"매수 가격이 기준가 이상: {info['price']}"

    print(f"  [PASS] setup_grid: qty={engine.total_qty:.4f}, "
          f"매도={len(engine.sell_orders)}개, 매수={len(engine.buy_orders)}개")


def test_handle_buy_fill():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_handle_buy_fill_async(engine, ex, state))


async def _test_handle_buy_fill_async(engine, ex, state):
    await engine.setup_grid()
    sell_count_before = len(engine.sell_orders)

    # 매수 주문 하나를 체결 시뮬레이션
    buy_oid = list(engine.buy_orders.keys())[0]
    buy_info = engine.buy_orders[buy_oid]
    ex.simulate_fill(buy_oid)

    await engine.monitor_orders()

    # 매수 체결 → 해당 주문 제거 + 새 매도 주문 생성
    assert buy_oid not in engine.buy_orders, "체결된 매수 주문이 남아있음"
    assert len(engine.sell_orders) == sell_count_before + 1, "대응 매도 주문 미생성"
    print("  [PASS] handle_buy_fill: 매수 체결 → 매도 주문 생성")


def test_handle_sell_fill():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_handle_sell_fill_async(engine, ex, state))


async def _test_handle_sell_fill_async(engine, ex, state):
    await engine.setup_grid()
    buy_count_before = len(engine.buy_orders)

    # 매도 주문 하나를 체결 시뮬레이션
    sell_oid = list(engine.sell_orders.keys())[0]
    ex.simulate_fill(sell_oid)

    await engine.monitor_orders()

    # 매도 체결 → 해당 주문 제거 + 새 매수 주문 생성 + PnL 기록
    assert sell_oid not in engine.sell_orders, "체결된 매도 주문이 남아있음"
    assert len(engine.buy_orders) == buy_count_before + 1, "대응 매수 주문 미생성"
    assert state.trade_count == 1, f"거래 횟수: {state.trade_count}"
    assert state.daily_pnl != 0.0, "PnL 미기록"
    print(f"  [PASS] handle_sell_fill: 매도 체결 → PnL={state.daily_pnl:,.0f}원, 매수 재배치")


def test_stop_loss():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_stop_loss_async(engine, ex, state))


async def _test_stop_loss_async(engine, ex, state):
    from executor import GridEngine
    from shared_state import BotState

    await engine.setup_grid()
    assert engine.is_active is True

    # 2% 하락 시 손절 발동
    triggered = await engine.check_stop_loss(current_price=97.9)
    assert triggered is True, "손절 미발동"
    assert engine.is_active is False, "그리드 미비활성"
    assert state.daily_pnl < 0, f"손실 미기록: {state.daily_pnl}"
    assert len(engine.buy_orders) == 0, "미체결 매수 주문 잔존"
    assert len(engine.sell_orders) == 0, "미체결 매도 주문 잔존"

    # 정상 범위에서는 미발동
    state2 = BotState()
    ex2 = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine2 = GridEngine("ETH/USDT", ex2, state2)
    await engine2.setup_grid()
    not_triggered = await engine2.check_stop_loss(current_price=99.0)
    assert not_triggered is False, "정상 가격에서 손절 발동"

    print("  [PASS] stop_loss: 2% 하락 발동, 정상가 미발동")


def test_market_filter():
    from executor import update_market_filter
    from shared_state import BotState

    asyncio.run(_test_market_filter_async())


async def _test_market_filter_async():
    from executor import update_market_filter
    from shared_state import BotState

    state = BotState()

    # 시나리오 A: 현재가($100) >= 200MA → healthy
    ex_healthy = MockExchange(ticker_price=100.0)
    await update_market_filter(state, ex_healthy)
    assert state.is_market_healthy is True, "정상 시장에서 악화 판정"

    # MockExchange는 모든 캔들 close=ticker_price 반환
    # 201개 캔들 전부 close=100이므로 MA200=100, current=100 → healthy
    print("  [PASS] market_filter: 정상 시장 healthy 판정")


def test_regrid():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_regrid_async(engine, ex))


async def _test_regrid_async(engine, ex):
    await engine.setup_grid()
    old_base = engine.base_price

    # 가격 상승 시뮬레이션
    ex._ticker_price = 110.0
    ex._usdt_balance = 5000.0  # 매도 후 자금 회수 가정

    await engine.regrid()

    # 새 기준가가 업데이트됨
    assert engine.base_price == 110.0, f"기준가 미갱신: {engine.base_price}"
    assert engine.is_active is True, "리그리딩 후 비활성"
    assert len(engine.sell_orders) == 5, f"매도 주문: {len(engine.sell_orders)}"
    assert len(engine.buy_orders) == 5, f"매수 주문: {len(engine.buy_orders)}"

    print(f"  [PASS] regrid: 기준가 {old_base} → {engine.base_price}")


def test_run_executor_kill():
    from executor import run_executor
    from shared_state import BotState

    asyncio.run(_test_run_executor_kill_async())


async def _test_run_executor_kill_async():
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    state.target_coin = "ETH/USDT"

    # 2초 후 킬 스위치 발동
    async def trigger_kill():
        await asyncio.sleep(2)
        state.kill_event.set()

    # run_executor와 킬 트리거 동시 실행
    from executor import run_executor
    await asyncio.gather(
        run_executor(state, ex),
        trigger_kill(),
    )

    assert state.kill_event.is_set(), "킬 이벤트 미설정"
    print("  [PASS] run_executor: 킬 스위치 정상 종료")


# ─────────────────────────────────────────────────────────
# 버그픽스 단위 테스트 (오프라인)
# ─────────────────────────────────────────────────────────

class MockExchangeWithPrecision(MockExchange):
    """stepSize=0.01, min_notional=$10 환경 시뮬레이션 (A2 테스트용)."""

    @property
    def markets(self):
        return {
            "ETH/USDT": {
                "limits": {
                    "amount": {"min": 0.01},
                    "cost": {"min": 10.0},
                },
                "precision": {"amount": 2},
            }
        }

    async def load_markets(self):
        return self.markets

    def amount_to_precision(self, symbol, amount):
        return round(float(amount), 2)

    def price_to_precision(self, symbol, price):
        return round(float(price), 2)


# ── A1: import 바인딩 버그 ────────────────────────────────

def test_a1_krw_rate_runtime_change():
    """A1: config.KRW_RATE 런타임 변경이 손익 계산에 반영되어야 한다."""
    import config
    original_rate = config.KRW_RATE
    try:
        config.KRW_RATE = 2700  # 기존 1350의 2배
        asyncio.run(_test_a1_krw_rate_async())
    finally:
        config.KRW_RATE = original_rate


async def _test_a1_krw_rate_async():
    import config
    from executor import GridEngine  # 이미 기본값으로 로드된 캐시 사용
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    await engine.setup_grid()

    # A8 이후: setup_grid에서 매수 수수료가 즉시 차감됨 → 스냅샷 후 매도 변화량으로 비교
    pnl_after_setup = state.daily_pnl
    avg_price_before_sell = engine.avg_price

    sell_oid = list(engine.sell_orders.keys())[0]
    sell_info = engine.sell_orders[sell_oid]
    sell_price = sell_info["price"]
    sell_qty = sell_info["qty"]
    ex.simulate_fill(sell_oid)
    await engine.monitor_orders()

    # 매도 1회 변화량: (sell - avg) * qty - sell_fee
    gross_usdt = (sell_price - avg_price_before_sell) * sell_qty
    sell_fee_usdt = sell_price * sell_qty * 0.001
    net_usdt = gross_usdt - sell_fee_usdt
    expected_delta_krw = net_usdt * 2700  # config.KRW_RATE = 2700 반영 기대
    actual_delta = state.daily_pnl - pnl_after_setup

    assert abs(actual_delta - expected_delta_krw) < 0.1, (
        f"KRW_RATE 런타임 변경 미반영: "
        f"expected delta {expected_delta_krw:.2f}원 (rate=2700), "
        f"got {actual_delta:.2f}원"
    )
    print(f"  [PASS] a1_krw_rate_runtime_change: 매도 Δ={actual_delta:.2f}원 (rate=2700 반영)")


def test_a1_seed_runtime_change():
    """A1: config.SEED 런타임 변경이 포지션 사이징에 반영되어야 한다."""
    import config
    original_seed = config.SEED
    try:
        config.SEED = 6_000_000  # 기존 3,000,000의 2배
        from executor import GridEngine
        from shared_state import BotState
        state = BotState()
        ex = MockExchange()
        engine = GridEngine("ETH/USDT", ex, state)

        # SEED=6,000,000, KRW_RATE=1350 → seed_usdt=4444
        # max_invest = (4444 * 0.01) / 0.02 = 2222
        size = engine.calc_position_size(usdt_balance=5000.0)
        assert 2200 < size < 2240, (
            f"SEED 런타임 변경 미반영: expected ~2222, got {size:.2f}"
        )
        print(f"  [PASS] a1_seed_runtime_change: max_invest={size:.2f} (SEED=6,000,000 반영)")
    finally:
        config.SEED = original_seed


# ── A2: LOT_SIZE / MIN_NOTIONAL ──────────────────────────

def test_a2_lot_size_precision():
    """A2: 주문 수량이 바이낸스 stepSize에 맞게 반올림되어야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchangeWithPrecision(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_a2_lot_size_async(engine, ex))


async def _test_a2_lot_size_async(engine, ex):
    await engine.setup_grid()

    step = 0.01  # MockExchangeWithPrecision precision=2

    for oid, info in engine.sell_orders.items():
        qty = info["qty"]
        assert abs(qty - round(qty, 2)) < 1e-9, (
            f"sell 수량 stepSize 미준수: {qty}"
        )
        notional = qty * info["price"]
        assert notional >= 10.0, f"sell MIN_NOTIONAL 미달: {notional:.4f}"

    for oid, info in engine.buy_orders.items():
        qty = info["qty"]
        assert abs(qty - round(qty, 2)) < 1e-9, (
            f"buy 수량 stepSize 미준수: {qty}"
        )
        notional = qty * info["price"]
        assert notional >= 10.0, f"buy MIN_NOTIONAL 미달: {notional:.4f}"

    print("  [PASS] a2_lot_size: stepSize 준수, MIN_NOTIONAL 충족")


# ── A3: regrid 이중 포지션 버그 ──────────────────────────

def test_a3_regrid_sells_existing_position():
    """A3: regrid() 시 기존 보유 물량을 먼저 시장가 매도해야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_a3_regrid_async(engine, ex, state))


async def _test_a3_regrid_async(engine, ex, state):
    await engine.setup_grid()
    qty_before = engine.total_qty
    assert qty_before > 0, "그리드 설정 후 보유량 없음"

    order_id_before = ex._order_id
    ex._ticker_price = 110.0
    ex._usdt_balance = 5000.0

    await engine.regrid()

    # regrid 과정에서 기존 물량에 대한 시장가 매도 주문이 발생해야 함
    new_market_sells = [
        o for o in ex._orders.values()
        if o["type"] == "market" and o["side"] == "sell"
        and int(o["id"]) > order_id_before
    ]
    assert len(new_market_sells) >= 1, (
        "regrid() 시 기존 보유 물량 시장가 매도 없음 — 이중 포지션 위험"
    )
    assert engine.is_active is True, "regrid 후 그리드 미활성"
    print(f"  [PASS] a3_regrid_sells_existing: qty={qty_before:.4f} 매도 후 재배치")


# ── A4: 긴급 매도 PnL 미기록 ─────────────────────────────

def test_a4_emergency_sell_records_pnl():
    """A4: emergency_sell() 이 PnL을 state.daily_pnl에 기록해야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_a4_emergency_sell_async(engine, ex, state))


async def _test_a4_emergency_sell_async(engine, ex, state):
    await engine.setup_grid()
    assert engine.total_qty > 0

    pnl_before = state.daily_pnl
    ex._ticker_price = 101.0  # 약간 상승 (손익 발생)

    await engine.emergency_sell("킬 스위치 테스트")

    assert engine.total_qty == 0, "긴급 매도 후 보유량 잔존"
    assert engine.is_active is False, "긴급 매도 후 그리드 활성 상태"
    assert state.daily_pnl != pnl_before, "긴급 매도 PnL 미기록"
    assert len(engine.buy_orders) == 0, "긴급 매도 후 매수 주문 잔존"
    assert len(engine.sell_orders) == 0, "긴급 매도 후 매도 주문 잔존"
    print(f"  [PASS] a4_emergency_sell: PnL={state.daily_pnl:,.0f}원 기록됨")


# ── A5: 일일 PnL 자정 리셋 ───────────────────────────────

def test_a5_daily_reset():
    """A5: BotState.reset_daily() 가 일일 집계 수치를 초기화해야 한다."""
    from shared_state import BotState

    state = BotState()
    state.daily_pnl = 25000.0
    state.trade_count = 7
    state.win_count = 5
    state.consecutive_losses = 2

    state.reset_daily()

    assert state.daily_pnl == 0.0, f"daily_pnl 미초기화: {state.daily_pnl}"
    assert state.trade_count == 0, f"trade_count 미초기화: {state.trade_count}"
    assert state.win_count == 0, f"win_count 미초기화: {state.win_count}"
    assert state.consecutive_losses == 0, f"consecutive_losses 미초기화: {state.consecutive_losses}"
    print("  [PASS] a5_daily_reset: 일일 집계 수치 초기화 완료")


# ── A8: 수수료 이중 차감 정리 ────────────────────────────

def test_a8_setup_grid_buy_fee_deduction():
    """A8: setup_grid 초기 시장가 매수 직후 매수 수수료가 PnL에 즉시 반영돼야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_a8_setup_grid_async(engine, state))


async def _test_a8_setup_grid_async(engine, state):
    import config as cfg
    from config import FEE_RATE

    await engine.setup_grid()

    # 그리드 매수/매도는 모두 미체결(open) 상태이므로 PnL에는 영향이 없고,
    # 초기 시장가 매수 수수료만 차감된 상태여야 한다.
    expected_fee_krw = engine.avg_price * engine.total_qty * FEE_RATE * cfg.KRW_RATE
    assert abs(state.daily_pnl + expected_fee_krw) < 0.01, (
        f"매수 수수료 미반영: 예상 {-expected_fee_krw:.4f}, 실제 {state.daily_pnl:.4f}"
    )
    print(f"  [PASS] a8_setup_grid: 초기 매수 수수료 {-state.daily_pnl:,.2f}원 즉시 차감")


def test_a8_grid_rotation_pnl_accuracy():
    """A8: 그리드 10회 회전 시 누적 PnL이 이론값과 ±1% 이내로 일치해야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_a8_grid_rotation_async(engine, state))


async def _test_a8_grid_rotation_async(engine, state):
    import config as cfg
    from config import FEE_RATE, GRID_SPACING

    BUY_PRICE = 100.0
    QTY = 1.0
    SELL_PRICE = BUY_PRICE * (1 + GRID_SPACING)
    ROTATIONS = 10

    engine.is_active = True
    engine.base_price = BUY_PRICE

    for i in range(ROTATIONS):
        # 잔존 주문 정리 후 매수 1개 → 매도 1개를 직접 호출로 시뮬레이션
        engine.buy_orders.clear()
        engine.sell_orders.clear()

        oid_buy = f"buy_{i}"
        info_buy = {"price": BUY_PRICE, "qty": QTY, "grid_level": 1}
        engine.buy_orders[oid_buy] = info_buy
        await engine._handle_buy_fill(oid_buy, info_buy)

        # _handle_buy_fill이 새 매도 주문을 생성 → 그것을 체결시킨다
        sell_oid = next(iter(engine.sell_orders))
        sell_info = engine.sell_orders[sell_oid]
        await engine._handle_sell_fill(sell_oid, sell_info)

    # 회전 1회 이론 PnL (USDT)
    buy_fee = BUY_PRICE * QTY * FEE_RATE
    sell_fee = SELL_PRICE * QTY * FEE_RATE
    grid_profit = (SELL_PRICE - BUY_PRICE) * QTY
    expected_per_rotation_usdt = grid_profit - buy_fee - sell_fee
    expected_total_krw = expected_per_rotation_usdt * ROTATIONS * cfg.KRW_RATE

    diff = abs(state.daily_pnl - expected_total_krw)
    tolerance = abs(expected_total_krw) * 0.01
    assert diff <= tolerance, (
        f"10회 회전 PnL 오차 초과: 예상 {expected_total_krw:.2f}원, "
        f"실제 {state.daily_pnl:.2f}원, 차이 {diff:.2f}원"
    )
    assert state.trade_count == ROTATIONS, f"trade_count 불일치: {state.trade_count}"
    print(f"  [PASS] a8_grid_rotation: 10회 회전 PnL={state.daily_pnl:,.2f}원 "
          f"(이론 {expected_total_krw:,.2f}원, 오차 {diff:.4f}원)")


# ── C1: 초기 매수 지정가 전환 ────────────────────────────

def test_c1_setup_grid_uses_limit_buy():
    """C1: setup_grid() 초기 매수가 지정가(limit) 주문이어야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_c1_limit_buy_async(engine, ex))


async def _test_c1_limit_buy_async(engine, ex):
    await engine.setup_grid()

    # 첫 번째 주문이 limit buy여야 한다 (시장가 아님)
    first_order = ex._orders["1"]
    assert first_order["type"] == "limit", (
        f"초기 매수가 시장가 주문: type={first_order['type']}"
    )
    assert first_order["side"] == "buy", (
        f"초기 주문이 매수가 아님: side={first_order['side']}"
    )
    assert first_order["price"] is not None, "지정가 주문에 가격 미설정"
    assert engine.is_active is True, "그리드 미활성"
    print("  [PASS] c1_setup_grid_limit_buy: 초기 매수 → limit 주문 확인")


# ── C2: 재시작 시 상태 복구 ──────────────────────────────

class MockExchangeRecovery(MockExchange):
    """재시작 상태 복구 테스트용 — 다중 통화 잔고 + 다중 심볼 markets 지원."""

    def __init__(self, balances: dict | None = None,
                 tickers: dict | None = None,
                 pre_open_orders: list | None = None):
        super().__init__()
        self._balances = balances or {"USDT": 1000.0}
        self._tickers = tickers or {}
        # 사전 주입된 미체결 주문 (cancel 대상)
        for o in pre_open_orders or []:
            self._order_id += 1
            oid = str(self._order_id)
            order = {**o, "id": oid, "status": "open",
                     "filled": 0.0, "average": o.get("price")}
            self._orders[oid] = order
            self._open_order_ids.add(oid)

    @property
    def markets(self):
        # 잔고에 등장하는 통화의 /USDT 페어 + 티커에 명시된 심볼을 마켓으로 등록
        symbols = set()
        for cur in self._balances:
            if cur != "USDT":
                symbols.add(f"{cur}/USDT")
        symbols.update(self._tickers.keys())
        return {
            s: {"limits": {"amount": {"min": 0.0001},
                           "cost": {"min": 10.0}},
                "precision": {"amount": 6}}
            for s in symbols
        }

    async def load_markets(self):
        return self.markets

    def amount_to_precision(self, symbol, amount):
        return round(float(amount), 6)

    async def fetch_balance(self):
        per_currency = {
            cur: {"free": amt, "used": 0.0, "total": amt}
            for cur, amt in self._balances.items()
        }
        free = dict(self._balances)
        used = {cur: 0.0 for cur in self._balances}
        total = dict(self._balances)
        return {**per_currency, "free": free, "used": used, "total": total}

    async def fetch_ticker(self, symbol):
        if symbol in self._tickers:
            return {"last": self._tickers[symbol]}
        return {"last": 0.0}  # 모르는 심볼 → 가격 없음


def test_c2_recover_cancels_open_orders():
    """C2: 재시작 시 모든 미체결 주문이 취소돼야 한다."""
    from executor import recover_state

    pre_orders = [
        {"symbol": "ETH/USDT", "type": "limit", "side": "buy",
         "amount": 1.0, "price": 90.0},
        {"symbol": "ETH/USDT", "type": "limit", "side": "sell",
         "amount": 1.0, "price": 110.0},
        {"symbol": "BTC/USDT", "type": "limit", "side": "buy",
         "amount": 0.01, "price": 50000.0},
    ]
    ex = MockExchangeRecovery(
        balances={"USDT": 1000.0},
        pre_open_orders=pre_orders,
    )
    result = asyncio.run(recover_state(ex))

    assert result["canceled"] == 3, f"취소된 주문 수 오류: {result['canceled']}"
    assert len(ex._open_order_ids) == 0, "미체결 주문 잔존"
    print(f"  [PASS] c2_recover_cancels_open_orders: {result['canceled']}건 취소")


def test_c2_recover_liquidates_non_usdt_positions():
    """C2: 재시작 시 비-USDT 포지션이 시장가 매도돼야 한다."""
    from executor import recover_state

    ex = MockExchangeRecovery(
        balances={"USDT": 500.0, "ETH": 0.5, "BTC": 0.01},
        tickers={"ETH/USDT": 2000.0, "BTC/USDT": 50000.0},
    )
    order_id_before = ex._order_id
    result = asyncio.run(recover_state(ex))

    # ETH 0.5 * $2000 = $1000, BTC 0.01 * $50000 = $500 → 둘 다 MIN_NOTIONAL 초과
    assert len(result["liquidated"]) == 2, (
        f"청산된 포지션 수 오류: {result['liquidated']}"
    )

    # 시장가 매도 주문이 실제로 발행됐는지 확인
    new_market_sells = [
        o for o in ex._orders.values()
        if o["type"] == "market" and o["side"] == "sell"
        and int(o["id"]) > order_id_before
    ]
    symbols_sold = {o["symbol"] for o in new_market_sells}
    assert "ETH/USDT" in symbols_sold and "BTC/USDT" in symbols_sold, (
        f"예상 심볼 매도 누락: {symbols_sold}"
    )
    print(f"  [PASS] c2_recover_liquidates: {len(new_market_sells)}건 시장가 매도")


def test_c2_recover_skips_stablecoins_and_bnb():
    """C2: USDT·BNB·주요 스테이블코인 잔고는 매도 대상에서 제외돼야 한다."""
    from executor import recover_state

    ex = MockExchangeRecovery(
        balances={
            "USDT": 500.0, "USDC": 200.0, "BUSD": 100.0,
            "BNB": 2.0,  # $600 상당이라도 수수료용이므로 스킵
            "FDUSD": 50.0, "DAI": 30.0, "TUSD": 20.0,
        },
        tickers={"BNB/USDT": 300.0},  # BNB 가격 있어도 스킵돼야 함
    )
    order_id_before = ex._order_id
    result = asyncio.run(recover_state(ex))

    assert result["liquidated"] == [], (
        f"스테이블/BNB가 청산됨: {result['liquidated']}"
    )
    new_sells = [
        o for o in ex._orders.values()
        if o["type"] == "market" and int(o["id"]) > order_id_before
    ]
    assert new_sells == [], f"예상치 못한 매도 발생: {new_sells}"
    print("  [PASS] c2_recover_skips_stablecoins_bnb: 시장가 매도 0건")


def test_c2_recover_skips_dust():
    """C2: MIN_NOTIONAL 미달 잔고(dust)는 스킵돼야 한다."""
    from executor import recover_state

    # ETH 0.001 * $2000 = $2 → MIN_NOTIONAL($10) 미달 → 스킵
    # BTC 없고, DOGE 0.5 * $0.1 = $0.05 → dust
    # SOL 0.2 * $100 = $20 → MIN_NOTIONAL 초과 → 청산
    ex = MockExchangeRecovery(
        balances={"USDT": 500.0, "ETH": 0.001, "DOGE": 0.5, "SOL": 0.2},
        tickers={"ETH/USDT": 2000.0, "DOGE/USDT": 0.1, "SOL/USDT": 100.0},
    )
    result = asyncio.run(recover_state(ex))

    liquidated_currencies = [item.split()[0] for item in result["liquidated"]]
    assert liquidated_currencies == ["SOL"], (
        f"dust 필터링 실패: liquidated={result['liquidated']}, "
        f"skipped={result['skipped']}"
    )
    # ETH·DOGE는 skipped 목록에 dust 사유로 들어가야 함
    skipped_str = " ".join(result["skipped"])
    assert "ETH" in skipped_str and "DOGE" in skipped_str, (
        f"dust 자산이 skipped에 누락: {result['skipped']}"
    )
    print(f"  [PASS] c2_recover_skips_dust: SOL만 청산, "
          f"ETH/DOGE는 dust로 스킵")


# ── B1: 외부 취소를 체결로 오인하는 결함 ─────────────────

def test_b1_external_cancel_not_counted_as_fill():
    """B1: 지정가 매수 주문이 외부에서 취소되면 (0.0, 0.0)을 반환해야 한다.
    open_orders 목록 누락을 체결로 판단하던 기존 로직의 회귀 테스트."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_b1_external_cancel_async(engine, ex))


async def _test_b1_external_cancel_async(engine, ex):
    # 지정가 매수가 open 상태로 남도록 base_price를 ticker 아래로 설정
    engine.base_price = 99.0

    async def external_cancel():
        await asyncio.sleep(1.2)
        # 현재 open 상태인 주문을 외부에서 취소
        for oid in list(ex._open_order_ids):
            await ex.cancel_order(oid, "ETH/USDT")

    # 1회 시도, 3초 타임아웃으로 외부 취소 → 실패 반환 기대
    retry_task = asyncio.create_task(
        engine._limit_buy_with_retry(buy_usdt=100.0, max_attempts=1, timeout=3)
    )
    cancel_task = asyncio.create_task(external_cancel())
    fill_price, fill_qty = await retry_task
    await cancel_task

    assert (fill_price, fill_qty) == (0.0, 0.0), (
        f"외부 취소 주문이 체결로 오인됨: price={fill_price}, qty={fill_qty}"
    )
    print("  [PASS] b1_external_cancel: 외부 취소 주문 체결 오인 없음 → (0.0, 0.0)")


# ── B3: 매도 수량 총합이 보유량 초과 방지 ────────────────

def test_b3_setup_grid_sell_qty_within_holdings():
    """B3: setup_grid 배치 후 Σsell_qty ≤ total_qty 이어야 한다.

    stepSize 반올림이 올림으로 일어나는 케이스(fill_qty=0.13, step=0.01)에서
    기존 코드는 5 × round(0.13/5, 2) = 5 × 0.03 = 0.15 > 0.13 으로
    insufficient balance 를 유발했다.
    """
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    # usdt_free=26 → calc_position_size 가 26 반환 → buy_usdt=13 → fill_qty=0.13
    ex = MockExchangeWithPrecision(ticker_price=100.0, usdt_balance=26.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_b3_setup_grid_async(engine))


async def _test_b3_setup_grid_async(engine):
    await engine.setup_grid()

    assert engine.is_active, "그리드 미활성"
    assert engine.total_qty > 0, "초기 매수 실패"

    total_sell_qty = sum(o["qty"] for o in engine.sell_orders.values())
    assert total_sell_qty <= engine.total_qty + 1e-9, (
        f"Σsell_qty={total_sell_qty} > total_qty={engine.total_qty} "
        f"(insufficient balance 발생 가능)"
    )
    print(f"  [PASS] b3_setup_grid_sell_qty: Σsell={total_sell_qty}, "
          f"total={engine.total_qty} (≤ 보장)")


def test_b3_handle_buy_fill_caps_sell_qty():
    """B3: _handle_buy_fill 은 남은 가용량(total_qty - Σ기배치)을 상한으로 매도해야 한다."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchangeWithPrecision(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_b3_handle_buy_fill_async(engine, ex))


async def _test_b3_handle_buy_fill_async(engine, ex):
    # 인위적으로 기배치 매도량이 total_qty 와 근접하게 세팅
    await engine._load_market_info()
    engine.total_qty = 1.00
    engine.avg_price = 100.0
    # 기배치 매도 합 0.99 → 가용량 0.01 만 남음
    engine.sell_orders = {
        "s1": {"price": 101.0, "qty": 0.50, "grid_level": 1},
        "s2": {"price": 102.0, "qty": 0.49, "grid_level": 2},
    }

    # 매수 0.05 체결 → 원래라면 0.05 매도 주문 생성하려 하지만,
    # total_qty=1.05, 기배치=0.99 → 가용 0.06 이지만 min(qty=0.05, 0.06)=0.05 여야 함
    buy_info = {"price": 99.0, "qty": 0.05, "grid_level": 1}
    engine.buy_orders["b1"] = buy_info
    await engine._handle_buy_fill("b1", buy_info)

    total_sell = sum(o["qty"] for o in engine.sell_orders.values())
    assert total_sell <= engine.total_qty + 1e-9, (
        f"Σsell_qty={total_sell} > total_qty={engine.total_qty}"
    )

    # 이번엔 가용량이 매수량보다 적은 케이스 — 상한에 걸려야 함
    engine.sell_orders = {
        "s1": {"price": 101.0, "qty": 0.98, "grid_level": 1},
    }
    engine.total_qty = 1.00
    buy_info2 = {"price": 99.0, "qty": 0.10, "grid_level": 2}
    engine.buy_orders["b2"] = buy_info2
    await engine._handle_buy_fill("b2", buy_info2)

    total_sell2 = sum(o["qty"] for o in engine.sell_orders.values())
    assert total_sell2 <= engine.total_qty + 1e-9, (
        f"매수 초과분이 매도로 반영됨: Σ={total_sell2}, total={engine.total_qty}"
    )
    # total_qty=1.10, 기배치=0.98 → 가용 0.12, min(0.10, 0.12)=0.10 → OK
    # 또는 total_qty=1.10, 이전 s1=0.98 + 새로 0.10 = 1.08 ≤ 1.10
    print(f"  [PASS] b3_handle_buy_fill_caps: 상한 적용 후 "
          f"Σsell={total_sell2} ≤ total_qty={engine.total_qty}")


# ── H2: 텔레그램 플러드 방지 ─────────────────────────────

def test_h2_dedup_suppresses_duplicate():
    """H2: 동일 메시지가 60초 이내에 반복되면 한 번만 전송돼야 한다."""
    import notifier
    asyncio.run(_test_h2_dedup_async())


async def _test_h2_dedup_async():
    import notifier
    notifier._reset_flood_state()
    # 간격 스로틀은 본 테스트 목적이 아니므로 최소화
    orig_interval = notifier._MIN_SEND_INTERVAL_SEC
    notifier._MIN_SEND_INTERVAL_SEC = 0.0

    delivered = []

    async def fake_deliver(text):
        delivered.append(text)

    orig_deliver = notifier._deliver
    notifier._deliver = fake_deliver
    try:
        await notifier.send("동일 메시지")
        await notifier.send("동일 메시지")  # 중복 → 억제
        await notifier.send("다른 메시지")
        await notifier.send("동일 메시지")  # 여전히 윈도우 내 → 억제
    finally:
        notifier._deliver = orig_deliver
        notifier._MIN_SEND_INTERVAL_SEC = orig_interval
        notifier._reset_flood_state()

    assert delivered == ["동일 메시지", "다른 메시지"], (
        f"중복 억제 실패: 실제 발송={delivered}"
    )
    print("  [PASS] h2_dedup: 60s 윈도우 내 동일 메시지 1회만 발송")


def test_h2_min_interval_enforced():
    """H2: 서로 다른 메시지라도 전체 발송 최소 간격이 지켜져야 한다."""
    import notifier
    asyncio.run(_test_h2_min_interval_async())


async def _test_h2_min_interval_async():
    import time
    import notifier
    notifier._reset_flood_state()
    # 테스트 속도를 위해 간격을 축소 (비율 검증은 동일)
    orig_interval = notifier._MIN_SEND_INTERVAL_SEC
    notifier._MIN_SEND_INTERVAL_SEC = 0.2

    send_ts: list[float] = []

    async def fake_deliver(text):
        send_ts.append(time.monotonic())

    orig_deliver = notifier._deliver
    notifier._deliver = fake_deliver
    try:
        await notifier.send("A")
        await notifier.send("B")
        await notifier.send("C")
    finally:
        notifier._deliver = orig_deliver
        notifier._MIN_SEND_INTERVAL_SEC = orig_interval
        notifier._reset_flood_state()

    assert len(send_ts) == 3, f"3회 발송 기대, 실제 {len(send_ts)}"
    for i in range(1, len(send_ts)):
        gap = send_ts[i] - send_ts[i - 1]
        assert gap >= 0.19, f"발송 간격 부족: {gap:.3f}s (최소 0.2s)"
    print(f"  [PASS] h2_min_interval: 3회 발송 최소 간격 유지 "
          f"(간격 {[round(send_ts[i]-send_ts[i-1], 3) for i in range(1, 3)]}s)")


# ── B5: stability_score 후보군 min-max 정규화 ─────────────

def test_b5_stability_score_minmax_normalized():
    """B5: CV 절대 임계값(0.05) 제거 후 후보군 상대 순위로 stability 점수가 차등되는지.

    구 공식은 CV > 5% 코인을 모두 0점으로 clamp → ATR 필터 통과 코인 대부분이
    동점이 되어 가중치 20% 가 사실상 낭비. 새 공식은 후보군 내 min-max 정규화.
    """
    from screener import _score_and_rank

    # 세 코인 모두 CV > 5% (구 공식이면 stability=0 동점)
    #   A: CV 6%, B: CV 12%, C: CV 20%
    prices_a = [100 + (6 if i % 2 == 0 else -6) for i in range(30)]
    prices_b = [100 + (12 if i % 2 == 0 else -12) for i in range(30)]
    prices_c = [100 + (20 if i % 2 == 0 else -20) for i in range(30)]

    passed = []
    for sym, prices in [("A/USDT", prices_a), ("B/USDT", prices_b), ("C/USDT", prices_c)]:
        passed.append({
            "symbol":   sym,
            "atr_rate": 0.0275,        # 중앙값 → atr_score=1.0 (모두 동점)
            "volume":   1_000_000.0,   # 동일 → vol_score=0 (모두 동점)
            "last":     100.0,
            "ohlcv":    _make_ohlcv(prices),
        })

    ranked = _score_and_rank(passed)
    scores = {c["symbol"]: c["score"] for c in ranked}

    assert scores["A/USDT"] > scores["B/USDT"] > scores["C/USDT"], \
        f"min-max 정규화 실패: {scores}"

    # A 는 stability=1.0 → 0.5 + 0 + 0.2 = 0.7
    # C 는 stability=0.0 → 0.5 + 0 + 0   = 0.5
    assert abs(scores["A/USDT"] - 0.7) < 1e-9, f"A score={scores['A/USDT']}"
    assert abs(scores["C/USDT"] - 0.5) < 1e-9, f"C score={scores['C/USDT']}"
    assert 0.5 < scores["B/USDT"] < 0.7, f"B score={scores['B/USDT']}"

    print(f"  [PASS] b5_stability_minmax: A={scores['A/USDT']:.3f} > "
          f"B={scores['B/USDT']:.3f} > C={scores['C/USDT']:.3f}")


# ─────────────────────────────────────────────────────────
# Phase 6: MODE 분기 + SQLite 영속화
# ─────────────────────────────────────────────────────────

def test_mode_branch_live():
    """MODE=live 시 실거래 API 키 env 를 읽는지."""
    import importlib
    import sys
    with _patched_env({
        "MODE": "live",
        "BINANCE_API_KEY": "LIVE_KEY",
        "BINANCE_SECRET_KEY": "LIVE_SECRET",
        "BINANCE_TESTNET_API_KEY": "TESTNET_KEY",
        "BINANCE_TESTNET_SECRET_KEY": "TESTNET_SECRET",
    }):
        sys.modules.pop("config", None)
        cfg = importlib.import_module("config")
        assert cfg.MODE == "live"
        assert cfg.BINANCE_API_KEY == "LIVE_KEY"
        assert cfg.BINANCE_SECRET_KEY == "LIVE_SECRET"
    print("  [PASS] mode_branch_live: 실거래 키 로드")


def test_mode_branch_testnet():
    """MODE=testnet 시 testnet API 키 env 를 읽는지 (실거래 키와 분리)."""
    import importlib
    import sys
    with _patched_env({
        "MODE": "testnet",
        "BINANCE_API_KEY": "LIVE_KEY",
        "BINANCE_SECRET_KEY": "LIVE_SECRET",
        "BINANCE_TESTNET_API_KEY": "TESTNET_KEY",
        "BINANCE_TESTNET_SECRET_KEY": "TESTNET_SECRET",
    }):
        sys.modules.pop("config", None)
        cfg = importlib.import_module("config")
        assert cfg.MODE == "testnet"
        assert cfg.BINANCE_API_KEY == "TESTNET_KEY", \
            "testnet 모드에서 실거래 키가 로드됨"
        assert cfg.BINANCE_SECRET_KEY == "TESTNET_SECRET"
    print("  [PASS] mode_branch_testnet: testnet 키 로드 + 실거래 키 격리")


def test_mode_branch_invalid():
    """MODE 값이 live/testnet/paper 외면 부팅 시 즉시 실패해야 한다."""
    import importlib
    import sys
    with _patched_env({"MODE": "demo"}):
        sys.modules.pop("config", None)
        try:
            importlib.import_module("config")
        except AssertionError:
            print("  [PASS] mode_branch_invalid: 잘못된 MODE 거부")
            return
    raise AssertionError("MODE=demo 허용됨 (AssertionError 기대)")


def _patched_env(overrides: dict):
    """환경변수 임시 덮어쓰기 컨텍스트 매니저."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        saved = {k: os.environ.get(k) for k in overrides}
        os.environ.update({k: v for k, v in overrides.items() if v is not None})
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _ctx()


def test_persistence_init_and_roundtrip():
    """SqliteBackend 왕복: init → record_trade → load_trades (mode 필터)."""
    import tempfile
    import os as _os
    from persistence import SqliteBackend

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _os.path.join(tmp, "trades.db")
            be = SqliteBackend(path=db_path)
            await be.init()

            await be.record_trade("BTC/USDT", "BUY",  0.01, 50000.0, 0.5, -500.0, "testnet", ts=1000.0)
            await be.record_trade("BTC/USDT", "SELL", 0.01, 50500.0, 0.5, 4500.0, "testnet", ts=2000.0)
            await be.record_trade("ETH/USDT", "BUY",  0.5,  2000.0,  0.5, -500.0, "live",    ts=3000.0)

            all_trades = await be.load_trades()
            assert len(all_trades) == 3

            testnet_only = await be.load_trades(mode="testnet")
            assert len(testnet_only) == 2
            assert all(t["mode"] == "testnet" for t in testnet_only)
            # DESC 정렬 확인
            assert testnet_only[0]["ts"] > testnet_only[1]["ts"]
            assert testnet_only[0]["side"] == "SELL"

    asyncio.run(_run())
    print("  [PASS] persistence_roundtrip: init/insert/load + mode 필터링")


def test_persistence_equity_and_events():
    """A2 확장: equity_snapshots / bot_events 테이블 insert+select."""
    import tempfile
    import os as _os
    from persistence import SqliteBackend

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _os.path.join(tmp, "trades.db")
            be = SqliteBackend(path=db_path)
            await be.init()

            await be.record_equity_snapshot(
                mode="testnet", equity_usdt=1000.0, cash_usdt=700.0,
                position_value_usdt=300.0, realized_pnl=5.0, unrealized_pnl=-2.0,
                ts=1000.0,
            )
            await be.record_event(
                mode="testnet", event_type="STARTUP", severity="INFO",
                message="bot booted", context={"pid": 123}, ts=1001.0,
            )

            # sqlite 직접 검증 (스키마 존재 + row 삽입)
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                eq_rows = conn.execute("SELECT * FROM equity_snapshots").fetchall()
                ev_rows = conn.execute("SELECT * FROM bot_events").fetchall()
            assert len(eq_rows) == 1 and eq_rows[0]["equity_usdt"] == 1000.0
            assert len(ev_rows) == 1
            assert ev_rows[0]["event_type"] == "STARTUP"
            assert '"pid": 123' in ev_rows[0]["context"]

    asyncio.run(_run())
    print("  [PASS] persistence_equity_and_events: 신규 테이블 왕복")


def test_n3_snapshot_equity_records_positions():
    """N3: snapshot_equity() 가 잔고 + 비-USDT 포지션 평가액을 기록한다."""
    import persistence
    from executor import snapshot_equity
    from shared_state import BotState

    captured: list[dict] = []
    orig = persistence.record_equity_snapshot

    async def fake(mode, equity_usdt, cash_usdt, position_value_usdt,
                   realized_pnl, unrealized_pnl, ts=None):
        captured.append({
            "mode": mode, "equity": equity_usdt, "cash": cash_usdt,
            "pos": position_value_usdt, "rpnl": realized_pnl,
            "upnl": unrealized_pnl,
        })

    persistence.record_equity_snapshot = fake
    try:
        state = BotState()
        ex = MockExchangeRecovery(
            balances={"USDT": 500.0, "ETH": 0.5},
            tickers={"ETH/USDT": 2000.0},
        )
        asyncio.run(snapshot_equity(ex, state))
    finally:
        persistence.record_equity_snapshot = orig

    assert len(captured) == 1, f"record_equity_snapshot 미호출: {captured}"
    row = captured[0]
    assert row["cash"] == 500.0, f"cash 오류: {row['cash']}"
    # ETH 0.5 * $2000 = $1000
    assert abs(row["pos"] - 1000.0) < 0.01, f"position_value 오류: {row['pos']}"
    assert abs(row["equity"] - 1500.0) < 0.01, f"equity 오류: {row['equity']}"
    assert row["mode"] in {"live", "testnet"}
    print(f"  [PASS] n3_snapshot_equity: equity=${row['equity']:.2f}, "
          f"cash=${row['cash']:.2f}, pos=${row['pos']:.2f}")


def test_n4_market_filter_logs_transition_event():
    """N4: BTC 200MA 상태 전환 시 record_event 가 호출된다."""
    import persistence
    from executor import update_market_filter
    from shared_state import BotState

    captured: list[tuple] = []
    orig = persistence.record_event

    async def fake(mode, event_type, severity, message, context=None, ts=None):
        captured.append((event_type, severity, context))

    persistence.record_event = fake
    try:
        state = BotState()
        state.is_market_healthy = True  # 초기 healthy

        # MockExchange 서브클래스: closes 중 앞 200개는 120, 마지막은 100 → MA200>current
        class _BearMarket(MockExchange):
            async def fetch_ohlcv(self, symbol, timeframe, limit=None):
                n = limit or 201
                prices = [120.0] * (n - 1) + [100.0]
                return [[i, 99, 121, 99, prices[i], 1_000_000] for i in range(n)]

        asyncio.run(update_market_filter(state, _BearMarket()))
    finally:
        persistence.record_event = orig

    assert state.is_market_healthy is False, "200MA 하회인데 healthy 유지"
    assert any(c[0] == "MARKET_FILTER" and c[1] == "WARNING" for c in captured), (
        f"MARKET_FILTER WARNING 이벤트 누락: {captured}"
    )
    print(f"  [PASS] n4_market_filter_event: {len(captured)}회 기록")


def test_n4_recover_state_logs_event():
    """N4: recover_state() 완료 시 RECOVER_STATE 이벤트가 기록된다."""
    import persistence
    from executor import recover_state

    captured: list[tuple] = []
    orig = persistence.record_event

    async def fake(mode, event_type, severity, message, context=None, ts=None):
        captured.append((event_type, severity, context))

    persistence.record_event = fake
    try:
        ex = MockExchangeRecovery(balances={"USDT": 1000.0})
        asyncio.run(recover_state(ex))
    finally:
        persistence.record_event = orig

    assert any(c[0] == "RECOVER_STATE" for c in captured), (
        f"RECOVER_STATE 이벤트 누락: {captured}"
    )
    event = next(c for c in captured if c[0] == "RECOVER_STATE")
    assert event[2] is not None and "canceled" in event[2], (
        f"context 에 결과 누락: {event[2]}"
    )
    print(f"  [PASS] n4_recover_state_event: context keys={list(event[2].keys())}")


def test_n5_recover_logs_trade_on_liquidation():
    """N5: recover_state() 청산 매도가 trades 테이블에 기록된다.
    감사 권고: emergency 청산도 BUY/SELL 와 동일하게 거래 이력 추적."""
    import persistence
    from executor import recover_state

    captured: list[tuple] = []
    orig = persistence.record_trade

    async def fake(symbol, side, qty, price, fee, pnl, mode, ts=None):
        captured.append((symbol, side, qty, price, mode))

    persistence.record_trade = fake
    try:
        ex = MockExchangeRecovery(
            balances={"USDT": 500.0, "ETH": 0.5, "BTC": 0.01},
            tickers={"ETH/USDT": 2000.0, "BTC/USDT": 50000.0},
        )
        asyncio.run(recover_state(ex))
    finally:
        persistence.record_trade = orig

    assert len(captured) == 2, f"청산 trade 기록 누락: {captured}"
    sides = {c[1] for c in captured}
    assert sides == {"SELL"}, f"청산 trade side 오류: {sides}"
    symbols = {c[0] for c in captured}
    assert symbols == {"ETH/USDT", "BTC/USDT"}, (
        f"예상 심볼 누락: {symbols}"
    )
    print(f"  [PASS] n5_recover_logs_trade: {len(captured)}건 SELL 기록 "
          f"({symbols})")


def test_n5b_recover_throttles_between_sells():
    """N5b: recover_state() 매도 사이에 throttle(asyncio.sleep) 호출.
    binance 50 orders/10s 제한 회피 — testnet 사전 잔고 다중 청산 시 429 폭주 방지."""
    import executor as executor_mod
    from executor import recover_state, RECOVER_SELL_THROTTLE_SEC

    sleep_durations: list[float] = []
    orig_sleep = executor_mod.asyncio.sleep

    async def fake_sleep(seconds):
        sleep_durations.append(seconds)
        # 실제로 sleep 안 함 — 테스트 빠르게 끝내려고

    executor_mod.asyncio.sleep = fake_sleep
    try:
        ex = MockExchangeRecovery(
            balances={"USDT": 100.0, "ETH": 0.5, "BTC": 0.01, "SOL": 0.2},
            tickers={"ETH/USDT": 2000.0, "BTC/USDT": 50000.0,
                     "SOL/USDT": 100.0},
        )
        asyncio.run(recover_state(ex))
    finally:
        executor_mod.asyncio.sleep = orig_sleep

    throttle_calls = [s for s in sleep_durations
                      if s == RECOVER_SELL_THROTTLE_SEC]
    # 3건 매도 → throttle 호출 최소 3회
    assert len(throttle_calls) >= 3, (
        f"throttle 호출 부족 ({RECOVER_SELL_THROTTLE_SEC}s): "
        f"{throttle_calls} (전체 sleep: {sleep_durations})"
    )
    print(f"  [PASS] n5b_recover_throttles: {len(throttle_calls)}회 throttle "
          f"@{RECOVER_SELL_THROTTLE_SEC}s")


def test_record_trade_hook_called_on_sell():
    """매도 체결 시 persistence.record_trade(async) 가 호출되는지 (SELL + mode 전달)."""
    from executor import GridEngine
    from shared_state import BotState
    import persistence

    captured: list[tuple] = []
    orig = persistence.record_trade

    async def fake(symbol, side, qty, price, fee, pnl, mode, ts=None):
        captured.append((symbol, side, qty, price, mode))

    persistence.record_trade = fake
    try:
        state = BotState()
        ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
        engine = GridEngine("ETH/USDT", ex, state)
        asyncio.run(_hook_sell_async(engine, ex))
    finally:
        persistence.record_trade = orig

    sides = [c[1] for c in captured]
    assert "BUY" in sides, f"초기 매수 BUY 기록 누락: {sides}"
    assert "SELL" in sides, f"매도 체결 SELL 기록 누락: {sides}"
    modes = {c[4] for c in captured}
    assert modes <= {"live", "testnet"}, f"예상외 mode: {modes}"
    print(f"  [PASS] record_trade_hook_called: {len(captured)}회 호출, sides={sides}")


async def _hook_sell_async(engine, ex):
    await engine.setup_grid()
    sell_oid = list(engine.sell_orders.keys())[0]
    ex.simulate_fill(sell_oid)
    await engine.monitor_orders()


def test_n1_supabase_init_failure_falls_back_to_sqlite():
    """N1: SupabaseBackend.init() 실패 시 init_db() 가 SQLite 로 degraded 기동."""
    import tempfile
    import os as _os
    import persistence
    # persistence 가 참조하는 config 객체를 그대로 사용해야 한다.
    # test_mode_branch_* 에서 config 모듈을 reload 했을 경우 `import config`
    # 로 새로 가져오면 persistence 가 보는 것과 다른 객체가 될 수 있음.
    _config = persistence.config

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            db_path = _os.path.join(tmp, "fallback.db")
            # persistence 싱글톤 + fallback 상태 초기화
            persistence._backend = None
            persistence._last_fallback_reason = None

            saved = (_config.DB_BACKEND, _config.SUPABASE_DB_URL, _config.SQLITE_DB_PATH)
            saved_init = persistence.SupabaseBackend.init
            _config.DB_BACKEND = "supabase"
            _config.SUPABASE_DB_URL = "postgres://unused:unused@localhost:5432/fake"
            _config.SQLITE_DB_PATH = db_path

            async def fake_init(self):
                raise RuntimeError("asyncpg connect refused")

            persistence.SupabaseBackend.init = fake_init
            try:
                result = await persistence.init_db()
                assert result == "sqlite_fallback", f"fallback 미발동: {result}"
                # fallback 이후 기록이 SQLite 에 쌓이는지 확인 (config 복원 전)
                await persistence.record_trade(
                    "BTC/USDT", "BUY", 0.01, 50000.0, 0.5, 0.0, "testnet", ts=1000.0,
                )
                rows = await persistence.load_trades()
                assert len(rows) == 1 and rows[0]["symbol"] == "BTC/USDT"
            finally:
                persistence.SupabaseBackend.init = saved_init
                _config.DB_BACKEND, _config.SUPABASE_DB_URL, _config.SQLITE_DB_PATH = saved
                persistence._backend = None
                persistence._last_fallback_reason = None

    asyncio.run(_run())
    print("  [PASS] n1_fallback_to_sqlite: Supabase init 실패 → SQLite 기록 가능")


def test_n1_fallback_reason_exposed_for_alert():
    """N1: fallback 사유가 get_fallback_reason() 으로 노출되어 텔레그램 알림에 사용 가능."""
    import tempfile
    import os as _os
    import persistence
    _config = persistence.config

    async def _run():
        with tempfile.TemporaryDirectory() as tmp:
            persistence._backend = None
            persistence._last_fallback_reason = None

            saved = (_config.DB_BACKEND, _config.SUPABASE_DB_URL, _config.SQLITE_DB_PATH)
            saved_init = persistence.SupabaseBackend.init
            _config.DB_BACKEND = "supabase"
            _config.SUPABASE_DB_URL = "postgres://x"
            _config.SQLITE_DB_PATH = _os.path.join(tmp, "f.db")

            async def fake_init(self):
                raise ConnectionError("DNS resolution failed for abc.supabase.co")

            persistence.SupabaseBackend.init = fake_init
            try:
                await persistence.init_db()
                reason = persistence.get_fallback_reason()
                assert reason is not None, "fallback 사유가 None"
                assert "ConnectionError" in reason, f"예외 타입 누락: {reason}"
                assert "DNS" in reason, f"원본 메시지 누락: {reason}"
            finally:
                persistence.SupabaseBackend.init = saved_init
                _config.DB_BACKEND, _config.SUPABASE_DB_URL, _config.SQLITE_DB_PATH = saved
                persistence._backend = None
                persistence._last_fallback_reason = None

    asyncio.run(_run())
    print("  [PASS] n1_fallback_reason_exposed: 텔레그램 알림용 사유 추출 확인")


def test_n1_sqlite_native_failure_not_swallowed():
    """N1: sqlite 모드에서 init 실패는 fallback 대상이 아니므로 예외가 그대로 전파되어야 한다.
    (로컬 쓰기 실패는 숨기면 안 됨)"""
    import persistence
    _config = persistence.config

    async def _run():
        persistence._backend = None
        persistence._last_fallback_reason = None

        saved_backend = _config.DB_BACKEND
        saved_init = persistence.SqliteBackend.init
        _config.DB_BACKEND = "sqlite"

        async def fake_init(self):
            raise OSError("disk full")

        persistence.SqliteBackend.init = fake_init
        try:
            try:
                await persistence.init_db()
            except OSError as e:
                assert "disk full" in str(e)
                return "propagated"
            return "swallowed"
        finally:
            persistence.SqliteBackend.init = saved_init
            _config.DB_BACKEND = saved_backend
            persistence._backend = None

    result = asyncio.run(_run())
    assert result == "propagated", f"sqlite 실패가 삼켜짐: {result}"
    print("  [PASS] n1_sqlite_failure_propagated: 로컬 쓰기 실패는 기동 차단")


# ─── N2: persistence 공개 함수 자체 격리 (백엔드 실패가 매매 흐름에 전파되지 않음) ───

class _FailingBackend:
    """모든 write 가 예외를 던지는 mock 백엔드 (N2 테스트 전용)."""
    def __init__(self, exc: BaseException):
        self.exc = exc

    async def record_trade(self, *a, **kw):
        raise self.exc

    async def record_equity_snapshot(self, *a, **kw):
        raise self.exc

    async def record_event(self, *a, **kw):
        raise self.exc


def _n2_run_with_failing_backend(coro_factory, exc: BaseException):
    """FailingBackend + notifier.notify_error 캡처로 공개 함수를 실행.
    반환: (raised_exc_or_None, captured_notifier_calls)."""
    import persistence
    import notifier

    captured: list[tuple] = []

    async def fake_notify_error(ctx, e):
        captured.append((ctx, e))

    orig_backend = persistence._backend
    orig_notify = notifier.notify_error
    persistence._backend = _FailingBackend(exc)
    notifier.notify_error = fake_notify_error
    raised = None
    try:
        try:
            asyncio.run(coro_factory())
        except BaseException as e:
            raised = e
    finally:
        persistence._backend = orig_backend
        notifier.notify_error = orig_notify
    return raised, captured


def test_n2_record_trade_swallows_backend_error():
    """N2: 백엔드 record_trade 예외를 persistence 공개 함수가 삼키고 notifier 로 알림."""
    import persistence
    exc = RuntimeError("asyncpg pool drained")
    raised, captured = _n2_run_with_failing_backend(
        lambda: persistence.record_trade(
            "BTC/USDT", "BUY", 0.01, 50000.0, 0.5, 0.0, "testnet",
        ),
        exc,
    )
    assert raised is None, f"예외가 전파됨: {raised!r}"
    assert len(captured) == 1, f"notify_error 호출 횟수 이상: {captured}"
    assert captured[0][0] == "persistence.record_trade"
    assert captured[0][1] is exc
    print("  [PASS] n2_record_trade_swallows: 백엔드 실패가 호출부로 전파되지 않음")


def test_n2_record_event_swallows_backend_error():
    """N2: 백엔드 record_event 예외를 persistence 공개 함수가 삼키고 notifier 로 알림."""
    import persistence
    exc = ConnectionError("postgres terminated connection")
    raised, captured = _n2_run_with_failing_backend(
        lambda: persistence.record_event(
            "testnet", "TEST", "INFO", "msg", {"k": "v"},
        ),
        exc,
    )
    assert raised is None, f"예외가 전파됨: {raised!r}"
    assert len(captured) == 1 and captured[0][0] == "persistence.record_event"
    print("  [PASS] n2_record_event_swallows: 매매 흐름 차단 없음")


def test_n2_record_equity_snapshot_swallows_backend_error():
    """N2: 백엔드 record_equity_snapshot 예외를 공개 함수가 삼키고 notifier 로 알림."""
    import persistence
    exc = TimeoutError("acquire pool timeout 10s")
    raised, captured = _n2_run_with_failing_backend(
        lambda: persistence.record_equity_snapshot(
            "testnet", 1000.0, 800.0, 200.0, 50.0, 0.0,
        ),
        exc,
    )
    assert raised is None, f"예외가 전파됨: {raised!r}"
    assert len(captured) == 1 and captured[0][0] == "persistence.record_equity_snapshot"
    print("  [PASS] n2_record_equity_swallows: 30분 스냅샷 타이머가 지속 가능")


def test_n12_service_uses_journald():
    """N12: deploy/daily30k.service 가 journald 로 로그 캡처 (timestamp 자동 부여 + auto-rotate).

    2026-04-28~05-04 6일 hang 사후 디버깅 시 print 캡처 로그에 timestamp 가
    없어 hang 시각을 추정 못 했던 것이 가장 큰 교훈. journald 전환으로
    `journalctl --since "Apr 28 02:00"` 같은 시간 쿼리가 가능해야 한다."""
    from pathlib import Path

    svc_path = Path(__file__).parent / "deploy" / "daily30k.service"
    content = svc_path.read_text()
    assert "StandardOutput=journal" in content, "stdout journald 미전환"
    assert "StandardError=journal" in content, "stderr journald 미전환"
    assert "SyslogIdentifier=daily30k" in content, "SyslogIdentifier 누락 (journalctl -t 식별자)"
    # 기존 append:logs/*.log 흔적이 남아있으면 systemd 가 우선순위 충돌
    assert "append:" not in content, "이전 append 모드 잔재 — journald 와 충돌"
    print("  [PASS] n12_service_uses_journald: journald 전환 + SyslogIdentifier 확인")


def test_n19_supervise_cancels_hung_executor():
    """N19: heartbeat 무갱신 코루틴을 watchdog_timeout 초과 시 강제 cancel → TimeoutError → 재시작.

    2026-04-28~05-04 사건의 핵심: run_executor 가 어떤 await 에서 예외 없이
    영원히 갇혀도 _supervise 가 못 잡았던 것. watchdog_timeout 으로 hang 을
    예외로 변환해 기존 재시작 경로 재사용."""
    import main as main_mod
    import persistence
    import notifier
    from shared_state import BotState

    state = BotState()
    captured_events: list[tuple] = []
    sent_messages: list = []

    orig_record = persistence.record_event
    orig_send = notifier.send
    orig_notify = notifier.notify_error

    async def fake_record(mode, event_type, severity, message, payload=None):
        captured_events.append((event_type, severity, message, payload))

    async def fake_send(msg, **kw):
        sent_messages.append(msg)

    async def fake_notify(ctx, e):
        sent_messages.append(("error", ctx, str(e)))

    persistence.record_event = fake_record
    notifier.send = fake_send
    notifier.notify_error = fake_notify

    invocation = [0]

    async def coro():
        invocation[0] += 1
        if invocation[0] >= 2:
            # 두 번째 시도: 정상 종료 (재시작 무한 루프 방지)
            return
        # 첫 번째: heartbeat 갱신 없이 무한 await → watchdog 발동 대상
        await asyncio.sleep(10.0)

    try:
        asyncio.run(main_mod._supervise(
            "executor", coro, state,
            max_restarts=3,
            watchdog_timeout=0.5,
            heartbeat_attr="executor_heartbeat",
        ))
    finally:
        persistence.record_event = orig_record
        notifier.send = orig_send
        notifier.notify_error = orig_notify

    # 첫 시도 watchdog cancel → SUPERVISOR_RESTART 1건, 그 후 정상 종료
    restart_events = [e for e in captured_events if e[0] == "SUPERVISOR_RESTART"]
    assert len(restart_events) == 1, (
        f"SUPERVISOR_RESTART 정확히 1건이어야: {captured_events}"
    )
    assert restart_events[0][3] is not None and restart_events[0][3].get("is_watchdog") is True, (
        f"is_watchdog payload 누락: {restart_events[0]}"
    )
    assert invocation[0] == 2, f"두 번째 시도 진입해야: {invocation[0]}"
    print(f"  [PASS] n19_supervise_cancels_hung: {invocation[0]}회 시도, "
          f"watchdog 1회 발동")


def test_n19_supervise_normal_executor_no_false_trigger():
    """N19: heartbeat 갱신 정상 코루틴은 watchdog 발동 없이 정상 종료."""
    import time
    import main as main_mod
    import persistence
    import notifier
    from shared_state import BotState

    state = BotState()
    captured_events: list = []
    orig_record = persistence.record_event
    orig_send = notifier.send
    orig_notify = notifier.notify_error

    async def fake_record(*a, **kw):
        captured_events.append(a)

    async def noop(*a, **kw):
        pass

    persistence.record_event = fake_record
    notifier.send = noop
    notifier.notify_error = noop

    async def healthy_coro():
        # heartbeat 매 0.05s 갱신 — watchdog_timeout 0.5s 보다 훨씬 빠름
        for _ in range(6):
            state.executor_heartbeat = time.time()
            await asyncio.sleep(0.05)
        # 정상 종료

    try:
        asyncio.run(main_mod._supervise(
            "executor", healthy_coro, state,
            max_restarts=3,
            watchdog_timeout=0.5,
            heartbeat_attr="executor_heartbeat",
        ))
    finally:
        persistence.record_event = orig_record
        notifier.send = orig_send
        notifier.notify_error = orig_notify

    assert len(captured_events) == 0, (
        f"정상 코루틴인데 SUPERVISOR_RESTART 발생: {captured_events}"
    )
    print("  [PASS] n19_supervise_normal_no_false_trigger: 정상 종료 + 0건 재시작")


def test_n25_supervise_restarts_when_snapshot_stale():
    """N25: heartbeat 가 갱신돼도 equity snapshot progress 가 끊기면 executor 재시작."""
    import time
    import main as main_mod
    import persistence
    from shared_state import BotState

    state = BotState()
    captured_events: list[tuple] = []

    orig_record = persistence.record_event
    orig_notify = main_mod.notify_error
    orig_send = main_mod.send

    async def fake_record(mode, event_type, severity, message, payload=None):
        captured_events.append((event_type, severity, message, payload))

    async def noop(*a, **kw):
        pass

    persistence.record_event = fake_record
    main_mod.notify_error = noop
    main_mod.send = noop

    invocation = [0]

    async def coro():
        invocation[0] += 1
        if invocation[0] >= 2:
            return
        while True:
            state.executor_heartbeat = time.time()
            await asyncio.sleep(0.05)

    try:
        asyncio.run(main_mod._supervise(
            "executor", coro, state,
            max_restarts=3,
            watchdog_timeout=0.5,
            heartbeat_attr="executor_heartbeat",
            progress_timeout=0.25,
            progress_attr="executor_last_snapshot_at",
        ))
    finally:
        persistence.record_event = orig_record
        main_mod.notify_error = orig_notify
        main_mod.send = orig_send

    restart_events = [e for e in captured_events if e[0] == "SUPERVISOR_RESTART"]
    assert len(restart_events) == 1, f"progress 재시작 1건이어야: {captured_events}"
    payload = restart_events[0][3] or {}
    assert payload.get("is_watchdog") is True, f"is_watchdog payload 누락: {payload}"
    assert "progress watchdog" in payload.get("error", ""), (
        f"progress watchdog 메시지 누락: {restart_events[0]}"
    )
    assert invocation[0] == 2, f"재시작 후 두 번째 시도 필요: {invocation[0]}"
    print("  [PASS] n25_supervise_snapshot_stale: heartbeat 정상 + snapshot 침묵 재시작")


def test_n25_snapshot_and_trade_mark_progress():
    """N25: snapshot/trade 성공 시 BotState 의 진행 시각이 갱신된다."""
    import persistence
    from executor import snapshot_equity, _log_trade
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=1234.0)
    captured: list[tuple] = []

    orig_snapshot = persistence.record_equity_snapshot
    orig_trade = persistence.record_trade

    async def fake_snapshot(**kw):
        captured.append(("snapshot", kw))

    async def fake_trade(*a, **kw):
        captured.append(("trade", a, kw))

    persistence.record_equity_snapshot = fake_snapshot
    persistence.record_trade = fake_trade

    try:
        before_snapshot = state.executor_last_snapshot_at
        asyncio.run(snapshot_equity(ex, state))
        before_trade = state.executor_last_trade_at
        asyncio.run(_log_trade("BTC/USDT", "BUY", 0.1, 100.0, 0.01, -10.0, state))
    finally:
        persistence.record_equity_snapshot = orig_snapshot
        persistence.record_trade = orig_trade

    assert state.executor_last_snapshot_at > before_snapshot, (
        "snapshot 성공 후 executor_last_snapshot_at 미갱신"
    )
    assert state.executor_last_trade_at > before_trade, (
        "trade 기록 후 executor_last_trade_at 미갱신"
    )
    assert [row[0] for row in captured] == ["snapshot", "trade"], (
        f"예상 기록 순서 불일치: {captured}"
    )
    print("  [PASS] n25_progress_markers: snapshot/trade 진행 시각 갱신")


def test_n20_retry_api_times_out_on_hung_call():
    """N20: _retry_api 가 hung await 을 timeout 으로 끊고 max_retries 만큼 시도 후 raise.

    이번 사건의 가장 의심되는 가설: ccxt 의 fetch_balance/fetch_ticker/fetch_ohlcv
    같은 외부 await 가 네트워크 이상으로 영원히 갇힘. 60s 디폴트 timeout 으로
    각 시도를 끊으면 지수 백오프 후 최종 raise → 호출부 try/except 가 잡음."""
    import asyncio as _async
    from executor import _retry_api

    call_count = [0]

    async def hung_fn():
        call_count[0] += 1
        await _async.sleep(5.0)  # timeout 보다 훨씬 김

    raised: BaseException | None = None
    try:
        asyncio.run(_retry_api(hung_fn, max_retries=2, timeout=0.05))
    except BaseException as e:
        raised = e

    assert isinstance(raised, _async.TimeoutError), (
        f"기대 TimeoutError, 실제: {type(raised).__name__}={raised!r}"
    )
    assert call_count[0] == 2, (
        f"max_retries=2 만큼 시도해야: 실제 {call_count[0]}"
    )
    print(f"  [PASS] n20_retry_api_times_out: {call_count[0]}회 시도 후 TimeoutError")


def test_n20_retry_api_normal_call_unaffected():
    """N20: 정상 빠른 호출은 timeout 영향 없이 결과 반환."""
    from executor import _retry_api

    async def fast_fn(value):
        await asyncio.sleep(0.01)
        return value * 2

    result = asyncio.run(_retry_api(fast_fn, 21, timeout=1.0))
    assert result == 42, f"기대 42, 실제 {result}"
    print("  [PASS] n20_retry_api_normal_unaffected: timeout 적용해도 정상 호출 영향 없음")


def test_n22_init_db_result_visible_in_journal():
    """N22: main.py 가 init_db 결과를 stdout/stderr 로 무조건 출력 (journal 가시화).

    2026-05-04 사건: 부팅 시 Supabase 일시 끊김으로 SQLite fallback 발동했으나
    [DEGRADED] 텔레그램 알림이 일시 NetworkError 로 누락 → 16시간 후에야 발견.
    텔레그램은 외부 의존이라 신뢰성 한계가 있음. journal 에 흔적 남기는 것이
    가장 신뢰성 높은 사후 진단 수단."""
    from pathlib import Path

    main_path = Path(__file__).parent / "main.py"
    content = main_path.read_text()
    assert 'print(f"[init_db] backend=' in content, \
        "init_db 결과 stdout 출력 누락 — journal 에 backend 선택 흔적 안 남음"
    assert '[init_db] FALLBACK reason=' in content, \
        "fallback 사유 stderr 출력 누락 — 텔레그램 누락 시 사후 진단 불가"
    assert "file=sys.stderr" in content, \
        "fallback 사유는 stderr 로 가야 journal -p err 로 빠르게 필터 가능"
    assert "import sys" in content, "sys import 누락"
    print("  [PASS] n22_init_db_result_visible_in_journal: backend 선택 결과 journal 가시화")


# ─────────────────────────────────────────────────────────────────────
# N26: DAILY_STOP / KILL_SWITCH 분기 break 보장 (2026-05-09 사건 처방)
# ─────────────────────────────────────────────────────────────────────

class _N26FailingEngineBase:
    """공통 — setup_grid 에서 daily_pnl 강제 변경, emergency_sell 가 raise.

    iter 1 line 779 setup_grid 호출 시 daily_pnl 변경 → iter 2 line 721/735
    분기 진입 시 engine 살아있는 상태로 emergency_sell 호출 → raise.
    결함 코드: except 블록이 잡아 kill_event.set()/break 도달 못 함 → spam.
    패치 코드: kill_event.set() 가 emergency_sell 전에 호출 + try/except 로 break 보장."""

    _trigger_pnl: float = 0.0  # 서브클래스에서 설정

    def __init__(self, symbol, exchange, state):
        self.symbol = symbol
        self.exchange = exchange
        self.state = state
        self.is_active = False
        self.buy_orders: list = []
        self.sell_orders: list = []
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.total_invested = 0.0

    def validate_fees(self):
        return True

    async def setup_grid(self):
        self.is_active = True
        if self.state.daily_pnl == 0:
            self.state.daily_pnl = self._trigger_pnl

    async def emergency_sell(self, reason):
        raise RuntimeError(f"simulated ccxt failure: {reason}")

    async def _get_current_price(self):
        return 100.0

    async def check_stop_loss(self, p):
        return False

    async def monitor_orders(self):
        pass

    async def regrid(self):
        pass


def _n26_install_mocks(engine_cls):
    """run_executor 외부 의존 우회 + GridEngine 교체. (orig_state, restore) 반환."""
    import shared_state  # noqa: F401
    import executor as executor_mod
    import notifier
    import persistence

    captured_events: list[tuple] = []

    orig_record_event = persistence.record_event

    async def fake_record_event(mode, event_type, severity, message, payload=None):
        captured_events.append((event_type, severity, message))

    persistence.record_event = fake_record_event

    orig_send = notifier.send
    orig_notify_kill = notifier.notify_kill_switch
    orig_notify_daily = notifier.notify_daily_stop
    orig_notify_err = notifier.notify_error
    orig_notify_trade = notifier.notify_trade

    async def _noop(*a, **kw):
        pass

    notifier.send = _noop
    notifier.notify_kill_switch = _noop
    notifier.notify_daily_stop = _noop
    notifier.notify_error = _noop
    notifier.notify_trade = _noop

    orig_grid_engine = executor_mod.GridEngine
    executor_mod.GridEngine = engine_cls

    orig_umf = executor_mod.update_market_filter
    orig_ukr = executor_mod.update_krw_rate
    orig_se = executor_mod.snapshot_equity
    orig_recover = executor_mod.recover_state
    executor_mod.update_market_filter = _noop
    executor_mod.update_krw_rate = _noop
    executor_mod.snapshot_equity = _noop
    executor_mod.recover_state = _noop

    def restore():
        persistence.record_event = orig_record_event
        notifier.send = orig_send
        notifier.notify_kill_switch = orig_notify_kill
        notifier.notify_daily_stop = orig_notify_daily
        notifier.notify_error = orig_notify_err
        notifier.notify_trade = orig_notify_trade
        executor_mod.GridEngine = orig_grid_engine
        executor_mod.update_market_filter = orig_umf
        executor_mod.update_krw_rate = orig_ukr
        executor_mod.snapshot_equity = orig_se
        executor_mod.recover_state = orig_recover

    return captured_events, restore


def test_n26_daily_stop_no_spam_when_emergency_sell_raises():
    """N26: 5/9 00:00 사건 재현·방지.

    DAILY_STOP 분기에서 engine.emergency_sell 가 ccxt 예외를 던지면
    `kill_event.set()` 과 `break` 가 도달 못 해 메인 루프가 spam 했던 결함.
    실제 사건: 5/9 00:00:28~00:02:34 KST DAILY_STOP 이벤트 3,562건 누적.

    패치: kill_event.set() 을 emergency_sell 보다 먼저 호출 + try/except 로
    감싸 break 도달 보장. DAILY_STOP 정확히 1건, kill_event=True."""
    asyncio.run(_test_n26_daily_stop_async())


async def _test_n26_daily_stop_async():
    import config
    import executor as executor_mod
    from shared_state import BotState

    class _DailyStopEngine(_N26FailingEngineBase):
        _trigger_pnl = config.DAILY_TARGET + 100  # should_stop_profit=True

    captured_events, restore = _n26_install_mocks(_DailyStopEngine)

    state = BotState()
    state.target_coin = "BTC/USDT"

    class _Ex:
        pass

    ex = _Ex()

    async def force_stop():
        await asyncio.sleep(5.0)
        state.kill_event.set()

    try:
        await asyncio.wait_for(
            asyncio.gather(
                executor_mod.run_executor(state, ex),
                force_stop(),
            ),
            timeout=10.0,
        )
    finally:
        restore()

    daily_stop_count = sum(1 for e in captured_events if e[0] == "DAILY_STOP")
    assert daily_stop_count == 1, (
        f"DAILY_STOP 정확히 1건이어야 함 (실제 {daily_stop_count}건). "
        f"5/9 00:00 spam 사건(3,562건) 재발."
    )
    assert state.kill_event.is_set(), "kill_event 가 set 되어야 함"
    print(f"  [PASS] n26_daily_stop_no_spam: DAILY_STOP {daily_stop_count}건, kill_event=True")


def test_n26_kill_switch_no_spam_when_emergency_sell_raises():
    """N26: KILL_SWITCH 분기도 DAILY_STOP 와 동일 결함 (대칭 검증).

    daily_pnl <= -DAILY_LOSS_LIMIT 분기에서도 emergency_sell 예외 → spam 가능했던 결함.
    패치: KILL_SWITCH 분기도 kill_event.set() 선호출 + try/except 적용."""
    asyncio.run(_test_n26_kill_switch_async())


async def _test_n26_kill_switch_async():
    import config
    import executor as executor_mod
    from shared_state import BotState

    class _KillSwitchEngine(_N26FailingEngineBase):
        _trigger_pnl = -config.DAILY_LOSS_LIMIT - 100

    captured_events, restore = _n26_install_mocks(_KillSwitchEngine)

    state = BotState()
    state.target_coin = "BTC/USDT"

    class _Ex:
        pass

    ex = _Ex()

    async def force_stop():
        await asyncio.sleep(5.0)
        state.kill_event.set()

    try:
        await asyncio.wait_for(
            asyncio.gather(
                executor_mod.run_executor(state, ex),
                force_stop(),
            ),
            timeout=10.0,
        )
    finally:
        restore()

    kill_count = sum(1 for e in captured_events if e[0] == "KILL_SWITCH")
    assert kill_count == 1, (
        f"KILL_SWITCH 정확히 1건이어야 함 (실제 {kill_count}건). spam 결함 재발."
    )
    assert state.kill_event.is_set(), "kill_event 가 set 되어야 함"
    print(f"  [PASS] n26_kill_switch_no_spam: KILL_SWITCH {kill_count}건, kill_event=True")


def test_n27_daily_stop_does_not_terminate_supervisor():
    """N27 (2026-05-10 사건): DAILY_STOP 분기가 kill_event.set() 을 호출하면
    main 의 모든 _supervise(screener/executor/telegram) 가 종료 → main() 정상 exit(0)
    → systemd Restart=on-failure 정책상 정상 종료는 재시작 안 함 → 봇 영구 종료
    → 다음 날 자정 자동 재개 불가능. 5/10 20:08 KST 일일 목표 달성 후 5/11 까지
    텔레그램·Supabase 둘 다 침묵.

    패치: DAILY_STOP 분기에서 kill_event 호출 제거 + 자정까지 sleep loop 로 대기
    (executor 만 일시 중단, screener/telegram 은 계속), 자정 reset_daily 후 매매 재개."""
    asyncio.run(_test_n27_async())


async def _test_n27_async():
    import inspect
    import config
    import executor as executor_mod
    from shared_state import BotState

    class _DailyStopEngine(_N26FailingEngineBase):
        _trigger_pnl = config.DAILY_TARGET + 100  # should_stop_profit=True

        async def emergency_sell(self, reason):
            return None  # 5/10 사건은 emergency_sell 정상 통과 → 그래도 봇 종료된 케이스

    captured_events, restore = _n26_install_mocks(_DailyStopEngine)

    state = BotState()
    state.target_coin = "BTC/USDT"

    class _Ex:
        pass

    ex = _Ex()

    daily_stop_seen = asyncio.Event()
    orig_log_event = executor_mod._log_event

    async def spy_log_event(ev_type, sev, msg, payload=None):
        await orig_log_event(ev_type, sev, msg, payload)
        if ev_type == "DAILY_STOP":
            daily_stop_seen.set()

    executor_mod._log_event = spy_log_event

    kill_state_after_daily_stop = {"value": None}

    async def force_stop():
        await daily_stop_seen.wait()
        # DAILY_STOP 기록 후 sleep loop 진입까지 잠시 대기
        await asyncio.sleep(0.3)
        # ★ 핵심 단언: DAILY_STOP 분기는 kill_event 를 set 하면 안 됨
        kill_state_after_daily_stop["value"] = state.kill_event.is_set()
        # 이제 외부에서 set 하여 봇 정리 종료
        state.kill_event.set()

    try:
        await asyncio.wait_for(
            asyncio.gather(
                executor_mod.run_executor(state, ex),
                force_stop(),
            ),
            timeout=10.0,
        )
    finally:
        executor_mod._log_event = orig_log_event
        restore()

    assert daily_stop_seen.is_set(), "DAILY_STOP 이벤트 미기록 — 테스트 셋업 결함"
    assert kill_state_after_daily_stop["value"] is False, (
        "N27: DAILY_STOP 직후 kill_event 가 set 됨 — "
        "main 의 _supervise 들이 종료되어 봇 영구 정지. "
        "5/10 20:08 사건 재발."
    )

    # 정적 검증: 자정 자동 재개 분기 존재 (재개 가시성 확보)
    src = inspect.getsource(executor_mod.run_executor)
    ds_start = src.find("if state.should_stop_profit:")
    next_block = src.find("# ── 4.", ds_start)
    assert ds_start >= 0 and next_block > ds_start, "DAILY_STOP 블록 구조 변경 — 테스트 갱신 필요"
    ds_src = src[ds_start:next_block]
    assert "reset_daily" in ds_src, (
        "N27: DAILY_STOP 분기에 reset_daily() 호출 없음 — 자정 자동 재개 누락."
    )
    assert "DAILY_RESUME" in ds_src, (
        "N27: DAILY_STOP 분기에 DAILY_RESUME 이벤트 없음 — 재개 가시성 누락."
    )
    assert "executor_last_snapshot_at" in ds_src, (
        "N25: DAILY_STOP 의도적 대기 중 snapshot progress 갱신 없음 — "
        "progress watchdog 가 45분마다 executor 를 재시작할 수 있음."
    )
    assert "kill_event.set" not in ds_src, (
        "N27: DAILY_STOP 분기에 kill_event.set() 호출 — 봇 종료 결함 재발."
    )

    print("  [PASS] n27_daily_stop_no_terminate: kill_event 미설정 + 자정 재개 분기 확인")


def test_n28_supabase_pool_disables_statement_cache():
    """N28 (2026-05-11 사건): Supabase Transaction Pooler(pgbouncer 6543) 는
    transaction-mode 라 prepared statement 캐시 충돌 발생.
    `DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_N__" already exists`
    → silent fallback 발동 → 운영 데이터가 SQLite 로 빠짐. 처방: asyncpg.create_pool
    호출에 `statement_cache_size=0` 명시. 정적 검증 — 실제 connection 통합 테스트는 CI 환경
    의존성으로 회피."""
    import inspect
    import persistence

    src = inspect.getsource(persistence.SupabaseBackend.init)
    assert "statement_cache_size=0" in src, (
        "N28: SupabaseBackend.init 에 statement_cache_size=0 누락 — "
        "pgbouncer Transaction Pool 모드와 충돌 → silent fallback 재발."
    )
    print("  [PASS] n28_supabase_pool_no_cache: statement_cache_size=0 명시 확인")


def test_n29b_log_event_critical_emits_stdout():
    """N29-B (2026-05-13 사건): KILL_SWITCH 시 journal 에 단 1줄도 없어 진단 외란.
    _log_event 가 CRITICAL/ERROR/WARN 을 stdout 에 동시 출력하는지 확인.
    INFO 는 폭주 방지 위해 제외."""
    import io
    import contextlib
    import persistence
    from executor import _log_event

    orig_backend = persistence._backend

    class _NoopBackend:
        async def record_event(self, *a, **kw):
            return None
        async def record_trade(self, *a, **kw):
            return None
        async def record_equity_snapshot(self, *a, **kw):
            return None

    persistence._backend = _NoopBackend()
    try:
        # CRITICAL — 반드시 출력
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            asyncio.run(_log_event("KILL_SWITCH", "CRITICAL",
                                   "일일 손실 한도 초과",
                                   {"daily_pnl_krw": -159166.0,
                                    "limit_krw": 90000.0}))
        out = buf.getvalue()
        assert "[CRITICAL] KILL_SWITCH" in out, (
            f"CRITICAL 이벤트 stdout 누락: {out!r}"
        )
        assert "일일 손실 한도 초과" in out, f"메시지 누락: {out!r}"
        assert "daily_pnl_krw" in out, f"context payload 누락: {out!r}"

        # WARN — 출력
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            asyncio.run(_log_event("N25_TRADE_IDLE", "WARNING",
                                   "24시간 무거래 침묵", None))
        assert "[WARNING] N25_TRADE_IDLE" in buf.getvalue(), (
            "WARNING 이벤트 stdout 누락"
        )

        # INFO — 출력 안 됨 (journal 폭주 방지)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            asyncio.run(_log_event("EXECUTOR_START", "INFO",
                                   "executor 시작", None))
        assert buf.getvalue() == "", (
            f"INFO 이벤트가 stdout 에 출력됨 (폭주 위험): {buf.getvalue()!r}"
        )
    finally:
        persistence._backend = orig_backend

    print("  [PASS] n29b_log_event_severity_stdout: CRITICAL/WARN stdout / INFO 침묵")


def test_n29a_notify_death_script_valid():
    """N29-A (2026-05-13 사건): KILL_SWITCH 후 봇 종료 → 34시간 침묵.
    systemd ExecStopPost 훅 + notify_death.sh 가 외부 사망 알림을 보장하는지 정적 검증.
    """
    import os

    script_path = os.path.join(os.path.dirname(__file__), "deploy", "notify_death.sh")
    assert os.path.exists(script_path), (
        f"N29-A: deploy/notify_death.sh 누락 — systemd ExecStopPost 훅 실행 불가."
    )
    assert os.access(script_path, os.X_OK), (
        f"N29-A: {script_path} 실행 권한 부재 — systemd 가 호출해도 실행 실패."
    )

    with open(script_path) as f:
        body = f.read()
    assert "TELEGRAM_TOKEN" in body, "N29-A: notify_death.sh 가 TELEGRAM_TOKEN 미참조."
    assert "TELEGRAM_CHAT_ID" in body, "N29-A: notify_death.sh 가 TELEGRAM_CHAT_ID 미참조."
    assert "api.telegram.org" in body, "N29-A: 텔레그램 API 엔드포인트 누락."
    assert "exit 0" in body, (
        "N29-A: notify_death.sh 가 exit 0 으로 종료하지 않음 — "
        "알림 실패가 systemd Restart 정책에 영향 줄 위험."
    )

    service_path = os.path.join(os.path.dirname(__file__), "deploy", "daily30k.service")
    with open(service_path) as f:
        service_body = f.read()
    assert "ExecStopPost=" in service_body, (
        "N29-A: daily30k.service 에 ExecStopPost 훅 누락 — 사망 알림 미연결."
    )
    assert "notify_death.sh" in service_body, (
        "N29-A: ExecStopPost 가 notify_death.sh 를 가리키지 않음."
    )

    print("  [PASS] n29a_notify_death_script_valid: 사망 알림 훅 정적 검증 통과")


def test_n30_grid_setup_idle_alerts_after_threshold():
    """N30 (2026-05-15 사건): setup_grid 초기 매수 미체결로 engine=None 반복 시
    10일간 무거래였으나 어떤 경고도 없었다. N25 trade-idle 은 engine 활성 전제라
    이 상태를 못 잡는다. _note_grid_setup_idle 이 임계 경과 후 WARNING 을 내고,
    임계 전에는 침묵하며, 진입 성공 시 idle 추적이 리셋되는지 검증."""
    import persistence
    import executor
    from executor import _note_grid_setup_idle
    from shared_state import BotState

    captured: list[tuple] = []
    orig = persistence.record_event

    async def fake(mode, event_type, severity, message, context=None, ts=None):
        captured.append((event_type, severity))

    persistence.record_event = fake
    try:
        state = BotState()
        state.target_coin = "BTC/USDT"
        t0 = 1_000_000.0

        # 1) 첫 실패 — idle 시작 기록, 임계(1h) 전이라 침묵
        asyncio.run(_note_grid_setup_idle(state, "초기 매수 미체결", t0))
        assert state.executor_grid_idle_since == t0, "idle 시작 시각 미기록"
        assert not captured, f"임계 전 조기 경고 발생: {captured}"

        # 2) 임계 직전(59분) — 여전히 침묵
        asyncio.run(_note_grid_setup_idle(
            state, "초기 매수 미체결", t0 + executor.N30_GRID_IDLE_ALERT_SEC - 60))
        assert not captured, f"임계 직전 조기 경고: {captured}"

        # 3) 임계 초과(1h+1초) — WARNING 1건
        asyncio.run(_note_grid_setup_idle(
            state, "초기 매수 미체결", t0 + executor.N30_GRID_IDLE_ALERT_SEC + 1))
        assert any(et == "GRID_SETUP_IDLE" and sev == "WARNING" for et, sev in captured), (
            f"임계 초과인데 GRID_SETUP_IDLE WARNING 미발생: {captured}"
        )
        n_after_first = len(captured)

        # 4) 쿨다운(6h) 내 재호출 — 추가 경고 없음 (spam 방지)
        asyncio.run(_note_grid_setup_idle(
            state, "초기 매수 미체결", t0 + executor.N30_GRID_IDLE_ALERT_SEC + 120))
        assert len(captured) == n_after_first, f"쿨다운 내 spam 발생: {captured}"

        # 5) 진입 성공 시 호출자가 리셋 → 다음 idle 은 새 사이클로 재시작
        state.executor_grid_idle_since = 0.0
        asyncio.run(_note_grid_setup_idle(state, "초기 매수 미체결", t0 + 999_999))
        assert state.executor_grid_idle_since == t0 + 999_999, (
            "리셋 후 idle 시작 시각이 새로 기록되지 않음"
        )
    finally:
        persistence.record_event = orig

    print("  [PASS] n30_grid_setup_idle: 임계 경과 경고 + 침묵 + 쿨다운 + 리셋")


def test_n30_market_filter_unavailable_warns_once():
    """N30: BTC 일봉 < 201 이면 200MA 필터를 계산할 수 없어 update_market_filter 가
    조용히 return → is_market_healthy 가 기본값(True)에 동결된다 (5/15 testnet 일봉 20개).
    동작(매매 허용)은 유지하되 MARKET_FILTER_UNAVAILABLE WARNING 을 1회만 내는지 검증."""
    import persistence
    from executor import update_market_filter
    from shared_state import BotState

    captured: list[tuple] = []
    orig = persistence.record_event

    async def fake(mode, event_type, severity, message, context=None, ts=None):
        captured.append((event_type, severity))

    persistence.record_event = fake
    try:
        state = BotState()
        state.is_market_healthy = True

        class _ShortHistory(MockExchange):
            async def fetch_ohlcv(self, symbol, timeframe, limit=None):
                # testnet 처럼 일봉이 20개만 존재
                return [[i, 99, 121, 99, 100.0, 1_000_000] for i in range(20)]

        ex = _ShortHistory()
        asyncio.run(update_market_filter(state, ex))
        asyncio.run(update_market_filter(state, ex))  # 2회차 — 추가 경고 없어야

    finally:
        persistence.record_event = orig

    warns = [et for et, sev in captured
             if et == "MARKET_FILTER_UNAVAILABLE" and sev == "WARNING"]
    assert len(warns) == 1, (
        f"일봉 부족 경고가 정확히 1회가 아님(spam/누락): {captured}"
    )
    assert state.is_market_healthy is True, (
        "필터 미적용 시 동작 유지(매매 허용)되어야 — is_market_healthy 변형됨"
    )
    assert state.market_filter_unavailable_warned is True, "1회 경고 플래그 미설정"
    print("  [PASS] n30_market_filter_unavailable: 일봉 부족 1회 경고 + 동작 유지")


class _PaperReader:
    """PaperExchange 용 경량 mainnet reader 모의 (가격 동적 변경 가능)."""

    def __init__(self, price=100.0):
        self.price = price
        self.markets = {}

    async def fetch_ticker(self, symbol):
        return {"last": self.price}

    async def fetch_ohlcv(self, symbol, timeframe, limit=None):
        n = limit or 201
        return [[i, self.price, self.price, self.price, self.price, 1000.0]
                for i in range(n)]

    async def fetch_tickers(self, *a, **k):
        return {}

    async def load_markets(self, *a, **k):
        return self.markets

    def amount_to_precision(self, symbol, amount):
        return float(round(float(amount), 6))

    def price_to_precision(self, symbol, price):
        return float(round(float(price), 2))

    async def close(self):
        pass


def _paper(tmpdir, price=100.0):
    import os
    from paper_exchange import PaperExchange
    return PaperExchange(_PaperReader(price), state_path=os.path.join(tmpdir, "s.json"))


def test_paper_exchange_limit_fill():
    """paper: 지정가 매수/매도가 현재가 도달 시 즉시 전량 체결되고 잔고가 이동한다."""
    import tempfile
    import config

    with tempfile.TemporaryDirectory() as d:
        px = _paper(d, price=100.0)
        px.balance = {"USDT": 10000.0}

        # 현재가(100)에 건 buy → 즉시 체결
        o = asyncio.run(px.create_order("BTC/USDT", "limit", "buy", 1.0, 100.0))
        assert o["status"] == "closed" and o["filled"] == 1.0, o
        assert abs(px.balance["BTC"] - 1.0) < 1e-9, px.balance
        fee = 100.0 * 1.0 * config.FEE_RATE
        assert abs(px.balance["USDT"] - (10000.0 - 100.0 - fee)) < 1e-6, px.balance

        # 현재가 아래(90)에 건 buy → open 유지
        o2 = asyncio.run(px.create_order("BTC/USDT", "limit", "buy", 1.0, 90.0))
        assert o2["status"] == "open", o2
        assert len(asyncio.run(px.fetch_open_orders("BTC/USDT"))) == 1

        # 가격 하락(90) → fetch_open_orders 진입 시 체결 판정으로 사라짐
        px._reader.price = 90.0
        assert len(asyncio.run(px.fetch_open_orders("BTC/USDT"))) == 0, "도달했는데 미체결"
        assert abs(px.balance["BTC"] - 2.0) < 1e-9, px.balance

        # sell 대칭: 현재가(90) 위(95)에 건 sell → open, 가격 상승 시 체결
        os1 = asyncio.run(px.create_order("BTC/USDT", "limit", "sell", 1.0, 95.0))
        assert os1["status"] == "open", os1
        px._reader.price = 95.0
        f = asyncio.run(px.fetch_order(os1["id"], "BTC/USDT"))
        assert f["status"] == "closed" and f["filled"] == 1.0, f
        assert abs(px.balance["BTC"] - 1.0) < 1e-9, px.balance
    print("  [PASS] paper_limit_fill: buy/sell 즉시·지연 체결 + 잔고 이동")


def test_paper_exchange_market_slippage():
    """paper: 시장가는 현재가 ± PAPER_SLIPPAGE 로 즉시 체결, 수수료 USDT 차감."""
    import tempfile
    import config

    with tempfile.TemporaryDirectory() as d:
        px = _paper(d, price=100.0)
        px.balance = {"USDT": 0.0, "BTC": 2.0}

        o = asyncio.run(px.create_order("BTC/USDT", "market", "sell", 1.0))
        assert o["status"] == "closed", o
        expected_px = 100.0 * (1 - config.PAPER_SLIPPAGE)
        assert abs(o["average"] - expected_px) < 1e-9, o
        fee = expected_px * 1.0 * config.FEE_RATE
        assert abs(px.balance["USDT"] - (expected_px - fee)) < 1e-6, px.balance
        assert abs(px.balance["BTC"] - 1.0) < 1e-9, px.balance
    print("  [PASS] paper_market_slippage: 시장가 슬리피지·수수료 반영")


def test_paper_exchange_cancel():
    """paper: cancel_order 는 미체결 주문을 canceled 로 마킹하고 잔고를 변경하지 않는다."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        px = _paper(d, price=100.0)
        px.balance = {"USDT": 10000.0}
        o = asyncio.run(px.create_order("BTC/USDT", "limit", "buy", 1.0, 90.0))  # open
        before = dict(px.balance)
        c = asyncio.run(px.cancel_order(o["id"], "BTC/USDT"))
        assert c["status"] == "canceled", c
        assert px.balance == before, "취소가 잔고를 변경함"
        assert len(asyncio.run(px.fetch_open_orders("BTC/USDT"))) == 0
    print("  [PASS] paper_cancel: 미체결 취소 + 잔고 불변")


def test_paper_state_roundtrip():
    """paper: 가상 상태(잔고·미체결·next_id)가 JSON 저장/복원으로 일치한다."""
    import tempfile
    import os
    from paper_exchange import PaperExchange

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "s.json")
        px = PaperExchange(_PaperReader(100.0), state_path=path)
        px.balance = {"USDT": 5000.0}
        asyncio.run(px.create_order("BTC/USDT", "limit", "buy", 1.0, 90.0))  # open + save

        px2 = PaperExchange(_PaperReader(100.0), state_path=path)
        px2.load_state()
        assert abs(px2.balance["USDT"] - 5000.0) < 1e-9, px2.balance
        open2 = [o for o in px2.open_orders.values() if o["status"] == "open"]
        assert len(open2) == 1, px2.open_orders
        assert px2._next_id == px._next_id, (px2._next_id, px._next_id)
    print("  [PASS] paper_state_roundtrip: 잔고·미체결·next_id 복원 일치")


def test_paper_engine_integration():
    """paper: PaperExchange 를 주입한 GridEngine 이 코드 수정 없이 그리드를 배치·체결한다.

    executor 무수정 원칙 검증 — 거래소 객체 교체만으로 setup_grid + monitor_orders 동작.
    """
    import tempfile
    import persistence
    from executor import GridEngine
    from shared_state import BotState

    orig_trade = persistence.record_trade

    async def fake_trade(*a, **k):
        pass

    persistence.record_trade = fake_trade
    try:
        with tempfile.TemporaryDirectory() as d:
            px = _paper(d, price=100.0)
            px.balance = {"USDT": 100000.0}
            state = BotState()
            eng = GridEngine("BTC/USDT", px, state)

            asyncio.run(eng.setup_grid())
            assert eng.is_active, "paper 거래소로 그리드 미배치 (initial buy 미체결?)"
            assert eng.total_qty > 0, "초기 매수 미반영"
            assert px.balance.get("BTC", 0.0) > 0, "가상 BTC 미보유"

            # 1초 폴링 1싸이클이 예외 없이 동작 (가격 불변이라 추가 체결 없음)
            asyncio.run(eng.monitor_orders())
    finally:
        persistence.record_trade = orig_trade
    print("  [PASS] paper_engine_integration: setup_grid 가상 체결 + monitor 1싸이클")


def test_n2_notifier_failure_also_swallowed():
    """N2: notifier 자체 장애(텔레그램 다운 등)에도 persistence 공개 함수는 예외 미전파."""
    import persistence
    import notifier

    orig_backend = persistence._backend
    orig_notify = notifier.notify_error
    persistence._backend = _FailingBackend(RuntimeError("db down"))

    async def failing_notify(ctx, e):
        raise RuntimeError("telegram API timeout")

    notifier.notify_error = failing_notify
    raised = None
    try:
        try:
            asyncio.run(persistence.record_event(
                "testnet", "TEST", "INFO", "msg",
            ))
        except BaseException as e:
            raised = e
    finally:
        persistence._backend = orig_backend
        notifier.notify_error = orig_notify

    assert raised is None, f"notifier 실패가 전파됨: {raised!r}"
    print("  [PASS] n2_notifier_failure_swallowed: 이중 장애에도 매매 흐름 유지")


# ─────────────────────────────────────────────────────────
# Codex 적대적 리뷰 결함 4건 회귀 테스트 (F1·F2·F3·F4)
# ─────────────────────────────────────────────────────────

class MockExchangeOrderLog(MockExchange):
    """호출 순서를 기록하는 MockExchange — F1 청산 순서 검증."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.call_log: list[tuple] = []

    async def create_order(self, symbol, type_, side, amount, price=None):
        self.call_log.append(("create_order", type_, side, amount))
        return await super().create_order(symbol, type_, side, amount, price)

    async def cancel_order(self, order_id, symbol):
        self.call_log.append(("cancel_order", order_id))
        return await super().cancel_order(order_id, symbol)

    async def fetch_balance(self):
        self.call_log.append(("fetch_balance",))
        return await super().fetch_balance()


class MockExchangeWithLockedBalance(MockExchange):
    """ETH 잔고가 열린 sell 주문에 잠긴 상태 시뮬레이션 — F1 잔고 동기화 검증."""

    def __init__(self, *args, base_ccy="ETH", base_free=0.0,
                 base_locked=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._base_ccy = base_ccy
        self._base_free = base_free
        self._base_locked = base_locked

    async def fetch_balance(self):
        b = await super().fetch_balance()
        b[self._base_ccy] = {
            "free": self._base_free,
            "used": self._base_locked,
            "total": self._base_free + self._base_locked,
        }
        b["free"][self._base_ccy] = self._base_free
        b["used"][self._base_ccy] = self._base_locked
        b["total"][self._base_ccy] = self._base_free + self._base_locked
        return b

    async def cancel_order(self, order_id, symbol):
        result = await super().cancel_order(order_id, symbol)
        # 실거래 시뮬레이션: 마지막 sell 주문이 취소되면 잠긴 잔고가 free 로 환원
        if not self._open_order_ids and self._base_locked > 0:
            self._base_free += self._base_locked
            self._base_locked = 0.0
        return result

    async def create_order(self, symbol, type_, side, amount, price=None):
        # 시장가 매도: free 잔고 부족 시 거절 (실거래 Binance 동작 모사)
        if side == "sell" and type_ == "market":
            if amount > self._base_free + 1e-9:
                raise Exception(
                    f"InsufficientBalance: free={self._base_free}, requested={amount}"
                )
            self._base_free -= amount
        return await super().create_order(symbol, type_, side, amount, price)


class MockExchangePartialFill(MockExchange):
    """fetch_order 응답에 부분 체결 정보를 주입 — F2/F3 부분 체결 검증."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._partial_overrides: dict[str, dict] = {}

    def set_partial(self, order_id: str, filled: float,
                    average: float, status: str = "canceled") -> None:
        self._partial_overrides[order_id] = {
            "filled": filled, "average": average, "status": status,
        }

    async def fetch_order(self, order_id, symbol):
        order = await super().fetch_order(order_id, symbol)
        if order_id in self._partial_overrides:
            order = {**order, **self._partial_overrides[order_id]}
        return order

    async def fetch_open_orders(self, symbol=None):
        orders = await super().fetch_open_orders(symbol)
        return [o for o in orders if o["id"] not in self._partial_overrides]


# ── F1: 안전 청산 순서 (cancel_all → market sell) ─────────

def test_codex_f1_emergency_sell_cancels_first():
    """F1: emergency_sell() 호출 시 cancel_order 가 시장가 매도보다 먼저 실행."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchangeOrderLog(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f1_cancels_first_async(engine, ex))


async def _test_codex_f1_cancels_first_async(engine, ex):
    await engine.setup_grid()
    ex.call_log.clear()

    await engine.emergency_sell("F1 청산 순서 검증")

    market_sell_idx = None
    cancel_indices = []
    for i, entry in enumerate(ex.call_log):
        if entry[0] == "create_order" and entry[1] == "market" and entry[2] == "sell":
            market_sell_idx = i
        if entry[0] == "cancel_order":
            cancel_indices.append(i)

    assert market_sell_idx is not None, "market sell 호출 없음"
    assert cancel_indices, "cancel_order 호출 없음"
    assert all(c < market_sell_idx for c in cancel_indices), (
        f"cancel_order 가 market sell 뒤에 호출됨: "
        f"cancels={cancel_indices}, sell={market_sell_idx}"
    )
    print(f"  [PASS] codex_f1_cancels_first: cancels={cancel_indices}, "
          f"market_sell@{market_sell_idx}")


def test_codex_f1_emergency_sell_uses_free_balance():
    """F1: 잠긴 잔고 시나리오에서 cancel 후 free 환원 → 정상 청산."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    # ETH 1.0 보유, 모두 sell 주문에 잠겨있음 (free=0, used=1.0)
    ex = MockExchangeWithLockedBalance(
        ticker_price=100.0, usdt_balance=5000.0,
        base_ccy="ETH", base_free=0.0, base_locked=1.0,
    )
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f1_uses_free_balance_async(engine, ex, state))


async def _test_codex_f1_uses_free_balance_async(engine, ex, state):
    # setup_grid 우회 — locked balance 시나리오를 명확히 재현
    engine.total_qty = 1.0
    engine.avg_price = 100.0
    engine.is_active = True
    # 가짜 sell 주문 1건 — cancel_all 의 cancel_order 호출 대상
    fake_sell = await ex.create_order("ETH/USDT", "limit", "sell", 1.0, 105.0)
    engine.sell_orders[fake_sell["id"]] = {
        "price": 105.0, "qty": 1.0, "grid_level": 1,
    }

    result = await engine.emergency_sell("F1 잠긴 잔고")

    assert engine.total_qty == 0.0, f"청산 후 total_qty != 0: {engine.total_qty}"
    assert engine.is_active is False, "청산 후 is_active 유지됨"
    assert ex._base_locked == 0.0, "잠긴 잔고 미해제"
    print(f"  [PASS] codex_f1_uses_free_balance: locked={ex._base_locked}, "
          f"free 환원 후 정상 청산")


# ── F2: monitor_orders 의 fetch_order 재확인 ──────────────

def test_codex_f2_open_order_missing_fetches_status():
    """F2: open_orders 누락 + fetch_order=canceled 시 PnL/total_qty 변경 없음."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f2_canceled_async(engine, ex, state))


async def _test_codex_f2_canceled_async(engine, ex, state):
    # 미체결 매수 주문 1건 생성 → 외부에서 취소 (filled=0 유지)
    fake_order = await ex.create_order("ETH/USDT", "limit", "buy", 1.0, 99.0)
    engine.buy_orders[fake_order["id"]] = {
        "price": 99.0, "qty": 1.0, "grid_level": 1,
    }
    await ex.cancel_order(fake_order["id"], "ETH/USDT")

    pnl_before = state.daily_pnl
    qty_before = engine.total_qty
    sell_orders_before = len(engine.sell_orders)

    await engine.monitor_orders()

    assert engine.total_qty == qty_before, (
        f"취소된 주문으로 total_qty 오염: {qty_before} → {engine.total_qty}"
    )
    assert state.daily_pnl == pnl_before, (
        f"취소된 주문으로 PnL 오염: {pnl_before} → {state.daily_pnl}"
    )
    assert fake_order["id"] not in engine.buy_orders, (
        "취소된 주문이 buy_orders 에 잔존"
    )
    assert len(engine.sell_orders) == sell_orders_before, (
        "취소된 매수에서 잘못된 매도 그리드 생성됨"
    )
    print(f"  [PASS] codex_f2_canceled_not_filled: "
          f"PnL={state.daily_pnl}, qty={engine.total_qty} 유지")


def test_codex_f2_partial_fill_uses_actual_filled():
    """F2: fetch_order.filled=0.3, info.qty=1.0 → total_qty 가 0.3 만 증가."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchangePartialFill(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f2_partial_async(engine, ex, state))


async def _test_codex_f2_partial_async(engine, ex, state):
    fake_order = await ex.create_order("ETH/USDT", "limit", "buy", 1.0, 99.0)
    engine.buy_orders[fake_order["id"]] = {
        "price": 99.0, "qty": 1.0, "grid_level": 1,
    }
    # 부분 체결 후 취소: filled=0.3, average=99.5
    ex.set_partial(fake_order["id"], filled=0.3, average=99.5, status="canceled")

    qty_before = engine.total_qty
    cost_before = engine.avg_price * engine.total_qty

    await engine.monitor_orders()

    expected_qty = qty_before + 0.3
    assert abs(engine.total_qty - expected_qty) < 1e-6, (
        f"실제 filled 미반영: 예상 {expected_qty}, 실제 {engine.total_qty}"
    )
    # 평균가도 actual avg(99.5) 로 계산되어야 함
    expected_cost = cost_before + 99.5 * 0.3
    actual_cost = engine.avg_price * engine.total_qty
    assert abs(actual_cost - expected_cost) < 1e-3, (
        f"avg_price 계산이 info.price(99) 사용: 예상 cost {expected_cost}, "
        f"실제 {actual_cost}"
    )
    print(f"  [PASS] codex_f2_partial_fill: total_qty +0.3 정확 반영, "
          f"avg=${engine.avg_price:.2f}")


# ── F3: _limit_buy_with_retry 부분 체결 회수 ──────────────

def test_codex_f3_limit_buy_returns_partial_fill():
    """F3: 타임아웃 후 cancel + fetch_order.filled=0.6 → (avg, 0.6) 반환."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchangePartialFill(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f3_partial_async(engine, ex))


async def _test_codex_f3_partial_async(engine, ex):
    engine.base_price = 99.0  # ticker(100) 보다 낮음 → 즉시 체결 안 됨

    async def trigger_partial():
        await asyncio.sleep(1.0)
        for oid in list(ex._open_order_ids):
            ex.set_partial(oid, filled=0.6, average=99.5, status="canceled")
            await ex.cancel_order(oid, "ETH/USDT")

    asyncio.create_task(trigger_partial())

    fill_price, fill_qty = await engine._limit_buy_with_retry(
        buy_usdt=100.0, max_attempts=3, timeout=3,
    )

    assert fill_qty > 0, "부분 체결 회수 실패 — (0, 0) 반환됨"
    assert abs(fill_qty - 0.6) < 1e-6, f"부분 체결 수량 부정확: {fill_qty}"
    assert abs(fill_price - 99.5) < 1e-6, f"부분 체결 평균가 부정확: {fill_price}"
    print(f"  [PASS] codex_f3_partial_recovered: ({fill_price}, {fill_qty})")


def test_codex_f3_limit_buy_full_zero_retries():
    """F3 회귀 방지: filled=0 케이스는 기존처럼 (0.0, 0.0) 반환."""
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)
    asyncio.run(_test_codex_f3_zero_async(engine, ex))


async def _test_codex_f3_zero_async(engine, ex):
    engine.base_price = 99.0

    async def trigger_cancel():
        await asyncio.sleep(1.0)
        for oid in list(ex._open_order_ids):
            await ex.cancel_order(oid, "ETH/USDT")

    asyncio.create_task(trigger_cancel())

    fill_price, fill_qty = await engine._limit_buy_with_retry(
        buy_usdt=100.0, max_attempts=1, timeout=3,
    )

    assert (fill_price, fill_qty) == (0.0, 0.0), (
        f"filled=0 케이스에서 회귀 (F3 패치가 기존 동작 깨뜨림): "
        f"({fill_price}, {fill_qty})"
    )
    print(f"  [PASS] codex_f3_zero_retries: filled=0 → (0.0, 0.0) 유지")


# ── F4: 텔레그램 권한 필터 ────────────────────────────────

def test_codex_f4_unauthorized_chat_rejected():
    """F4: filters.Chat 이 TELEGRAM_CHAT_ID_INT 와 다른 chat 의 명령을 거부."""
    from telegram.ext import filters
    import config

    # filters.Chat 의 chat_ids 속성 검증 (frozenset[int])
    AUTHORIZED = 123456789
    chat_filter = filters.Chat(chat_id=AUTHORIZED)
    assert AUTHORIZED in chat_filter.chat_ids, "허가된 chat_id 가 filter 에 없음"
    assert 999999 not in chat_filter.chat_ids, "비인가 chat_id 가 filter 에 포함"

    # config 의 TELEGRAM_CHAT_ID_INT 변환 로직 검증
    assert hasattr(config, "TELEGRAM_CHAT_ID_INT"), (
        "config 에 TELEGRAM_CHAT_ID_INT 누락 — F4 패치 미적용"
    )
    if config.TELEGRAM_CHAT_ID is not None:
        try:
            expected = int(config.TELEGRAM_CHAT_ID)
            assert config.TELEGRAM_CHAT_ID_INT == expected, (
                f"TELEGRAM_CHAT_ID_INT 변환 오류: "
                f"{config.TELEGRAM_CHAT_ID_INT} != {expected}"
            )
        except (TypeError, ValueError):
            # str 변환 불가 시 None — 부팅 시점에 봇이 안전하게 멈춤
            assert config.TELEGRAM_CHAT_ID_INT is None

    print(f"  [PASS] codex_f4_filter: chat_ids={chat_filter.chat_ids}, "
          f"config.TELEGRAM_CHAT_ID_INT={config.TELEGRAM_CHAT_ID_INT}")


# ─────────────────────────────────────────────────────────
# Phase 3 통합 테스트 (온라인 — 실제 바이낸스 API 호출)
# ─────────────────────────────────────────────────────────

async def test_scan_online():
    """실제 바이낸스 API를 사용한 스캐너 통합 테스트."""
    from screener import _scan

    print("\n[통합 테스트] 바이낸스 실시간 스캔 시작 (수십 초 소요)...")
    ex = ccxt_async.binance({
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET_KEY,
        "enableRateLimit": True,
    })
    try:
        candidates = await _scan(ex)
        print(f"  후보 {len(candidates)}개:")
        for c in candidates:
            print(f"    {c['symbol']}: score={c['score']:.3f}, "
                  f"ATR={c['atr_rate']*100:.2f}%, "
                  f"거래량=${c['volume']:,.0f}, "
                  f"현재가=${c['last']:,.4f}")

        # 체크리스트
        if candidates:
            for c in candidates:
                from config import ATR_MIN_RATE, ATR_MAX_RATE
                assert ATR_MIN_RATE <= c["atr_rate"] <= ATR_MAX_RATE, \
                    f"{c['symbol']} ATR 범위 초과: {c['atr_rate']}"
            print("  [PASS] 모든 후보의 ATR 비율 범위 내")
        else:
            print("  [INFO] 조건 충족 코인 없음 (시장 상황에 따라 정상)")
    finally:
        await ex.close()


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "unit"

    def _run_phase3():
        print("=== Phase 3 단위 테스트 ===")
        test_calc_atr()
        test_is_pumped()
        test_pre_filter()
        print("Phase 3 단위 테스트 통과!")

    def _run_phase4():
        print("=== Phase 4 단위 테스트 ===")
        test_validate_fees()
        test_calc_position_size()
        test_setup_grid()
        test_handle_buy_fill()
        test_handle_sell_fill()
        test_stop_loss()
        test_market_filter()
        test_regrid()
        test_run_executor_kill()
        print("Phase 4 단위 테스트 통과!")

    def _run_bugfix_phase67():
        # executor 를 기본 config 값(KRW_RATE=1350, SEED=3,000,000)으로 먼저 로드.
        # 이후 config 값을 바꿔도 executor 내부 바인딩은 바뀌지 않음 → A1 회귀 보장.
        import executor  # noqa: F401
        # Phase 4 `test_run_executor_kill` 이 `update_krw_rate()` 로 실제 업비트 API 를
        # 타서 `config.KRW_RATE` 를 실시간 환율로 갱신할 수 있음. bugfix suite 은
        # KRW_RATE=1350 을 전제로 기대값을 계산하므로 진입 시 기본값으로 복원한다.
        import config as _cfg
        _cfg.KRW_RATE = 1350
        _cfg.SEED = 3_000_000
        print("=== 버그픽스 단위 테스트 ===")
        test_a1_krw_rate_runtime_change()
        test_a1_seed_runtime_change()
        test_a2_lot_size_precision()
        test_a3_regrid_sells_existing_position()
        test_a4_emergency_sell_records_pnl()
        test_a5_daily_reset()
        test_a8_setup_grid_buy_fee_deduction()
        test_a8_grid_rotation_pnl_accuracy()
        test_c1_setup_grid_uses_limit_buy()
        test_c2_recover_cancels_open_orders()
        test_c2_recover_liquidates_non_usdt_positions()
        test_c2_recover_skips_stablecoins_and_bnb()
        test_c2_recover_skips_dust()
        test_b1_external_cancel_not_counted_as_fill()
        test_b3_setup_grid_sell_qty_within_holdings()
        test_b3_handle_buy_fill_caps_sell_qty()
        test_h2_dedup_suppresses_duplicate()
        test_h2_min_interval_enforced()
        test_b5_stability_score_minmax_normalized()
        print("버그픽스 단위 테스트 통과!")

        print("\n=== Phase 6: MODE 분기 + SQLite 영속화 ===")
        test_mode_branch_live()
        test_mode_branch_testnet()
        test_mode_branch_invalid()
        test_persistence_init_and_roundtrip()
        test_persistence_equity_and_events()
        test_record_trade_hook_called_on_sell()
        print("Phase 6 단위 테스트 통과!")

        print("\n=== Phase 7: N3/N4 호출부 (equity + events) ===")
        test_n3_snapshot_equity_records_positions()
        test_n4_market_filter_logs_transition_event()
        test_n4_recover_state_logs_event()
        test_n5_recover_logs_trade_on_liquidation()
        test_n5b_recover_throttles_between_sells()
        print("Phase 7 N 트랙 단위 테스트 통과!")

        print("\n=== Phase 7: N1 Supabase → SQLite fallback ===")
        test_n1_supabase_init_failure_falls_back_to_sqlite()
        test_n1_fallback_reason_exposed_for_alert()
        test_n1_sqlite_native_failure_not_swallowed()
        print("Phase 7 N1 fallback 단위 테스트 통과!")

        print("\n=== Phase 7: N2 persistence 공개 함수 자체 격리 ===")
        test_n2_record_trade_swallows_backend_error()
        test_n2_record_event_swallows_backend_error()
        test_n2_record_equity_snapshot_swallows_backend_error()
        test_n2_notifier_failure_also_swallowed()
        print("Phase 7 N2 자체 격리 단위 테스트 통과!")

        print("\n=== Phase 7: N12+N19+N20 안전 패치 (executor hang 재발 방지) ===")
        test_n12_service_uses_journald()
        test_n19_supervise_cancels_hung_executor()
        test_n19_supervise_normal_executor_no_false_trigger()
        test_n25_supervise_restarts_when_snapshot_stale()
        test_n25_snapshot_and_trade_mark_progress()
        test_n20_retry_api_times_out_on_hung_call()
        test_n20_retry_api_normal_call_unaffected()
        print("Phase 7 N12+N19+N20+N25 안전 패치 단위 테스트 통과!")

        print("\n=== Phase 7: N22 init_db 결과 journal 가시화 ===")
        test_n22_init_db_result_visible_in_journal()
        print("Phase 7 N22 가시성 패치 단위 테스트 통과!")

        print("\n=== Phase 7: N26 DAILY_STOP / KILL_SWITCH spam 방지 ===")
        test_n26_daily_stop_no_spam_when_emergency_sell_raises()
        test_n26_kill_switch_no_spam_when_emergency_sell_raises()
        print("Phase 7 N26 spam 방지 단위 테스트 통과!")

        print("\n=== Phase 7: N27 DAILY_STOP 봇 종료 방지 (자동 재개) ===")
        test_n27_daily_stop_does_not_terminate_supervisor()
        print("Phase 7 N27 자동 재개 단위 테스트 통과!")

        print("\n=== Phase 7: N28 Supabase pgbouncer 호환 (statement_cache_size=0) ===")
        test_n28_supabase_pool_disables_statement_cache()
        print("Phase 7 N28 silent fallback 방지 단위 테스트 통과!")

        print("\n=== Phase 7: N29 KILL_SWITCH 가시성·사망 알림 ===")
        test_n29b_log_event_critical_emits_stdout()
        test_n29a_notify_death_script_valid()
        print("Phase 7 N29 가시성·사망 알림 단위 테스트 통과!")

        print("\n=== Phase 7: N30 grid-setup idle + 200MA 필터 미적용 가시화 ===")
        test_n30_grid_setup_idle_alerts_after_threshold()
        test_n30_market_filter_unavailable_warns_once()
        print("Phase 7 N30 진입 실패 idle·필터 가시화 단위 테스트 통과!")

        print("\n=== Phase 7: Paper 모드 (mainnet 실시세 + 로컬 가상 체결) ===")
        test_paper_exchange_limit_fill()
        test_paper_exchange_market_slippage()
        test_paper_exchange_cancel()
        test_paper_state_roundtrip()
        test_paper_engine_integration()
        print("Phase 7 Paper 모드 단위 테스트 통과!")

        print("\n=== Codex 적대적 리뷰 결함 4건 회귀 (F1·F2·F3·F4) ===")
        test_codex_f1_emergency_sell_cancels_first()
        test_codex_f1_emergency_sell_uses_free_balance()
        test_codex_f2_open_order_missing_fetches_status()
        test_codex_f2_partial_fill_uses_actual_filled()
        test_codex_f3_limit_buy_returns_partial_fill()
        test_codex_f3_limit_buy_full_zero_retries()
        test_codex_f4_unauthorized_chat_rejected()
        print("Codex 적대적 리뷰 4건 회귀 테스트 통과!")

    if mode == "unit":
        # 기본 실행: 모든 오프라인 단위 테스트 (Phase 3/4 + bugfix + Phase 6/7).
        # C1 리팩터 안전망 — `python test.py` 한 번으로 전 회귀 커버.
        _run_phase3()
        print()
        _run_phase4()
        print()
        _run_bugfix_phase67()
        print("\n모든 단위 테스트 통과!")

    elif mode == "unit3":
        _run_phase3()

    elif mode == "unit4":
        _run_phase4()

    elif mode == "bugfix":
        # 하위 호환 — bugfix + Phase 6/7 만 실행 (Phase 3/4 제외).
        _run_bugfix_phase67()

    elif mode == "scan":
        # 통합 테스트 실행 (온라인)
        asyncio.run(test_scan_online())
