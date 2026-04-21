---
name: project_state
description: Daily 30K 봇 현재 구현 상태, 핵심 파라미터, 발견된 이슈 (2026-04-21 감사 기준)
type: project
---

## 구현 완료 단계

Phase 1~6 페이퍼 인프라 완료. Phase 7 코드 완료 (사용자 액션 대기).
핵심 파일 8개: config.py, shared_state.py, notifier.py, screener.py, executor.py, persistence.py, main.py, test.py
deploy/ 디렉토리 추가: schema.sql, daily30k.service, setup.sh, update.sh

**Why:** Phase 7 A 트랙 코드 완료 — Supabase/SQLite 듀얼 백엔드 + systemd 배포 스크립트

## 핵심 파라미터 (config.py 확인값)

- SEED: 3,000,000원 (KRW)
- DAILY_TARGET: SEED * 1.0% = 30,000원
- DAILY_LOSS_LIMIT: SEED * 3.0% = 90,000원
- MAX_POSITION_RATE: 1% (1% Rule)
- STOP_LOSS_RATE: 2%
- GRID_COUNT: 5, GRID_SPACING: 0.5%
- FEE_RATE: 0.1%, INITIAL_BUY_RATIO: 50%
- SCANNER_INTERVAL_SEC: 900초 (15분)
- SCANNER_CANDLE_LIMIT: 30
- KRW_RATE: 1350 (기본값, 30분마다 갱신)
- ccxt enableRateLimit=True: main.py에서 확인됨
- MODE: live/testnet 분기 구현됨 (config.py:26-44)
- DB_BACKEND: sqlite/supabase 분기 (config.py:32-36)

## 2026-04-21 감사 — 이슈 현황

### 이전 모든 버그 해결됨 (B1~B5, C2, H2)

### 2026-04-21 신규 발견 이슈

**CRITICAL:**
- [N1] SupabaseBackend 연결 실패 시 fallback 없음: init()이 예외를 그대로 throw → main.py init_db() 실패 → 봇 시작 불가. 운영 환경에서 Supabase 일시 장애 시 전체 봇 다운. (persistence.py:190-203)
- [N2] SupabaseBackend.record_trade/record_event 등 쓰기 실패 시 예외 전파: _log_trade는 try-except로 잡지만, 직접 호출 경로(main.py 등)는 호출자가 예외를 직접 처리해야 함. (persistence.py:211-216)

**HIGH:**
- [N3] equity_snapshots 실제 호출부 없음: 테이블 스키마·헬퍼 함수 구현됐으나 main.py/executor.py 어디서도 record_equity_snapshot()을 주기적으로 호출하지 않음. 가장 유용한 지표(잔고 추이)가 수집 안 됨.
- [N4] bot_events 실제 호출부 없음: record_event() 구현됐으나 킬 스위치·재시작·에러 발생 시점에서 호출 코드 없음. Supabase 대시보드에서 이벤트 로그를 볼 수 없음.
- [N5] recover_state() 내 시장가 매도가 _log_trade 호출 없음: 청산된 포지션이 trades.db에 기록 안 됨. 수동 손익 계산 시 누락.
- [N6] stop_loss check_stop_loss() 시장가 매도 — CLAUDE.md "지정가 우선" 원칙 충돌. 손절·긴급매도는 시장가 허용이 관례이나 문서상 절대 원칙과 충돌. (executor.py:366-368)

**MEDIUM:**
- [N7] test.py 실행 진입점이 단편화: python test.py 는 unit suite만 실행. bugfix suite(버그픽스+Phase6)는 python test.py bugfix 로 별도 실행. 초보 사용자가 전체 suite 통과 확인 못할 수 있음.
- [N8] SupabaseBackend 오프라인 fallback 테스트 없음: asyncpg 연결 실패·pool timeout 엣지 케이스 테스트 전무.
- [N9] equity_snapshots/bot_events insert 실패 전파 경로 테스트 없음.
- [N10] deploy/setup.sh Python 버전 하드코딩 3.11 — 로컬 개발 venv는 Python 3.14 사용. VPS 설치 버전 불일치 위험.

## 파일 구조 현황

핵심 8개 파일 + deploy/4파일 모두 존재.
.env, .gitignore, .env.example, requirements.txt 모두 존재.

## C1 진입 선결 과제 Top 3

1. N3+N4: equity_snapshots/bot_events 실제 호출부 추가 (코드 완료라고 보기 어려운 상태)
2. N1: SupabaseBackend init 실패 시 SQLite fallback 또는 retry 로직
3. N10: setup.sh Python 버전 로컬(3.14) vs VPS(3.11) 불일치 문서화/수정
