# TODO — Daily 30K Bot

> **🗓️ 2026-04-22 로드맵 플랜:** `~/.claude/plans/streamed-launching-cascade.md`
> **상세 진행 방식:** [WORKFLOW.md](WORKFLOW.md)

---

## 👤 사용자 액션 남은 것 (외부 서비스 셋업)

> Claude 가 대행 불가한 작업. Claude 의 N 트랙 작업과 **병행 가능**.

### 🟢 지금 즉시 병행 가능

- [x] **A1b** (2026-04-23 완료): Supabase 프로젝트 생성 (서울 리전) + `deploy/schema.sql` 적용 + Pooler(6543) URI `.env` 기입. 로컬 `asyncpg` 검증 통과 — Postgres 17.6 연결 OK, 3개 테이블 컬럼·타입 1:1 일치
- [ ] **A4** (~30분): AWS Lightsail 인스턴스 생성 (서울, $5 플랜, Ubuntu 22.04) → SSH 접속 → `bash deploy/setup.sh` 실행 → `.env` 에 Supabase URI·바이낸스 키 입력 → `sudo systemctl start daily30k`

### 🟡 A1b + A4 완료 후

- [ ] **B1**: https://testnet.binance.vision 가입 → HMAC API 키 발급 → 서버 `.env` 에 `MODE=testnet` + `BINANCE_TESTNET_API_KEY` + `BINANCE_TESTNET_SECRET_KEY` 기재
- [ ] **B2**: `sudo systemctl restart daily30k` → 텔레그램 부팅 메시지 `[MODE=TESTNET]` 확인 + Supabase 대시보드 `trades` 테이블 행 증가 검증

### 🔴 1~2주 페이퍼 누적 후

- [ ] **B3**: 1주일 누적 손익 리포트 리뷰 → `MODE=live` 전환 여부 판단 → 실거래 바이낸스 HMAC 키 발급 (IP 화이트리스트 · 출금권한 OFF) → `.env` `MODE=live` + `BINANCE_API_KEY`/`BINANCE_SECRET_KEY` 기재 → `sudo systemctl restart daily30k`

---

## 완료 (Done)

- [x] 프로젝트 설계 문서 (PROJECT.md)
- [x] .env 환경변수 설정
- [x] test.py — 텔레그램 연결 테스트
- [x] 바이낸스 ccxt 연동 — BTC 실시간 가격 수신
- [x] GitHub 레포 세팅 및 /push 슬래시 커맨드

## 진행 중 (In Progress)

없음 (🤖 다음 진입: N6 — CLAUDE.md 시장가 예외 조항 명시 / 또는 N7 — SupabaseBackend 테스트 4건)

## 남은 작업 (Backlog)

### Phase 2 — 프로젝트 구조화

- [x] config.py — 시드 기반 수치 자동 계산 (.env 연동)
- [x] shared_state.py — BotState dataclass (킬 이벤트, 손익, 시장 상태)
- [x] notifier.py — 텔레그램 알림 모듈 (비동기)
- [x] screener.py — 스캐너 엔진 뼈대 (async)
- [x] main.py — asyncio.gather()로 3개 컴포넌트 동시 실행
- [x] `.env` SEED 관리 + `/seed` 텔레그램 커맨드

### Phase 3 — 스캐너 엔진

