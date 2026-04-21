"""
persistence.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  체결 로그를 SQLite(trades.db)에 영속화한다. Phase 6 페이퍼 트레이딩
  도입 단계의 최소 구현 — live/testnet 거래를 mode 컬럼으로 구분해
  후속 분석·파라미터 조정의 원천 데이터로만 사용한다.

설계 원칙:
  - 로그 전용. 포지션 복구에는 사용하지 않는다 (recover_state() 전량정리
    방식 유지).
  - 동기 sqlite3 드라이버. 이벤트 루프 차단 방지를 위해 호출자는
    asyncio.to_thread() 로 감싼다.
  - 기록 실패가 매매 흐름을 차단해서는 안 된다. 호출자는 예외를 삼키고
    notify_error 만 호출한다.

사용처:
  executor.py — _record_trade(SELL 공통 진입점), _handle_buy_fill(BUY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import sqlite3
import threading
import time

DEFAULT_DB_PATH = "trades.db"
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    symbol TEXT NOT NULL,
    side   TEXT NOT NULL,
    qty    REAL NOT NULL,
    price  REAL NOT NULL,
    fee    REAL NOT NULL,
    pnl    REAL NOT NULL,
    mode   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_mode_ts ON trades(mode, ts);
"""


def init_db(path: str = DEFAULT_DB_PATH) -> None:
    """스키마 초기화. 멱등(IF NOT EXISTS)."""
    with _lock, sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def record_trade(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    pnl: float,
    mode: str,
    ts: float | None = None,
    path: str = DEFAULT_DB_PATH,
) -> None:
    """체결 1건 기록. side는 BUY/SELL. ts 미지정 시 현재 시각."""
    if ts is None:
        ts = time.time()
    with _lock, sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO trades(ts, symbol, side, qty, price, fee, pnl, mode) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (ts, symbol, side, qty, price, fee, pnl, mode),
        )
        conn.commit()


def load_trades(
    mode: str | None = None,
    limit: int = 100,
    path: str = DEFAULT_DB_PATH,
) -> list[dict]:
    """최근 거래 조회. mode=None이면 전체."""
    with _lock, sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        if mode is None:
            cur = conn.execute(
                "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,)
            )
        else:
            cur = conn.execute(
                "SELECT * FROM trades WHERE mode = ? ORDER BY ts DESC LIMIT ?",
                (mode, limit),
            )
        return [dict(row) for row in cur.fetchall()]
