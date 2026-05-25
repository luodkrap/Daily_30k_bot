"""
shared_state.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  봇의 모든 실시간 상태를 관리하는 단일 데이터 클래스 BotState.
  스캐너, 엔진, 텔레그램 봇이 공유하는 전역 상태.

주요 필드:
  - kill_event: 킬 스위치 (asyncio.Event) — 모든 루프 즉시 중단
  - target_coin: 현재 거래 대상 코인
  - daily_pnl, trade_count: 일일 손익 및 거래 횟수
  - is_market_healthy: 시장 상태 (200MA 필터, 연속 손실 등)
  - should_stop_profit property: 수익 중단 조건 (목표 도달 또는 시장 악화)

사용처:
  screener.py, main.py (executor 뼈대), 텔레그램 봇 함수들
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
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

    # ─── 컴포넌트 heartbeat (N19 watchdog) ────────────────
    # executor 메인 루프가 매 iteration 첫 줄에서 time.time() 으로 갱신.
    # _supervise(watchdog_timeout=600) 가 600초 무갱신 시 task 강제 cancel → 재시작.
    # 4/28~5/4 6일간 run_executor 단독 hang 사건(예외 없음 → 기존 _supervise 가 못 잡음)
    # 재발 방지가 목적. recover_state 내부 throttle sleep 직후에도 갱신.
    executor_heartbeat: float = 0.0
    # N25 silence watchdog — heartbeat 가 살아있어도 운영 산출물이 끊기면 감지.
    # equity snapshot 은 30분 주기이므로 supervisor 가 이 값을 별도 progress 로 감시한다.
    executor_last_snapshot_at: float = 0.0
    executor_last_trade_at: float = 0.0
    n25_last_trade_idle_alert_at: float = 0.0
    # N30: 그리드 진입 실패(setup_grid 초기 매수 미체결 등)가 반복되는 idle 감지.
    # engine 이 None 인 채 거래에 못 들어가는 상태는 N25 trade-idle(engine 활성 전제) 도,
    # snapshot watchdog(snapshot 은 정상) 도 못 잡는 사각지대였다 (5/15~ 10일 무거래 사건).
    executor_grid_idle_since: float = 0.0
    n30_last_grid_idle_alert_at: float = 0.0
    # N30: testnet 등에서 일봉이 201개 미만이면 200MA 필터를 계산할 수 없어
    # update_market_filter 가 조용히 return → is_market_healthy 가 기본값(True)에 동결된다
    # (5/15 testnet 일봉 20개 사건). 동작은 유지하되 1회만 경고한다.
    market_filter_unavailable_warned: bool = False

    def reset_daily(self) -> None:
        """자정 일일 집계 수치 초기화. run_executor에서 날짜 변경 감지 시 호출."""
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.consecutive_losses = 0

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