- [x] USDT 페어 + 스테이블코인/레버리지 토큰 사전 필터
- [x] 24h 거래량 $100M 이상 필터
- [x] ATR 기반 변동성 필터 (Wilder's Smoothing)
- [x] 펌프앤덤프 역필터 (3h/6h 급등, 거래량 스파이크)
- [x] API 병렬 처리 (asyncio.Semaphore)
- [x] 점수 기반 후보 코인 정렬 (ATR 적정성·거래량·가격안정성)
- [x] 스캐너 결과 텔레그램 보고
- [x] 단위·통합 테스트 케이스 추가

### Phase 4 — 트레이딩 엔진

- [x] 그리드 매매 로직 구현 (GridEngine: setup_grid, monitor_orders, regrid)
- [x] 동적 코인 스위칭 (run_executor 오케스트레이터)
- [x] `main.py` — run_executor를 executor.py로 분리
- [x] `config.py` — SCANNER_INTERVAL_SEC 3600 → 900 (15분, 동적 스위칭 반응성)

### Phase 5 — 리스크 관리

- [x] 손절매 (Stop-Loss) — check_stop_loss: 진입가 -2% 전량 시장가 매도
- [x] 1% Rule 포지션 사이징 — calc_position_size
- [x] 시장 필터 (200MA 기준) — update_market_filter + 실시간 환율 갱신
- [x] 킬 스위치 + 일일 손실 한도 — run_executor 안전장치 6단계

### 버그 수정 — Phase 5 감사 결과 (실전 투입 전 필수)

> 상세 수정 방법 및 진행 순서 → [WORKFLOW.md](WORKFLOW.md)

**치명적 (Critical) — 페이퍼 트레이딩 전 해결**

- [x] C3: `check_stop_loss()` + `emergency_sell()` 매수 수수료 누락 → 킬 스위치 지연
- [x] C4: 리그리딩 트리거 `not engine.buy_orders` 조건 누락 → 이중 포지션 위험
- [x] C1: `setup_grid()` 시장가 매수 → 지정가로 교체 (CLAUDE.md 원칙 위반)
- [x] C2: 재시작 시 포지션·주문 상태 복구 로직 없음 → 이중 포지션 위험 (실전 투입 블로커) (2026-04-21 `recover_state()` 전량정리 방식 — 미체결 주문 취소 + 비-USDT 포지션 시장가 매도, dust 스킵) **✅ 2026-04-25 N5/N5b 보완: `_log_trade` 기록 + 매도간 0.3s throttle (429 회피)**

**높은 우선순위 (High) — 실전 투입 전 해결**

- [x] H3: PROJECT.md 로드맵 Phase 4/5 완료 상태 미반영 (CLAUDE.md Rule 1 위반)
- [x] H4: `asyncio.gather` 컴포넌트 하나 실패 시 전체 봇 중단 → `_supervise()` 패턴으로 격리
- [x] H1: `requirements.txt` 없음 → VPS 배포 불가 (2026-04-17 `pip freeze` 기반 생성)
- [x] H2: 텔레그램 플러드 방지 없음 → 오류 루프 시 API 429 (2026-04-21 notifier.py에 60s dedup + 1s 간격 스로틀 구현)

**감사 결과 추가 (2026-04-15)**

- [x] A6: `regrid()` 매수 수수료 누락 → 양방향 수수료 적용
- [x] A7: `consecutive_losses → is_market_healthy` 미연동 → `check_loss_streak` 헬퍼 도입
- [x] A8: `_handle_sell_fill()` 수수료 이중 차감 → 매수 수수료를 매수 체결 시점으로 분리
- [x] A9: ATR `SCANNER_CANDLE_LIMIT=15` 부족 → 30으로 확대 (Wilder's Smoothing 동작)

**감사 결과 추가 (2026-04-17) — Phase 6 블로커 포함**

- [x] B1: `_limit_buy_with_retry` 외부 취소 주문을 체결로 오인 → 공매도 위험 (2026-04-21 `fetch_order` 폴링으로 전환)
- [x] B2: `check_stop_loss()` 후 `avg_price` 미초기화 → `emergency_sell`/`regrid`와 일관성 위반 (2026-04-17 avg_price·total_invested 0 초기화)
- [x] B3: `sell_qty` 총합이 `total_qty` 초과 가능 → stepSize 큰 자산에서 insufficient balance 오류 (2026-04-21 setup_grid 마지막 레벨 잔량 보정 + \_handle_buy_fill 상한 적용)
- [x] B5: `stability_score` 임계값 0.05 실효성 없음 → 가중치 20% 사실상 낭비 (2026-04-21 후보군 CV min-max 정규화로 전환 — ATR·volume 점수와 동일 방식)
- [ ] B7: 캔들 수집 실패 무음 처리 → API 오류 다발 시 후보 코인 집단 탈락 감지 불가

**🤖 감사 결과 추가 (2026-04-22) — Phase 7 보완 / C1 리팩터 전 선결**

> 감사 보고서: 2026-04-22 project-auditor 3/3. A2/C2 가 [x]로 체크됐으나 핵심 기능 누락 발견. C1(Exchange 추상화) 전 선결 Top 3 → **N3+N4 → N1 → N8**. 로드맵 플랜 → `~/.claude/plans/streamed-launching-cascade.md`

**치명적 (Critical) — C1 전 필수**

- [x] 🤖 N1 (2026-04-22 완료): `SupabaseBackend.init()` 실패 시 `persistence.init_db()` 내 SQLite degraded fallback + `main.py` 텔레그램 `[DEGRADED]` 알림 + `DB_FALLBACK` CRITICAL 이벤트 기록. 회귀 테스트 3건 (fallback 발동·사유 노출·sqlite 원시 실패 비삼킴)
- [x] 🤖 N2 (2026-04-22 완료): `persistence.py` 공개 함수 3개(`record_trade`·`record_equity_snapshot`·`record_event`) 에 `try/except` + `_safe_notify_backend_error` 헬퍼(notifier 지연 import + 이중 장애 stderr fallback) 내장. 설계 원칙 "기록 실패가 매매 흐름을 차단하지 않음" 을 호출부가 아닌 모듈 자체가 보장. `executor._log_trade`/`_log_event` 및 `main._supervise`/부트 flow 의 dead `try/except` 제거. 회귀 테스트 4건 (트레이드/이벤트/에쿼티 write 실패 + notifier 이중 장애 삼킴)

**높은 우선순위 (High)**

- [x] 🤖 N3: `snapshot_equity()` 헬퍼 추가 + `run_executor` 30분 타이머 편승 (2026-04-22 `update_krw_rate` 다음에 잔고+포지션 평가액 스냅샷 기록)
- [x] 🤖 N4: `_log_event()` 헬퍼 + 6개 지점에 호출 주입 (2026-04-22 EXECUTOR_START · KILL_SWITCH · DAILY_STOP · MARKET_FILTER 전환 · RECOVER_STATE 완료/실패 · SUPERVISOR_RESTART)
- [x] 🤖 N5 (2026-04-25 완료): `recover_state()` 매도 루프에 `_log_trade("SELL", ...)` 호출 추가 — 청산 거래도 `trades` 테이블에 기록 (수수료/PnL 산출 불가 → 0). 회귀 테스트 1건 (`test_n5_recover_logs_trade_on_liquidation`)
- [x] 🤖 N5b (2026-04-25 완료): `recover_state()` 매도 사이 `RECOVER_SELL_THROTTLE_SEC=0.3` sleep 추가 — binance 50 orders/10s 제한 회피. testnet 사전 잔고 다중 청산 시 429 폭주로 봇 부팅 실패 결함을 해소. 회귀 테스트 1건 (`test_n5b_recover_throttles_between_sells`). 사용자 A4 진행 중 발견된 testnet 환경 특이점 대응
- [ ] 🤖 N6: CLAUDE.md "모든 주문: 지정가 우선" 원칙과 손절·긴급매도·recover 청산의 시장가 사용 충돌 → 예외 조항 명시
- [ ] 🤖 N7: `SupabaseBackend` 관련 테스트 전무 → `MockAsyncpgPool`로 init 실패 / write 실패 / timeout / fallback 동작 4건

**중간 (Medium)**

- [x] 🤖 N8 (2026-04-22 완료): `python test.py` 기본 `unit` 모드에 bugfix+Phase 6/7 suite 통합 (Phase 3/4 헬퍼 + `_run_bugfix_phase67()` 헬퍼로 분리, `unit3`/`unit4`/`bugfix` 하위 호환 유지). Phase 4 `test_run_executor_kill` 이 `update_krw_rate` 를 통해 실제 업비트 API 로 `config.KRW_RATE` 를 오염시키던 테스트 격리 결함도 함께 해소 (bugfix suite 진입 시 `KRW_RATE=1350`/`SEED=3_000_000` 복원). C1 리팩터 안전망 확보
- [ ] 🤖 N9: `run_executor` `DAILY_LOSS_LIMIT` 킬 경로 테스트 없음 → 외부 kill_event 설정이 아닌 손익 누적 시나리오 테스트 추가
- [ ] 🤖 N10: `deploy/setup.sh:31` Python 3.11 vs 로컬 3.14 불일치 → 3.12+ 격상 또는 `requirements.txt` VPS 버전 재생성
- [x] N11: [PROJECT.md:86](PROJECT.md#L86) 파일 구조 표 헤더 "Phase 5 기준" → "Phase 7 기준" (2026-04-22 문서 수정)

**낮음 (Low)**

- [ ] 🤖 N12: `deploy/daily30k.service` 로그 rotate 미설정 → `/etc/logrotate.d/daily30k` 추가 또는 journald 전환
- [ ] 🤖 N13: `executor.py:282-299` `monitor_orders` 단일 주문 실패가 사이클 중단 → 체결 핸들러 개별 try-except
- [ ] 🤖 N14: `main.py:125-141` `_supervise` `max_restarts` 초과 시 `kill_event.set()` 호출 검증 테스트 없음

### Phase 6 — 검증

- [~] 페이퍼 트레이딩 — 인프라 완료 (2026-04-21 MODE=live/testnet 분기 + testnet 키 분리 + `set_sandbox_mode` + SQLite `trades.db` 체결 로그). 실연결 검증은 A 트랙 완료 후 B 트랙으로 진행.
- [ ] 🤖 백테스트 엔진 구축 (C 트랙, 2026-04-21 플랜 승인, **N 트랙 Top 3 해소 후**):
  - [ ] 🤖 C1: Exchange 인터페이스 추상화 — `exchanges/base.py`, `ccxt_exchange.py`, `backtest_exchange.py`. GridEngine `executor.py` 리팩터
  - [ ] 🤖 C2: `backtest/data.py` — `ccxt.fetch_ohlcv` 과거 1분봉 parquet 저장
  - [ ] 🤖 C3: `backtest/simulator.py` + `runner.py` — 시간 이동 tick 주입 + 파라미터 스윕
  - [ ] 🤖 C4: `backtest/results.py` — 손익곡선·MDD·샤프비·승률 리포트

### Phase 7 — 배포 (A 트랙, 2026-04-21 플랜 승인 / 코드 완료 2026-04-21)

> 사용자 액션 상세는 파일 상단 **"👤 사용자 액션 남은 것"** 섹션 참조.

- [x] A1: Supabase 프로젝트 — `deploy/schema.sql` 작성 (2026-04-21) + 서울 리전 프로젝트 생성·스키마 적용·Pooler URI `.env` 기입 (2026-04-23 A1b 완료)
- [x] A2: `persistence.py` asyncpg 듀얼 백엔드 — `SqliteBackend` / `SupabaseBackend` 클래스, 모듈 레벨 async 인터페이스, `config.DB_BACKEND` 싱글톤 분기. asyncpg 지연 임포트. (2026-04-21) **⚠ 2026-04-22 감사: `record_equity_snapshot`/`record_event` 호출부 미구현 → 🤖 N3/N4 에서 보완**
- [x] A3: `config.py` `DB_BACKEND` / `SQLITE_DB_PATH` / `SUPABASE_DB_URL` 추가. `.env.example` DB 섹션 + Pooler URI 안내. `requirements.txt` `asyncpg==0.30.0`. (2026-04-21)
- [ ] 👤 **A4**: AWS Lightsail 인스턴스 생성 (서울 리전, $5 플랜, Ubuntu 22.04) — **사용자 액션 → 상단 A4**
- [x] A5: `deploy/daily30k.service` (systemd unit, MemoryMax=512M) + `setup.sh` (Ubuntu 22.04 초기 프로비저닝) + `update.sh` (git pull + 조건부 pip install + restart). (2026-04-21)
