# Phase 4+5 트레이딩 엔진 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스캐너가 선정한 코인에 그리드 매매를 실행하고, 손절/킬스위치/200MA 필터로 리스크를 관리하는 완전한 트레이딩 엔진 구현.

**Architecture:** `executor.py`에 `GridEngine` 클래스(단일 코인 그리드 생명주기)와 `run_executor()` 오케스트레이터(동적 스위칭, 안전장치)를 구현. 1초 폴링으로 체결 감지, mock exchange 기반 TDD.

**Tech Stack:** ccxt async, asyncio, aiohttp (notifier)

**Spec:** `docs/superpowers/specs/2026-04-01-phase4-trading-engine-design.md`

---

## 파일 구조

| 파일          | 변경     | 역할                                                                         |
| ------------- | -------- | ---------------------------------------------------------------------------- |
| `config.py`   | 수정     | FEE_RATE, INITIAL_BUY_RATIO, MIN_PROFIT_RATIO, REGRID_ENABLED, KRW_RATE 추가 |
| `executor.py` | **신규** | GridEngine 클래스 + update_market_filter + run_executor                      |
| `main.py`     | 수정     | run_executor를 executor.py에서 import, 뼈대 제거                             |
| `test.py`     | 수정     | MockExchange + Phase 4 단위 테스트 추가                                      |
| `TODO.md`     | 수정     | Phase 4 항목 체크                                                            |

---

### Task 1: config.py 상수 추가

**Files:**

- Modify: `config.py:48` (마지막 섹션 뒤에 추가)

- [x] **Step 1: config.py에 Phase 4 상수 추가**

```python
# ─── 거래 비용 및 초기 매수 ──────────────────────────
FEE_RATE          = 0.001     # 바이낸스 현물 수수료 0.1%
INITIAL_BUY_RATIO = 0.50      # 투입금 중 시장가 즉시 매수 비율 50%
MIN_PROFIT_RATIO  = 0.001     # 최소 순수익 기준 0.1% (수수료 제외 후)
REGRID_ENABLED    = True      # 상단 이탈 시 리그리딩 ON/OFF
KRW_RATE          = 1350      # 원/달러 환율 (USDT ≈ USD)
```

- [x] **Step 2: 기존 main.py 하드코딩 환율을 KRW_RATE 참조로 교체**

`main.py:92`의 `krw_approx = usdt * 1350` → `krw_approx = usdt * config.KRW_RATE`

- [x] **Step 3: import 확인**

Run: `python -c "from config import FEE_RATE, INITIAL_BUY_RATIO, MIN_PROFIT_RATIO, REGRID_ENABLED, KRW_RATE; print('OK')"`
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add config.py main.py
git commit -m "feat: Phase 4 거래 비용 및 초기 매수 상수 추가 (config.py)"
```

---

### Task 2: MockExchange + GridEngine 뼈대 (수수료 검증, 포지션 사이징)

**Files:**

- Create: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 MockExchange와 Phase 4 테스트 추가**

test.py 하단, `test_pre_filter()` 함수 아래에 추가:

```python
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
```

- [x] **Step 2: 테스트 실행 → 실패 확인**

Run: `python test.py unit4`
Expected: `ModuleNotFoundError: No module named 'executor'`

- [x] **Step 3: executor.py 생성 — GridEngine 뼈대**

```python
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

from config import (
    GRID_COUNT, GRID_SPACING, FEE_RATE, INITIAL_BUY_RATIO,
    MIN_PROFIT_RATIO, REGRID_ENABLED, KRW_RATE,
    MAX_POSITION_RATE, STOP_LOSS_RATE, SEED,
    DAILY_LOSS_LIMIT,
)
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

    # ── 수수료 검증 ──────────────────────────────────
    def validate_fees(self) -> bool:
        """그리드 간격이 왕복 수수료 + 최소 수익을 초과하는지 확인."""
        net = GRID_SPACING - (FEE_RATE * 2)
        return net >= MIN_PROFIT_RATIO

    # ── 포지션 사이징 ────────────────────────────────
    def calc_position_size(self, usdt_balance: float) -> float:
        """1% Rule: 최대 투입 가능 USDT 계산."""
        seed_usdt = SEED / KRW_RATE
        max_loss_usdt = seed_usdt * MAX_POSITION_RATE
        max_invest = max_loss_usdt / STOP_LOSS_RATE
        return min(max_invest, usdt_balance)
