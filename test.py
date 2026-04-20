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
        order = {
            "id": oid,
            "symbol": symbol,
            "type": type_,
            "side": side,
            "amount": amount,
            "price": price,
            "filled": amount,
            "average": fill_price,
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
        """테스트 헬퍼: 지정가 주문을 체결 상태로 변경."""
        if order_id in self._orders:
            self._orders[order_id]["status"] = "closed"
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

    if mode == "unit":
        # 단위 테스트만 실행 (오프라인)
        print("=== Phase 3 단위 테스트 ===")
        test_calc_atr()
        test_is_pumped()
        test_pre_filter()
        print("Phase 3 단위 테스트 통과!\n")

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
        print("Phase 4 단위 테스트 통과!\n")

        print("모든 단위 테스트 통과!")

    elif mode == "unit4":
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

    elif mode == "bugfix":
        # executor를 기본 config 값(KRW_RATE=1350, SEED=3,000,000)으로 먼저 로드
        # 이후 config 값을 바꿔도 executor 내 바인딩은 바뀌지 않음 → 버그 재현
        import executor  # noqa: F401
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

    elif mode == "scan":
        # 통합 테스트 실행 (온라인)
        asyncio.run(test_scan_online())
