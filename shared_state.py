import asyncio
from dataclasses import dataclass, field


@dataclass
class BotState:
    # ─── 킬 스위치 (최우선) ────────────────────────────────
    kill_event: asyncio.Event = field(default_factory=asyncio.Event)

    # ─── 스캐너 → 엔진 ────────────────────────────────────
    target_coin: str = ""               # 현재 타겟 코인 (예: "ETH/USDT")
    screener_candidates: list = field(default_factory=list)

    # ─── 포지션 상태 ───────────────────────────────────────
    current_position: dict = field(default_factory=dict)
    grid_orders: list = field(default_factory=list)

    # ─── 일일 손익 ─────────────────────────────────────────
    daily_pnl: float = 0.0              # 오늘 누적 손익 (KRW)
    trade_count: int = 0                # 오늘 거래 횟수
    win_count: int = 0                  # 오늘 수익 거래 횟수

    # ─── 시장 상태 ─────────────────────────────────────────
    is_market_healthy: bool = True      # BTC 200MA, 승률 등 종합 판단
    consecutive_losses: int = 0         # 연속 손실 횟수

    # ─── 봇 상태 ──────────────────────────────────────────
    is_running: bool = False
    exchange: object = None  # ccxt exchange 인스턴스 (seed_cmd에서 잔고 조회용)

    @property
    def win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return self.win_count / self.trade_count

    @property
    def should_stop_profit(self) -> bool:
        """일일 수익 중단 조건 확인 (C형 로직)"""
        from config import DAILY_TARGET, DAILY_MIN_PROFIT
        if self.daily_pnl >= DAILY_TARGET:
            return True
        if self.daily_pnl >= DAILY_MIN_PROFIT and not self.is_market_healthy:
            return True
        return False