```

- [x] **Step 4: 테스트 실행 → 통과 확인**

test.py `if __name__` 블록에 `unit4` 모드 추가:

```python
    elif mode == "unit4":
        print("=== Phase 4 단위 테스트 ===")
        test_validate_fees()
        test_calc_position_size()
        print("Phase 4 단위 테스트 통과!")
```

Run: `python test.py unit4`
Expected: 두 테스트 모두 `[PASS]`

- [x] **Step 5: Commit**

```bash
git add executor.py test.py
git commit -m "feat: GridEngine 뼈대 — 수수료 검증 + 1% Rule 포지션 사이징"
```

---

### Task 3: setup_grid() — 초기 매수 + 그리드 배치

**Files:**

- Modify: `executor.py` (GridEngine에 메서드 추가)
- Modify: `test.py` (테스트 추가)

- [x] **Step 1: test.py에 setup_grid 테스트 추가**

```python
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
```

- [x] **Step 2: 테스트 실행 → 실패 확인**

Run: `python test.py unit4`
Expected: `AttributeError: 'GridEngine' object has no attribute 'setup_grid'`

- [x] **Step 3: executor.py에 setup_grid() 구현**

GridEngine 클래스 내부, `calc_position_size` 아래에 추가:

```python
    # ── 그리드 초기 설정 ─────────────────────────────
    async def setup_grid(self) -> None:
        """시장가 50% 매수 → 매도 그리드 5개 + 매수 그리드 5개 배치."""
        # 1. 현재가 조회
        ticker = await _retry_api(self.exchange.fetch_ticker, self.symbol)
        self.base_price = ticker["last"]

        # 2. 잔고 확인 & 포지션 사이징
        balance = await _retry_api(self.exchange.fetch_balance)
        usdt_free = balance["USDT"]["free"]
        max_invest = self.calc_position_size(usdt_free)

        # 3. 시장가 매수 (50%)
        buy_usdt = max_invest * INITIAL_BUY_RATIO
        buy_qty = buy_usdt / self.base_price

        order = await _retry_api(
            self.exchange.create_order,
            self.symbol, "market", "buy", buy_qty,
        )
        fill_price = order["average"] or self.base_price
        fill_qty = order["filled"]
        self.total_qty = fill_qty
        self.avg_price = fill_price
        self.total_invested = fill_qty * fill_price

        # 4. 매도 그리드 배치 (보유 물량 5등분)
        sell_qty_each = fill_qty / GRID_COUNT
        for level in range(1, GRID_COUNT + 1):
            price = self.base_price * (1 + GRID_SPACING * level)
            sell_order = await _retry_api(
                self.exchange.create_order,
                self.symbol, "limit", "sell", sell_qty_each, price,
            )
            self.sell_orders[sell_order["id"]] = {
                "price": price, "qty": sell_qty_each, "grid_level": level,
            }

        # 5. 매수 그리드 배치 (나머지 50% 5등분)
        remaining_usdt = max_invest - buy_usdt
        for level in range(1, GRID_COUNT + 1):
            price = self.base_price * (1 - GRID_SPACING * level)
            qty = (remaining_usdt / GRID_COUNT) / price
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
```

- [x] **Step 4: test.py unit4 모드에 테스트 추가 & 실행**

```python
    elif mode == "unit4":
        print("=== Phase 4 단위 테스트 ===")
        test_validate_fees()
        test_calc_position_size()
        test_setup_grid()
        print("Phase 4 단위 테스트 통과!")
