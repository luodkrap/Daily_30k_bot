-- ────────────────────────────────────────────────────────────────
-- Daily 30K Bot — Supabase Postgres Schema (A1)
-- ────────────────────────────────────────────────────────────────
-- 적용 방법: Supabase 대시보드 → SQL Editor → 전체 복사·실행.
-- 멱등 (IF NOT EXISTS) — 재실행해도 안전.
--
-- 설계 원칙:
--   · mode 컬럼으로 live/testnet 분리 — 페이퍼와 실거래 동일 스키마 공유.
--   · ts(Unix epoch) 는 기존 SQLite 호환용, created_at 은 Postgres 쿼리용.
--   · 가격·수량은 NUMERIC(20,8) — 암호화폐 소수점 8자리 보존.
--   · 조회 인덱스: (mode, ts DESC) — 대시보드 "최근 N건" 쿼리 패턴 최적화.
-- ────────────────────────────────────────────────────────────────

-- 1. 체결 로그 (SQLite trades 와 스키마 1:1 대응)
CREATE TABLE IF NOT EXISTS trades (
    id          BIGSERIAL PRIMARY KEY,
    ts          DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty         NUMERIC(20, 8) NOT NULL,
    price       NUMERIC(20, 8) NOT NULL,
    fee         NUMERIC(20, 8) NOT NULL,
    pnl         NUMERIC(20, 8) NOT NULL,
    mode        TEXT NOT NULL CHECK (mode IN ('live', 'testnet'))
);
CREATE INDEX IF NOT EXISTS idx_trades_mode_ts ON trades(mode, ts DESC);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts ON trades(symbol, ts DESC);

-- 2. 자산 스냅샷 (1시간 주기, 손익 곡선 / 드로다운 집계용)
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id                   BIGSERIAL PRIMARY KEY,
    ts                   DOUBLE PRECISION NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mode                 TEXT NOT NULL CHECK (mode IN ('live', 'testnet')),
    equity_usdt          NUMERIC(20, 8) NOT NULL,   -- 총 자산 USDT 환산
    cash_usdt            NUMERIC(20, 8) NOT NULL,   -- USDT 현금
    position_value_usdt  NUMERIC(20, 8) NOT NULL,   -- 보유 코인 평가액
    realized_pnl         NUMERIC(20, 8) NOT NULL,   -- 누적 실현손익
    unrealized_pnl       NUMERIC(20, 8) NOT NULL    -- 미실현손익
);
CREATE INDEX IF NOT EXISTS idx_equity_mode_ts ON equity_snapshots(mode, ts DESC);

-- 3. 봇 이벤트 로그 (킬스위치 / 재시작 / 심볼 전환 / 에러)
CREATE TABLE IF NOT EXISTS bot_events (
    id          BIGSERIAL PRIMARY KEY,
    ts          DOUBLE PRECISION NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    mode        TEXT NOT NULL CHECK (mode IN ('live', 'testnet')),
    event_type  TEXT NOT NULL,   -- STARTUP | SHUTDOWN | KILL_SWITCH | STOP_LOSS | EMERGENCY_SELL | SWITCH_SYMBOL | MARKET_FILTER | ERROR
    severity    TEXT NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    message     TEXT NOT NULL,
    context     JSONB            -- 자유 필드 (symbol, pnl, api_error 등)
);
CREATE INDEX IF NOT EXISTS idx_events_mode_ts ON bot_events(mode, ts DESC);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON bot_events(event_type, ts DESC);

-- ────────────────────────────────────────────────────────────────
-- KST 표시용 View (Supabase 대시보드 조회 편의)
-- 원본 테이블의 created_at 은 UTC TIMESTAMPTZ — KST 환산은 +9시간.
-- 각 View 는 created_at 만 KST timestamp(without timezone) 로 변환.
-- 봇 런타임은 base 테이블만 사용. View 는 사용자 조회 전용.
-- ────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW trades_kst AS
SELECT
    id, ts,
    (created_at AT TIME ZONE 'Asia/Seoul')::timestamp AS created_at,
    symbol, side, qty, price, fee, pnl, mode
FROM trades;

CREATE OR REPLACE VIEW equity_snapshots_kst AS
SELECT
    id, ts,
    (created_at AT TIME ZONE 'Asia/Seoul')::timestamp AS created_at,
    mode, equity_usdt, cash_usdt, position_value_usdt,
    realized_pnl, unrealized_pnl
FROM equity_snapshots;

CREATE OR REPLACE VIEW bot_events_kst AS
SELECT
    id, ts,
    (created_at AT TIME ZONE 'Asia/Seoul')::timestamp AS created_at,
    mode, event_type, severity, message, context
FROM bot_events;
