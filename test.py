import os
import asyncio
import ccxt
import ccxt.async_support as ccxt_async
import requests
from dotenv import load_dotenv

load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

exchange = ccxt.binance({
    "apiKey": BINANCE_API_KEY,
    "secret": BINANCE_SECRET_KEY,
    "enableRateLimit": True,
})


def get_btc_price():
    ticker = exchange.fetch_ticker("BTC/USDT")
    price = ticker["last"]
    return f"{price:,.2f}"


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()


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
        return {"USDT": {"free": self._usdt_balance}}

    async def create_order(self, symbol, type_, side, amount, price=None):
        self._order_id += 1
        oid = str(self._order_id)
        fill_price = price if price else self._ticker_price
        order = {
            "id": oid,
            "symbol": symbol,
            "type": type_,
            "side": side,
            "amount": amount,
            "price": price,
            "filled": amount,
            "average": fill_price,
            "status": "closed" if type_ == "market" else "open",
        }
        self._orders[oid] = order
        if order["status"] == "open":
            self._open_order_ids.add(oid)
        return order

    async def fetch_open_orders(self, symbol):
        return [self._orders[oid] for oid in self._open_order_ids if oid in self._orders]

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

    # 2. 초기 시장가 매수 실행됨 (보유량 > 0)
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

    sell_oid = list(engine.sell_orders.keys())[0]
    sell_info = engine.sell_orders[sell_oid]
    sell_price = sell_info["price"]
    sell_qty = sell_info["qty"]
    ex.simulate_fill(sell_oid)
    await engine.monitor_orders()

    # net_usdt = (sell_price - avg_price) * qty - fees
    gross_usdt = (sell_price - engine.avg_price) * sell_qty
    fee_usdt = (sell_price * sell_qty + engine.avg_price * sell_qty) * 0.001
    net_usdt = gross_usdt - fee_usdt
    expected_krw = net_usdt * 2700  # config.KRW_RATE = 2700 반영 기대

    assert abs(state.daily_pnl - expected_krw) < 0.1, (
        f"KRW_RATE 런타임 변경 미반영: "
        f"expected {expected_krw:.2f}원 (rate=2700), "
        f"got {state.daily_pnl:.2f}원"
    )
    print(f"  [PASS] a1_krw_rate_runtime_change: {state.daily_pnl:.0f}원 (rate=2700 반영)")


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

    mode = sys.argv[1] if len(sys.argv) > 1 else "basic"

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
        print("버그픽스 단위 테스트 통과!")

    elif mode == "scan":
        # 통합 테스트 실행 (온라인)
        asyncio.run(test_scan_online())

    else:
        # 기존 기본 테스트 (바이낸스 연결 + 텔레그램)
        print("바이낸스 연결 중...")
        btc_price = get_btc_price()
        print(f"현재 BTC 가격: ${btc_price}")

        message = f"도울 님, 연결 성공! 현재 비트코인 가격은 ${btc_price}입니다."
        send_telegram_message(message)
        print("텔레그램 메시지 전송 완료!")