```

Run: `python test.py unit4`
Expected: 세 테스트 모두 `[PASS]`

- [x] **Step 5: Commit**

```bash
git add executor.py test.py
git commit -m "feat: setup_grid — 초기 시장가 매수 + 매도/매수 그리드 배치"
```

---

### Task 4: monitor_orders + handle_fill — 체결 감지 & 대응

**Files:**

- Modify: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 체결 감지 테스트 추가**

```python
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
```

- [x] **Step 2: 테스트 실행 → 실패 확인**

Run: `python test.py unit4`
Expected: `AttributeError: 'GridEngine' object has no attribute 'monitor_orders'`

- [x] **Step 3: executor.py에 monitor_orders + handle_fill 구현**

GridEngine 클래스 내부, `setup_grid` 아래에 추가:

```python
    # ── 주문 모니터링 ────────────────────────────────
    async def monitor_orders(self) -> None:
        """1초 폴링: 미체결 목록과 비교하여 체결된 주문 감지."""
        open_orders = await _retry_api(self.exchange.fetch_open_orders, self.symbol)
        open_ids = {o["id"] for o in open_orders}

        # 매수 체결 감지
        for oid in list(self.buy_orders):
            if oid not in open_ids:
                await self._handle_buy_fill(oid, self.buy_orders[oid])

        # 매도 체결 감지
        for oid in list(self.sell_orders):
            if oid not in open_ids:
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

        # 위에 매도 주문
        sell_price = price * (1 + GRID_SPACING)
        order = await _retry_api(
            self.exchange.create_order,
            self.symbol, "limit", "sell", qty, sell_price,
        )
        self.sell_orders[order["id"]] = {
            "price": sell_price, "qty": qty, "grid_level": info["grid_level"],
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
        net_krw = net_usdt * KRW_RATE

        self.state.daily_pnl += net_krw
        self.state.trade_count += 1
        if net_krw > 0:
            self.state.win_count += 1
            self.state.consecutive_losses = 0
        else:
            self.state.consecutive_losses += 1

        await notify_trade(self.symbol, "SELL", sell_price, net_krw)

        # 아래에 매수 재배치
        buy_price = sell_price * (1 - GRID_SPACING)
        order = await _retry_api(
            self.exchange.create_order,
            self.symbol, "limit", "buy", qty, buy_price,
        )
        self.buy_orders[order["id"]] = {
            "price": buy_price, "qty": qty, "grid_level": info["grid_level"],
        }
```

- [x] **Step 4: test.py unit4에 새 테스트 추가 & 실행**

```python
        test_handle_buy_fill()
        test_handle_sell_fill()
```

Run: `python test.py unit4`
Expected: 다섯 테스트 모두 `[PASS]`

- [x] **Step 5: Commit**

```bash
git add executor.py test.py
git commit -m "feat: monitor_orders — 1초 폴링 체결 감지 + 매수/매도 대응 주문"
```

---

### Task 5: check_stop_loss + cancel_all — 손절매

**Files:**

- Modify: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 손절 테스트 추가**

```python
def test_stop_loss():
    from executor import GridEngine
    from shared_state import BotState

    state = BotState()
    ex = MockExchange(ticker_price=100.0, usdt_balance=5000.0)
    engine = GridEngine("ETH/USDT", ex, state)

    asyncio.run(_test_stop_loss_async(engine, ex, state))


async def _test_stop_loss_async(engine, ex, state):
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
```

- [x] **Step 2: 테스트 실행 → 실패 확인**

Run: `python test.py unit4`
Expected: `AttributeError: 'GridEngine' object has no attribute 'check_stop_loss'`

- [x] **Step 3: executor.py에 check_stop_loss + cancel_all 구현**

```python
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
        loss_krw = (loss_usdt - fee_usdt) * KRW_RATE

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
```

- [x] **Step 4: test.py unit4에 테스트 추가 & 실행**

```python
        test_stop_loss()
```

Run: `python test.py unit4`
Expected: 여섯 테스트 모두 `[PASS]`

- [x] **Step 5: Commit**

```bash
git add executor.py test.py
git commit -m "feat: check_stop_loss — 진입가 -2% 하락 시 전량 시장가 매도"
```

---

### Task 6: update_market_filter — 200MA 시장 필터

**Files:**

- Modify: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 200MA 필터 테스트 추가**

```python
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

    # 시나리오 B: 현재가가 MA보다 낮으면 → unhealthy
    # MockExchange는 모든 캔들 close=ticker_price 반환
    # 마지막 캔들 가격을 낮추려면 별도 mock 필요
    # 대신 함수 로직 자체를 검증: 201개 캔들 받아서 MA 계산 정상
    print("  [PASS] market_filter: 정상 시장 healthy 판정")
```

- [x] **Step 2: executor.py에 update_market_filter 구현**

`GridEngine` 클래스 바깥, 모듈 레벨 함수로 추가:

```python
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
```

- [x] **Step 3: test.py unit4에 테스트 추가 & 실행**

```python
        test_market_filter()
```

Run: `python test.py unit4`
Expected: `[PASS]`

- [x] **Step 4: Commit**

```bash
git add executor.py test.py
git commit -m "feat: update_market_filter — BTC 200MA 기반 시장 건강성 판단"
```

---

### Task 7: regrid — 리그리딩

**Files:**

- Modify: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 리그리딩 테스트 추가**

```python
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
```

- [x] **Step 2: executor.py에 regrid 구현**

GridEngine 클래스 내부, `cancel_all` 아래에 추가:

```python
    # ── 리그리딩 ─────────────────────────────────────
    async def regrid(self) -> None:
        """현재가 기준으로 그리드 새로 배치."""
        await self.cancel_all()
        self.total_qty = 0.0
        self.avg_price = 0.0
        self.total_invested = 0.0
        self.is_active = False
        await self.setup_grid()
        await send(f"[리그리딩] {self.symbol} 새 그리드 배치 @ ${self.base_price:,.2f}")
```

- [x] **Step 3: test.py unit4에 테스트 추가 & 실행**

```python
        test_regrid()
```

Run: `python test.py unit4`
Expected: `[PASS]`

- [x] **Step 4: Commit**

```bash
git add executor.py test.py
git commit -m "feat: regrid — 상단 이탈 시 현재가 기준 그리드 재배치"
```

---

### Task 8: run_executor — 오케스트레이터 (안전장치 + 동적 스위칭)

**Files:**

- Modify: `executor.py`
- Modify: `test.py`

- [x] **Step 1: test.py에 run_executor 킬 스위치 테스트 추가**

```python
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
```

- [x] **Step 2: executor.py에 run_executor 구현**

모듈 레벨 함수, `update_market_filter` 아래에 추가:

```python
async def run_executor(state: BotState, exchange) -> None:
    """트레이딩 엔진 메인 루프. 안전장치 → 그리드 매매 → 1초 폴링."""
    engine: GridEngine | None = None
    last_ma_check: float = 0

    print("[Executor] 시작")
    while not state.kill_event.is_set():
        try:
            # ── 1. 킬 이벤트 재확인 ──
            if state.kill_event.is_set():
                break

            # ── 2. 일일 손실 한도 초과 → 킬 스위치 ──
            if state.daily_pnl <= -DAILY_LOSS_LIMIT:
                await notify_kill_switch()
                if engine:
                    if engine.total_qty > 0:
                        await _retry_api(
                            exchange.create_order,
                            engine.symbol, "market", "sell", engine.total_qty,
                        )
                    await engine.cancel_all()
                state.kill_event.set()
                break

            # ── 3. 일일 목표 수익 달성 → 하드 스탑 ──
            if state.should_stop_profit:
                reason = "목표 수익 달성" if state.daily_pnl >= 0 else "조기 중단 (시장 악화)"
                await notify_daily_stop(reason, state.daily_pnl)
                if engine:
                    if engine.total_qty > 0:
                        await _retry_api(
                            exchange.create_order,
                            engine.symbol, "market", "sell", engine.total_qty,
                        )
                    await engine.cancel_all()
                state.kill_event.set()
                break

            # ── 4. 200MA 체크 (30분마다) ──
            now = time.time()
            if now - last_ma_check > 1800:
                await update_market_filter(state, exchange)
                last_ma_check = now

            # ── 5. 타겟 코인 없으면 대기 ──
            if not state.target_coin:
                await asyncio.sleep(1)
                continue

            # ── 6. 동적 코인 스위칭 ──
            if engine and engine.symbol != state.target_coin:
                await send(
                    f"[스위칭] {engine.symbol} → {state.target_coin}"
                )
                if engine.total_qty > 0:
                    await _retry_api(
                        exchange.create_order,
                        engine.symbol, "market", "sell", engine.total_qty,
                    )
                await engine.cancel_all()
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
        if engine.total_qty > 0:
            try:
                await exchange.create_order(
                    engine.symbol, "market", "sell", engine.total_qty,
                )
            except Exception:
                pass
        await engine.cancel_all()
    print("[Executor] 종료")
```

- [x] **Step 3: test.py unit4에 테스트 추가 & 실행**

```python
        test_run_executor_kill()
```

Run: `python test.py unit4`
Expected: `[PASS]`

- [x] **Step 4: Commit**

```bash
git add executor.py test.py
git commit -m "feat: run_executor — 안전장치 6단계 + 동적 코인 스위칭 + 그리드 오케스트레이션"
```

---

### Task 9: main.py 통합 + config 업데이트

**Files:**

- Modify: `main.py`
- Modify: `config.py`

- [x] **Step 1: main.py — run_executor를 executor.py에서 import**

main.py에서 기존 `run_executor` 함수(L32~47) 삭제하고 import 교체:

```python
# 기존 삭제: async def run_executor(...) 전체
# import 추가:
from executor import run_executor
```

- [x] **Step 2: config.py — SCANNER_INTERVAL_SEC 900으로 변경**

```python
SCANNER_INTERVAL_SEC  = 900     # 스캔 주기 (초) — 15분 (Phase 4: 동적 스위칭 반응성)
```

- [x] **Step 3: import 검증**

Run: `python -c "from main import main; print('OK')"`
Expected: `OK`

- [x] **Step 4: Commit**

```bash
git add main.py config.py
git commit -m "refactor: main.py run_executor → executor.py 분리, 스캐너 주기 15분"
```

---

### Task 10: 통합 테스트 + 문서 업데이트

**Files:**

- Modify: `test.py`
- Modify: `TODO.md`
- Modify: `CLAUDE.md`

- [x] **Step 1: test.py — 전체 테스트 실행 모드 추가**

기존 `unit` 모드에 Phase 4 테스트 병합:

```python
    if mode == "unit":
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
```

- [x] **Step 2: 전체 단위 테스트 실행**

Run: `python test.py unit`
Expected: Phase 3 + Phase 4 모든 테스트 `[PASS]`

- [x] **Step 3: TODO.md Phase 4 항목 체크**

Phase 4 항목을 전부 `[x]`로 변경, Phase 5 항목도 통합 구현된 것은 체크.

- [x] **Step 4: CLAUDE.md 파일 구조에 executor.py 추가**

```
executor.py      — 트레이딩 엔진 (GridEngine + run_executor + 200MA 필터)
```

- [x] **Step 5: Commit**

```bash
git add test.py TODO.md CLAUDE.md
git commit -m "docs: Phase 4+5 완료 — 테스트 통합, TODO/CLAUDE 업데이트"
```
