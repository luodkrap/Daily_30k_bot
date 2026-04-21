"""
persistence.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  체결 로그·자산 스냅샷·봇 이벤트를 영속화한다.
  Phase 7 에서 듀얼 백엔드로 확장:
    · sqlite  — 로컬 파일 (개발·백테스트·기본값)
    · supabase — Postgres + asyncpg (운영 Lightsail)

설계 원칙:
  - 인터페이스는 전부 async. 호출부는 그대로 `await persistence.record_trade(...)`.
  - 백엔드 전환은 config.DB_BACKEND 한 곳으로 결정 (런타임 분기 없음).
  - 기록 실패가 매매 흐름을 차단해서는 안 된다. 호출자는 예외를 삼키고
    notify_error 만 호출한다.
  - 포지션 복구에는 사용하지 않는다 (recover_state() 전량정리 방식 유지).

사용처:
  main.py      — init_db()
  executor.py  — record_trade(), (추후) record_event(), record_equity_snapshot()
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from typing import Any

import config


_SQLITE_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                  REAL NOT NULL,
    mode                TEXT NOT NULL,
    equity_usdt         REAL NOT NULL,
    cash_usdt           REAL NOT NULL,
    position_value_usdt REAL NOT NULL,
    realized_pnl        REAL NOT NULL,
    unrealized_pnl      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_mode_ts ON equity_snapshots(mode, ts);

CREATE TABLE IF NOT EXISTS bot_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    mode       TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity   TEXT NOT NULL,
    message    TEXT NOT NULL,
    context    TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_mode_ts ON bot_events(mode, ts);
"""


class SqliteBackend:
    """로컬 SQLite 파일 백엔드. 동기 드라이버를 asyncio.to_thread 로 래핑."""

    def __init__(self, path: str = "trades.db"):
        self.path = path
        self._lock = threading.Lock()

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()

    async def record_trade(
        self, symbol: str, side: str, qty: float, price: float,
        fee: float, pnl: float, mode: str, ts: float | None = None,
    ) -> None:
        if ts is None:
            ts = time.time()
        await asyncio.to_thread(
            self._insert_trade_sync,
            ts, symbol, side, qty, price, fee, pnl, mode,
        )

    def _insert_trade_sync(self, ts, symbol, side, qty, price, fee, pnl, mode) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO trades(ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, symbol, side, qty, price, fee, pnl, mode),
            )
            conn.commit()

    async def load_trades(
        self, mode: str | None = None, limit: int = 100,
    ) -> list[dict]:
        return await asyncio.to_thread(self._load_sync, mode, limit)

    def _load_sync(self, mode, limit) -> list[dict]:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            if mode is None:
                cur = conn.execute(
                    "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", (limit,),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM trades WHERE mode = ? ORDER BY ts DESC LIMIT ?",
                    (mode, limit),
                )
            return [dict(row) for row in cur.fetchall()]

    async def record_equity_snapshot(
        self, mode: str, equity_usdt: float, cash_usdt: float,
        position_value_usdt: float, realized_pnl: float, unrealized_pnl: float,
        ts: float | None = None,
    ) -> None:
        if ts is None:
            ts = time.time()
        await asyncio.to_thread(
            self._insert_equity_sync,
            ts, mode, equity_usdt, cash_usdt,
            position_value_usdt, realized_pnl, unrealized_pnl,
        )

    def _insert_equity_sync(self, ts, mode, eq, cash, pv, rpnl, upnl) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO equity_snapshots"
                "(ts, mode, equity_usdt, cash_usdt, position_value_usdt, "
                " realized_pnl, unrealized_pnl) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, mode, eq, cash, pv, rpnl, upnl),
            )
            conn.commit()

    async def record_event(
        self, mode: str, event_type: str, severity: str, message: str,
        context: dict[str, Any] | None = None, ts: float | None = None,
    ) -> None:
        if ts is None:
            ts = time.time()
        ctx_json = None if context is None else json.dumps(context, ensure_ascii=False)
        await asyncio.to_thread(
            self._insert_event_sync,
            ts, mode, event_type, severity, message, ctx_json,
        )

    def _insert_event_sync(self, ts, mode, event_type, severity, message, ctx_json) -> None:
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT INTO bot_events"
                "(ts, mode, event_type, severity, message, context) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, mode, event_type, severity, message, ctx_json),
            )
            conn.commit()


