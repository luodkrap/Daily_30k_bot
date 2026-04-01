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