class SupabaseBackend:
    """Supabase Postgres 백엔드. asyncpg connection pool 사용.

    스키마 적용은 `deploy/schema.sql` 을 Supabase SQL Editor 에서 선행 실행한다.
    init() 은 pool 생성만 담당 (테이블 존재 확인 쿼리 포함)."""

    def __init__(self, dsn: str):
        if not dsn:
            raise RuntimeError(
                "SUPABASE_DB_URL 미설정. DB_BACKEND=supabase 는 .env 에 "
                "SUPABASE_DB_URL 필요 (Supabase 프로젝트 Settings → Database → "
                "Connection pooling URI)."
            )
        self.dsn = dsn
        self._pool = None

    async def init(self) -> None:
        import asyncpg  # 지연 임포트 — sqlite 백엔드에서 미설치여도 돌아가게
        self._pool = await asyncpg.create_pool(
            self.dsn, min_size=1, max_size=5, command_timeout=10,
        )
        # 스키마 존재 검증 — deploy/schema.sql 미적용 시 조기 실패
        async with self._pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT to_regclass('public.trades') IS NOT NULL"
            )
            if not exists:
                raise RuntimeError(
                    "Supabase 'trades' 테이블이 존재하지 않습니다. "
                    "deploy/schema.sql 을 Supabase SQL Editor 에서 먼저 실행하세요."
                )

    async def record_trade(
        self, symbol, side, qty, price, fee, pnl, mode, ts=None,
    ) -> None:
        if ts is None:
            ts = time.time()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO trades(ts, symbol, side, qty, price, fee, pnl, mode) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                ts, symbol, side, qty, price, fee, pnl, mode,
            )

    async def load_trades(self, mode=None, limit=100) -> list[dict]:
        async with self._pool.acquire() as conn:
            if mode is None:
                rows = await conn.fetch(
                    "SELECT * FROM trades ORDER BY ts DESC LIMIT $1", limit,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM trades WHERE mode = $1 ORDER BY ts DESC LIMIT $2",
                    mode, limit,
                )
            return [dict(row) for row in rows]

    async def record_equity_snapshot(
        self, mode, equity_usdt, cash_usdt, position_value_usdt,
        realized_pnl, unrealized_pnl, ts=None,
    ) -> None:
        if ts is None:
            ts = time.time()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO equity_snapshots"
                "(ts, mode, equity_usdt, cash_usdt, position_value_usdt, "
                " realized_pnl, unrealized_pnl) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)",
                ts, mode, equity_usdt, cash_usdt,
                position_value_usdt, realized_pnl, unrealized_pnl,
            )

    async def record_event(
        self, mode, event_type, severity, message, context=None, ts=None,
    ) -> None:
        if ts is None:
            ts = time.time()
        ctx_json = None if context is None else json.dumps(context, ensure_ascii=False)
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO bot_events"
                "(ts, mode, event_type, severity, message, context) "
                "VALUES ($1,$2,$3,$4,$5,$6::jsonb)",
                ts, mode, event_type, severity, message, ctx_json,
            )


# ─── 모듈 레벨 싱글톤 ─────────────────────────────────────
_backend = None


def _get_backend():
    """config.DB_BACKEND 기반 싱글톤. 테스트에서는 직접 백엔드 인스턴스 사용."""
    global _backend
    if _backend is None:
        if config.DB_BACKEND == "supabase":
            _backend = SupabaseBackend(config.SUPABASE_DB_URL)
        else:
            _backend = SqliteBackend(path=config.SQLITE_DB_PATH)
    return _backend


async def init_db() -> None:
    await _get_backend().init()


async def record_trade(
    symbol: str, side: str, qty: float, price: float,
    fee: float, pnl: float, mode: str, ts: float | None = None,
) -> None:
    await _get_backend().record_trade(symbol, side, qty, price, fee, pnl, mode, ts)


async def load_trades(mode: str | None = None, limit: int = 100) -> list[dict]:
    return await _get_backend().load_trades(mode=mode, limit=limit)


async def record_equity_snapshot(
    mode: str, equity_usdt: float, cash_usdt: float,
    position_value_usdt: float, realized_pnl: float, unrealized_pnl: float,
    ts: float | None = None,
) -> None:
    await _get_backend().record_equity_snapshot(
        mode, equity_usdt, cash_usdt, position_value_usdt,
        realized_pnl, unrealized_pnl, ts,
    )


async def record_event(
    mode: str, event_type: str, severity: str, message: str,
    context: dict[str, Any] | None = None, ts: float | None = None,
) -> None:
    await _get_backend().record_event(mode, event_type, severity, message, context, ts)
