# WORKFLOW — Daily 30K Bot

> **세션 인수인계 문서.** 새 세션 시작 → 이 파일만 읽으면 10초 내 상태 파악 가능.  
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

---

## 🔲 빠른 상태 (Quick Status)

| 항목 | 값 |
|------|----|
| **현재 Phase** | **Phase 7 운영 진입 — 페이퍼 트레이딩 가동 중**. A4/B1/B2 모두 완료(2026-04-25, Lightsail `3.36.26.177` testnet 기동, recover 13건 청산 성공). N3+N4·N1·N8·N2·N5·N5b·OPS1 완료, Critical+High Top 5 해소 + 배포 가이드 자동화. 다음은 🤖 R1→R2 (B3 판단 지원 리포팅) 또는 🤖 N6/N7/N9~N14 잔여. Day ~14 에 R3 + 👤 B3 판단 |
| **마지막 점검** | 2026-04-22 (project-auditor 전체 감사 — A 트랙 + Phase 6 + 버그픽스 누적 반영) |
| **점검 누적** | 3/3 |
| **남은 블로커** | 없음 — testnet 페이퍼 가동 정상 (recover_state 정상 진입, 스캐너 환율 갱신 확인) |
| **테스트 상태** | 전체 통과 (`python test.py` 기본 실행으로 Phase 3/4 + bugfix + Phase 6/7 전부 커버, 신규 N5/N5b 2건 포함) |
| **로드맵 플랜** | `~/.claude/plans/streamed-launching-cascade.md` (2026-04-22 승인 — 역할 분담·타임라인) |

---

## 환경 체크리스트

```bash
# 1. venv 활성화
source venv/bin/activate        # Python 3.14 / venv 위치: ./venv/

# 2. 환경변수 확인
cat .env                        # BINANCE_API_KEY, TELEGRAM_BOT_TOKEN 등

# 3. 테스트 실행
python test.py                  # 전체 단위·통합 테스트

# 4. 봇 실행 (페이퍼 트레이딩 준비 완료 후)
python main.py
```

---

## 현재 작업

> 없음 — 아래 "다음 작업" 목록 최상위 항목(H1) 선택

<!--
작업 중일 때 아래 형식으로 채워넣을 것:

| 항목 | 값 |
|------|----|
| **작업 ID** | 예: C2 |
| **제목** | 예: 재시작 시 상태 복구 로직 |
| **진행도** | 예: 60% — fetch_open_orders 구현 완료, 잔고 조회 진행 중 |
| **수정 중인 파일** | 예: `executor.py`, `main.py` |
| **다음 실행 명령어** | 예: `python test.py` 후 `executor.py:120` 부터 이어서 |
| **블로커/메모** | 예: API rate limit 테스트 필요 |
-->

---

## 최근 파일 변경 이력

> 최근 3개 세션의 주요 변경만 유지. 오래된 항목은 완료 테이블로 이동.

| 날짜 | 파일 | 변경 이유 |
|------|------|-----------|
| 2026-04-25 | [deploy/advise.sh](deploy/advise.sh), [skills/deploy-advisor.md](skills/deploy-advisor.md) | OPS1b: 배포 필요성 판정 로직 추가 — `classify_file()` 헬퍼로 각 파일을 **skip/optional/required** 3등급 분류 → 최상단 배지(🚨 배포 필요 / 🟢 배포 선택 / 🔘 배포 불필요) + 파일별 태그 + 상태별 말미 명령 블록 분기. skills 의 제외 조건 삭제 (판정을 스크립트로 위임). 사용자 요청 "배포가 필요한지도 알려줘" 반영. 4개 케이스 검증 통과 |
| 2026-04-25 | [deploy/advise.sh](deploy/advise.sh), [skills/deploy-advisor.md](skills/deploy-advisor.md), [CLAUDE.md](CLAUDE.md), [TODO.md](TODO.md) | OPS1: 배포 가이드 시스템 구축. `deploy/advise.sh` 신규 — 변경 파일 유형별로 6등급 가이드(🔴 BEFORE DEPLOY / 🟠 ENV UPDATE / 🟠 SYSTEMD RELOAD / 🟡 TIMING WARNING / 🟢 AUTO / 🟢 STANDARD) 출력. `skills/deploy-advisor.md` 신규 — Claude 가 `*.py`/`deploy/*`/`.env.example`/`requirements.txt` 수정 세션 종료 시 `bash deploy/advise.sh --files ...` 실행해 응답에 첨부. `CLAUDE.md` 온디맨드 스킬 섹션에 참조 1줄. 6개 테스트 케이스 수동 검증 통과 (schema/env/service/trading/docs/복합) |
| 2026-04-25 | [TODO.md](TODO.md), [WORKFLOW.md](WORKFLOW.md) | A4+B1+B2 완료 처리. Lightsail $7 (서울, IP `3.36.26.177`) 페이퍼 트레이딩 가동 시작 — N5b throttle 패치 적용 후 recover_state 가 testnet 사전 잔고 13개(WAN/FUN/MDT/FIO/OXT/UTK/DEXE/GMT/BIFI/JUP/VANA/SOPH/AT) 정상 청산 → 봇 메인 루프 진입 (스캐너 환율 갱신 확인). 운영 인프라 100% 완성 |
| 2026-04-25 | [executor.py](executor.py), [test.py](test.py) | N5+N5b: `recover_state()` 매도 루프에 (1) `_log_trade("SELL", ...)` 호출 추가 — 청산 거래도 `trades` 테이블에 기록 (수수료/PnL 산출 불가 → 0); (2) `RECOVER_SELL_THROTTLE_SEC=0.3` sleep 추가 — binance 50 orders/10s 제한 회피. 회귀 테스트 2건 (`test_n5_recover_logs_trade_on_liquidation`, `test_n5b_recover_throttles_between_sells`). 사용자 A4 첫 부팅 시 testnet 사전 잔고 다중 청산이 429 폭주로 실패하던 환경 특이점 해소 |
| 2026-04-23 | [.env](.env), [TODO.md](TODO.md), [WORKFLOW.md](WORKFLOW.md) | A1b (사용자 액션): Supabase 프로젝트 생성 (서울 리전, Free 플랜) → `deploy/schema.sql` 적용 → Transaction Pooler(6543) URI `.env` `SUPABASE_DB_URL` 기입. 로컬 `asyncpg` 검증: Postgres 17.6 연결·3개 테이블(`trades`/`equity_snapshots`/`bot_events`) 존재·컬럼·타입 `schema.sql` 과 1:1 일치 확인. 운영 DB 블로커 해소, A4(Lightsail) 만 남음 |
| 2026-04-22 | [persistence.py](persistence.py), [executor.py](executor.py), [main.py](main.py), [test.py](test.py) | N2: `persistence` 공개 함수 3개(`record_trade`/`record_equity_snapshot`/`record_event`) 자체 try-except + `_safe_notify_backend_error` 헬퍼(notifier 지연 import + 이중 장애 stderr fallback). 설계 원칙 "기록 실패가 매매 흐름을 차단하지 않음"을 모듈 자체가 보장. `executor._log_trade`/`_log_event` 와 `main._supervise`/부트 flow 의 dead try-except 제거. 회귀 테스트 4건 (trade/event/equity write 실패 삼킴 + notifier 이중 장애 삼킴) |
| 2026-04-22 | [test.py](test.py) | N8: `python test.py` 기본 `unit` 모드에 bugfix+Phase 6/7 suite 통합. 헬퍼 3개(`_run_phase3`/`_run_phase4`/`_run_bugfix_phase67`)로 분리하여 `unit`/`unit3`/`unit4`/`bugfix` 모드에서 재사용. Phase 4 `test_run_executor_kill` 이 실제 업비트 API 로 `config.KRW_RATE` 를 오염시키던 테스트 격리 결함도 해소 (bugfix suite 진입 시 KRW_RATE/SEED 기본값 복원). C1 리팩터 안전망 확보 |
| 2026-04-22 | [persistence.py](persistence.py), [main.py](main.py), [test.py](test.py) | N1: `init_db()` Supabase→SQLite degraded fallback + `get_fallback_reason()` API. main.py 에서 `[DEGRADED]` 텔레그램 + `DB_FALLBACK` CRITICAL 이벤트 기록. 회귀 테스트 3건 (fallback 발동·사유 노출·sqlite 원시 실패 비삼킴). 운영 단일 장애점 해소 |
| 2026-04-22 | [executor.py](executor.py), [main.py](main.py), [test.py](test.py) | N3+N4: `snapshot_equity()` + `_log_event()` 헬퍼 추가 및 6개 호출 지점 주입 (EXECUTOR_START · KILL_SWITCH · DAILY_STOP · MARKET_FILTER 전환 · RECOVER_STATE 완료/실패 · SUPERVISOR_RESTART). 30분 타이머에 equity snapshot 편승. 회귀 테스트 3건 추가 |
| 2026-04-22 | [WORKFLOW.md](WORKFLOW.md), [TODO.md](TODO.md), [PROJECT.md](PROJECT.md) | 2026-04-22 project-auditor 3/3 감사 결과 반영: N1~N14 개선 항목 추가, Phase 7 "감사 후 보완" 상태 전환, C1 전 선결 Top 3 (N3+N4 → N1 → N8) 우선순위 기재. 플랜 파일 `~/.claude/plans/deep-jingling-frog.md` |
| 2026-04-21 | [persistence.py](persistence.py), [config.py](config.py), [main.py](main.py), [executor.py](executor.py), [.env.example](.env.example), [requirements.txt](requirements.txt), [test.py](test.py), [deploy/schema.sql](deploy/schema.sql), [deploy/daily30k.service](deploy/daily30k.service), [deploy/setup.sh](deploy/setup.sh), [deploy/update.sh](deploy/update.sh) | A 트랙 코드 (A1 schema.sql / A2 asyncpg 듀얼 백엔드 async 인터페이스 / A3 DB_BACKEND·SUPABASE_DB_URL env + asyncpg deps / A5 systemd unit·setup·update 스크립트). equity_snapshots·bot_events 테이블 추가 |
| 2026-04-21 | [WORKFLOW.md](WORKFLOW.md), [TODO.md](TODO.md), [PROJECT.md](PROJECT.md) | 운영 인프라 아키텍처 확정 반영: AWS Lightsail + Supabase Postgres 듀얼 백엔드 + 백테스트 엔진 (A/B/C 3트랙). 플랜 파일 `~/.claude/plans/mellow-imagining-wozniak.md` |
| 2026-04-21 | [config.py](config.py), [main.py](main.py), [executor.py](executor.py), [persistence.py](persistence.py), [.env.example](.env.example), [.gitignore](.gitignore), [test.py](test.py) | Phase 6 페이퍼 트레이딩 인프라: MODE=live/testnet 분기 + testnet API 키 분리 로드 + `set_sandbox_mode` + SQLite `trades.db` 체결 로그 (BUY/SELL 양방향, mode 컬럼) |
| 2026-04-21 | [screener.py](screener.py), [test.py](test.py) | B5: `_score_and_rank()` stability_score 를 후보군 CV min-max 정규화로 전환 (구 공식 `1 - cv/0.05` 는 CV>5% 코인을 전부 0점 clamp → 가중치 20% 실효성 없음) |
| 2026-04-21 | [executor.py](executor.py), [test.py](test.py) | B3: setup_grid 마지막 레벨에 `fill_qty - placed_sum` 잔량 사용 + _handle_buy_fill 에 `total_qty - Σ기배치` 상한 적용 (stepSize 반올림 누적으로 Σsell_qty > total_qty 되던 insufficient balance 결함 방지) |
| 2026-04-21 | [executor.py](executor.py), [test.py](test.py) | C2: `recover_state()` 추가 — 재시작 시 미체결 주문 취소 + 비-USDT 포지션 청산 (Phase 6 블로커 해소) |
| 2026-04-21 | [notifier.py](notifier.py), [test.py](test.py) | H2: 동일 메시지 60초 dedup + 발송 최소 1초 간격 스로틀 (텔레그램 429 방지) |
| 2026-04-21 | [executor.py](executor.py), [test.py](test.py) | B1: `_limit_buy_with_retry` `fetch_order` 기반 폴링으로 전환 — 외부 취소를 체결로 오인하던 결함 제거 |
| 2026-04-20 | [CLAUDE.md](CLAUDE.md), [.claudeignore](.claudeignore), [skills/](skills/) | 토큰 절약 구조 개편: .claudeignore 추가, CLAUDE.md 슬림화, 자동점검·문서화·컨벤션을 skills/로 분리 |
| 2026-04-17 | [executor.py](executor.py) | B2: `check_stop_loss()` avg_price·total_invested 0 초기화 추가 |
| 2026-04-17 | [requirements.txt](requirements.txt) | H1: `pip freeze` 기반 requirements.txt 생성 (VPS 배포 준비) |
| 2026-04-17 | [config.py](config.py) | A9: `SCANNER_CANDLE_LIMIT` 15→30 (Wilder's Smoothing 워밍업 확보) |
| 2026-04-17 | [executor.py](executor.py) | C1: `setup_grid()` 시장가→지정가 전환, `_limit_buy_with_retry` 헬퍼 추가 |
| 2026-04-17 | [test.py](test.py) | C1: 지정가 매수 단위 테스트 1건 추가 |

---

## 다음 작업 목록 (우선순위 순)

> **2026-04-22 감사 반영** (플랜: `~/.claude/plans/streamed-launching-cascade.md`) — Phase 7 코드 완료 후 감사에서 N1~N14 도출. **N 트랙이 C 트랙(C1)보다 선행**. A 트랙 사용자 액션은 Claude 작업과 병행 가능.

---

### 🗓️ 권장 타임라인

```
Day 0 (오늘)
 ├─ 🤖 N3+N4 호출부 추가 → 테스트 → 커밋 ✅ 2026-04-22 완료
 ├─ 🤖 N1 Supabase→SQLite fallback → 테스트 → 커밋 ✅ 2026-04-22 완료
 └─ 🤖 N8 테스트 기본 모드 개편 → 커밋 ✅ 2026-04-22 완료

Day 0~1 (병행)
 ├─ 👤 A1b Supabase 프로젝트 + schema.sql 적용 ✅ 2026-04-23 완료
 └─ 👤 A4 Lightsail 생성 + setup.sh + systemctl start ✅ 2026-04-25 완료

Day 1~3
 ├─ 🤖 N2·N5·N5b ✅ 완료 / N6·N7 잔여
 ├─ 👤 B1 testnet 키 발급 ✅ 2026-04-25 완료 (`CoinTradingBot` HMAC 키)
 └─ 👤 B2 testnet 부팅 + recover_state 13건 청산 ✅ 2026-04-25 완료

Day 3~10 (1~2주 페이퍼 방치)
 ├─ 🤖 R1·R2 (리포팅 — B3 판단 전 필수)
 ├─ 🤖 N9·N10·N12·N13·N14·B7 (Medium/Low 소화)
 └─ 🤖 C 트랙 (C1~C4 백테스트 엔진) 진행 가능

Day ~14
 ├─ 🤖 R3 (B3 직전 분석 대시보드)
 └─ 👤 B3 누적 손익 검토 → MODE=live 전환 판단
```

> 💡 **권장 순서:** N1 완료(2026-04-22) — Supabase 설정 실수가 있어도 봇이 SQLite fallback 으로 기동되므로 👤 A1b 를 안전하게 진행 가능.

---

### 🤖 Claude 트랙 (N 트랙 — 감사 후 보완) `C1 리팩터 전 선결`

> 감사 Top 3 선결 과제: **N3+N4 → N1 → N8**. 상세 우선순위·영향 범위 → [TODO.md](TODO.md) "감사 결과 추가 (2026-04-22)" 섹션.

**🔴 Critical — 1순위** (전량 완료 2026-04-22)
- [x] ~~**N3+N4** (2026-04-22 완료): `snapshot_equity()` / `_log_event()` 헬퍼 + 6개 호출 지점 주입 + 회귀 테스트 3건~~
- [x] ~~**N1** (2026-04-22 완료): `persistence.init_db()` Supabase→SQLite degraded fallback + `[DEGRADED]` 텔레그램 + `DB_FALLBACK` CRITICAL 이벤트 + 회귀 테스트 3건. 운영 단일 장애점 해소~~
- [x] ~~**N2** (2026-04-22 완료): `persistence` 공개 함수 3개 자체 try-except + `_safe_notify_backend_error` (notifier 지연 import + 이중 장애 stderr fallback). `executor._log_trade`/`_log_event` 와 `main._supervise`/부트 flow 의 dead try-except 제거. 회귀 테스트 4건. 매매 흐름 격리를 모듈 자체가 보장~~

**🟠 High**
- [x] ~~**N5** (2026-04-25 완료): `recover_state()` 매도 후 `_log_trade("SELL", ...)` 호출 추가. 회귀 테스트 1건~~
- [x] ~~**N5b** (2026-04-25 완료): `recover_state()` 매도 사이 `RECOVER_SELL_THROTTLE_SEC=0.3` sleep 추가 — binance 50 orders/10s 제한 회피 (testnet 사전 잔고 다중 청산 결함 해소). 회귀 테스트 1건~~
- [ ] N6: [CLAUDE.md](CLAUDE.md) "모든 주문: 지정가 우선" 원칙에 "손절·긴급매도·recover 청산 시장가 허용" 예외 조항 (문서만)
- [ ] N7: `SupabaseBackend` 테스트 4건 (`MockAsyncpgPool` — init 실패 / write 실패 / acquire timeout / fallback 동작)

**🟡 Medium**
- [x] ~~**N8** (2026-04-22 완료): 기본 `unit` 모드에 bugfix+Phase 6/7 suite 통합 — 헬퍼 3개로 분리 + `unit3`/`unit4`/`bugfix` 하위 호환. `test_run_executor_kill` 이 업비트 API 로 KRW_RATE 를 오염시키던 테스트 격리 결함도 해소~~
- [ ] N9: `run_executor` `DAILY_LOSS_LIMIT` 킬 경로 테스트 (외부 kill_event 설정 없이 손익 누적으로 발동)
- [ ] N10: [deploy/setup.sh:31](deploy/setup.sh#L31) Python 3.11 → 3.12+ 격상 또는 `requirements.txt` VPS 버전 재생성 (로컬 3.14 호환성 확보)
- [x] ~~N11: [PROJECT.md:86](PROJECT.md#L86) 헤더 "Phase 5 기준" → "Phase 7 기준"~~ ✅ 2026-04-22 문서 수정 완료

**🟢 Low**
- [ ] N12: [deploy/daily30k.service](deploy/daily30k.service) 로그 rotate — `/etc/logrotate.d/daily30k` 설정 또는 journald 전환
- [ ] N13: [executor.py:282-299](executor.py#L282-L299) `monitor_orders` 체결 핸들러 개별 try-except (단일 주문 실패 격리)
- [ ] N14: [main.py:125-141](main.py#L125-L141) `_supervise` `max_restarts` 초과 시 `kill_event.set()` 검증 테스트
- [ ] B7: 캔들 수집 실패 감지 — 무음 처리되는 API 오류 누적 시 실패율 임계치 넘으면 알림 (screener.py)

---

### 🤖 Claude 트랙 (R 트랙 — 리포팅·모니터링) `B3 판단 지원 · 2026-04-25 추가`

> testnet 페이퍼 가동 이후 도출. 현재 `/status` 는 메모리 `daily_pnl` 만 보여주고 누적 손익·추세·리스크 지표는 Supabase SQL 수동 조회만 가능. B3 전환 판단일 (~2026-05-09 전후) 전에 적어도 **R1** 은 필수.

- [ ] R1: `/status` 응답에 **누적 손익** 포함 — `notify_status()` 에서 Supabase `trades` `SUM(pnl)` 조회 추가. `persistence.get_total_pnl(mode)` 헬퍼 신설 + 회귀 테스트 1건
- [ ] R2: 일간/주간 손익 리포트 **자동 텔레그램 발송** — `run_reporter()` 컴포넌트 신설 (asyncio.gather 4번째 태스크). 자정 KST + 매주 월 오전 9시 발송. 손익·승률·MDD·평균 손익 포함
- [ ] R3: B3 판단용 **분석 대시보드** — `reports/summary.py` CLI (`python -m reports.summary --mode testnet --period 7d`) 승률·평균 손익·MDD·샤프비·일별 히트맵. `equity_snapshots` + `trades` 조인 기반. R2 출력부로 재사용

---

### 🤖 Claude 트랙 (C 트랙 — 백테스트 엔진) `N 트랙 Top 3 후 진행`

A 와 독립. 로컬 개발 환경에서 진행. **C1 전 반드시 N3+N4 → N1 → N8 해소 (감사 권고).**
- [ ] C1: Exchange 인터페이스 추상화 — `exchanges/base.py`, `ccxt_exchange.py`, `backtest_exchange.py`. GridEngine 이 추상 인터페이스만 참조하도록 `executor.py` 리팩터 (ccxt 의존 지점 약 25개 — 감사 보고서 §3-4 참조)
- [ ] C2: `backtest/data.py` — `ccxt.fetch_ohlcv` 로 과거 1분봉 다운 → parquet 저장
- [ ] C3: `backtest/simulator.py` + `backtest/runner.py` — 시간 이동 tick 주입 + 파라미터 스윕
- [ ] C4: `backtest/results.py` — 손익곡선·MDD·샤프비·승률 리포트

---

### 👤 사용자 트랙 (외부 서비스 셋업)

#### 🟢 지금 즉시 병행 가능 (Claude 작업과 독립)

**A 트랙 — 운영 인프라 (Supabase + Lightsail)** — 코드 완료 2026-04-21, 사용자 액션만 남음

- [x] A1-code: `deploy/schema.sql` 작성 (trades + equity_snapshots + bot_events)
- [x] A2: `persistence.py` asyncpg 듀얼 백엔드 (SqliteBackend / SupabaseBackend, async 인터페이스)
- [x] A3: `config.py` DB_BACKEND·SUPABASE_DB_URL, `.env.example` 갱신, `requirements.txt` asyncpg==0.30.0
- [x] A5: `deploy/daily30k.service`, `setup.sh`, `update.sh` 작성
- [x] **A1b** (2026-04-23 완료): Supabase 프로젝트 생성 (서울 리전) + `deploy/schema.sql` 적용 + Pooler(6543) URI `.env` 기입. 로컬 `asyncpg` 검증 (Postgres 17.6, 3 테이블 컬럼 1:1 일치)
- [ ] **A4** (사용자, ~30분): AWS Lightsail 인스턴스 생성 (서울, $5, Ubuntu 22.04) → SSH 접속 → `bash deploy/setup.sh` 실행 → `.env` 에 Supabase URI·바이낸스 키 입력 → `sudo systemctl start daily30k`

#### 🟡 A 완료 후 진행

**B 트랙 — 페이퍼 트레이딩 실연결**

- [ ] **B1** (사용자): https://testnet.binance.vision 가입 → HMAC 키 발급 → 서버 `.env` 에 `MODE=testnet` + `BINANCE_TESTNET_API_KEY` + `BINANCE_TESTNET_SECRET_KEY` 기재
- [ ] **B2** (사용자): `sudo systemctl restart daily30k` → 텔레그램 부팅 메시지 `[MODE=TESTNET]` 확인 · Supabase `trades` 테이블 행 증가 검증

#### 🔴 1~2주 페이퍼 누적 후

- [ ] **B3** (사용자): 1주일 누적 손익 리포트 리뷰 → `MODE=live` 전환 여부 판단 → 실거래 바이낸스 HMAC 키 발급 (IP 화이트리스트·출금권한 OFF) → `.env` `MODE=live` + `BINANCE_API_KEY`/`BINANCE_SECRET_KEY` 기재 → `sudo systemctl restart daily30k`

---

## 완료된 작업

<details>
<summary>전체 이력 (클릭하여 펼치기)</summary>

| 날짜 | ID | 내용 |
|------|----|------|
| 2026-04-25 | OPS1b | `deploy/advise.sh` 에 **배포 필요성 판정 로직** 추가. `classify_file()` 헬퍼가 변경 파일을 3등급(**skip** = 런타임 미관여 문서/스킬 / **optional** = 서버 참조 가능한 도구(`advise.sh`/`.env.example`/`test.py`) / **required** = 런타임·systemd·Supabase 로드(`*.py` 대부분 / `requirements.txt` / `deploy/{schema.sql,daily30k.service,setup.sh,update.sh}`)) 으로 분류. 최상단에 🚨/🟢/🔘 배지 출력, 파일별 [필요]/[선택]/[불필요] 태그, 말미 명령 블록 상태별 분기(SKIP→git push만 / OPTIONAL→선택적 `git pull --ff-only` / REQUIRED→update.sh 표준). `[STANDARD]` 섹션도 REQUIRED 일 때만 노출. `skills/deploy-advisor.md` 의 제외 조건 목록 삭제 → "세션에서 1개라도 파일 수정 시 항상 실행, 판정은 스크립트가 담당" 으로 단순화. 사용자 요청 "배포가 필요한지도 알려줘" 반영. 4개 케이스(SKIP / OPTIONAL / REQUIRED-main.py / REQUIRED+TIMING-executor.py) 검증 통과 |
| 2026-04-25 | OPS1 | 배포 가이드 시스템 구축 — 페이퍼 운영 중 코드 변경을 Lightsail 에 반영할 때 `update.sh` 만으로는 누락되는 단계(.env 수동 추가·Supabase ALTER TABLE·daemon-reload·매매 로직 재시작 타이밍)를 자동 안내. **`deploy/advise.sh`** (핵심 진단 엔진, 120줄): `--files`/`--since=`/unpushed 3모드, 변경 파일 유형별로 🔴 BEFORE DEPLOY (deploy/schema.sql) → 🟠 ENV UPDATE (.env.example 신규 env 자동 diff 추출) → 🟠 SYSTEMD RELOAD (daily30k.service) → 🟡 TIMING WARNING (executor/screener, 50+줄 변경 시 추가 경고) → 🟢 AUTO (requirements.txt) → 🟢 STANDARD 순으로 출력. 끝에 표준 배포 명령(ssh 주소·update.sh 실행·로그 tail) 공통 블록. **`skills/deploy-advisor.md`** (Claude 규칙): `*.py`/`deploy/*`/`.env.example`/`requirements.txt` 수정 세션에서만 트리거, `WORKFLOW.md`/`TODO.md`/`skills/*` 단독 수정 시 침묵. **`CLAUDE.md`** 온디맨드 스킬 섹션 1줄 추가. 로직 중복 없음 (Claude 스킬이 스크립트 출력을 그대로 인용). 6개 테스트 케이스 수동 검증 통과: schema/env/service/trading/docs-only/복합(schema+env+executor) |
| 2026-04-25 | A4+B1+B2 | 👤 사용자 액션 완료 — AWS Lightsail $7 플랜 (서울 `ap-northeast-2`, 1GB RAM, Ubuntu 22.04, IP `3.36.26.177`) 인스턴스 생성. 본인 GitHub repo `luodkrap/Daily_30k_bot` public 전환 후 `git clone` → `bash deploy/setup.sh` 통과 (Python 3.11 + venv + requirements + systemd unit). testnet HMAC 키 발급 (`CoinTradingBot`, TRADE/USER_DATA/USER_STREAM 권한) → `.env` 작성 (chmod 600) → `systemctl start daily30k`. 첫 부팅에서 testnet 사전 잔고 다중 청산이 binance 429 폭주로 실패 → **N5b throttle 패치 후 `bash deploy/update.sh` 재반영** → 13건(WAN/FUN/MDT/FIO/OXT/UTK/DEXE/GMT/BIFI/JUP/VANA/SOPH/AT) 정상 청산 + dust/fiat 스킵 + 환율 갱신까지 정상 진입. 페이퍼 트레이딩 1~2주 누적 단계 진입 (B3 시점에 live 전환 판단) |
| 2026-04-25 | N5+N5b | `executor.py` `recover_state()` 매도 루프 보강 — (1) **N5**: 청산 매도 직후 `_log_trade(symbol, "SELL", sell_qty, fill_price, 0.0, 0.0)` 호출 추가. emergency 청산은 평균매수가/수수료 정보 없으므로 fee/pnl 0.0 으로 기록. (2) **N5b**: 매도 try 블록 끝과 except 블록 양쪽에 `await asyncio.sleep(RECOVER_SELL_THROTTLE_SEC=0.3)` 추가 — binance create_order rate limit (50/10s) 회피. 모듈 상단에 throttle 상수 분리. 회귀 테스트 2건 (`test_n5_recover_logs_trade_on_liquidation`: 2개 자산 청산 시 SELL 2건 기록 검증; `test_n5b_recover_throttles_between_sells`: `executor_mod.asyncio.sleep` 몽키패치로 0.3s sleep 호출 횟수 ≥3 검증). 사용자 A4 첫 부팅 시 testnet 사전 잔고 (WBTC/DEXE/GMT/JUP 등) 다중 청산이 429 폭주로 RECOVER_STATE 절반 실패하던 환경 특이점 해소 |
| 2026-04-23 | A1b | 👤 사용자 액션 완료 — Supabase 프로젝트 생성 (서울 리전 `ap-northeast-2`, Free 플랜) → SQL Editor 에 [deploy/schema.sql](deploy/schema.sql) 적용 (멱등 `IF NOT EXISTS`) → **Transaction Pooler (6543 포트)** URI `.env` `SUPABASE_DB_URL` 기입 + `DB_BACKEND=supabase` 전환. 로컬 `asyncpg==0.30.0` 설치 후 검증 스크립트로 Postgres 17.6 접속 확인, 3개 테이블(`trades`/`equity_snapshots`/`bot_events`) 존재·컬럼명·타입 모두 [deploy/schema.sql](deploy/schema.sql) 과 1:1 일치 확인. 운영 DB 블로커 해소 — 남은 사용자 액션은 A4(Lightsail) 1건뿐 |
| 2026-04-22 | N2 | `persistence.py` — 공개 함수 3개(`record_trade`·`record_equity_snapshot`·`record_event`) 에 `try/except` + `_safe_notify_backend_error` 내장 (notifier 지연 import, notifier 자체 실패 시 `print` fallback 으로 이중 삼킴). 설계 원칙 "기록 실패가 매매 흐름을 차단하지 않음" 을 호출부가 아닌 모듈 자체가 보장. `executor._log_trade`/`_log_event` 및 `main._supervise`/부트 flow 의 persistence 전용 `try/except` 4곳을 dead code 로 간주하고 제거 (`snapshot_equity` 는 `fetch_balance`/`fetch_ticker` 예외도 잡으므로 유지). 회귀 테스트 4건: `test_n2_record_trade_swallows_backend_error`, `test_n2_record_event_swallows_backend_error`, `test_n2_record_equity_snapshot_swallows_backend_error`, `test_n2_notifier_failure_also_swallowed` (`_FailingBackend` + `notifier.notify_error` 몽키패치). Critical 트랙 전량 해소 |
| 2026-04-22 | N8 | `test.py` — `python test.py` 기본 `unit` 모드에 bugfix+Phase 6/7 suite 통합. 헬퍼 3개 (`_run_phase3`/`_run_phase4`/`_run_bugfix_phase67`) 로 분리 + `unit3`/`unit4`/`bugfix` 모드 하위 호환 유지. Phase 4 `test_run_executor_kill` 이 `update_krw_rate()` 로 실제 업비트 API 를 타서 `config.KRW_RATE` 를 실시간 환율로 덮어쓰던 테스트 격리 결함을 `_run_bugfix_phase67` 진입 시 KRW_RATE/SEED 기본값 복원으로 해소. C1 리팩터 안전망 확보 |
| 2026-04-22 | N1 | `persistence.py` — `init_db()` Supabase 실패 시 SQLite degraded fallback (`sqlite_fallback` 반환). `_last_fallback_reason` 저장 + `get_fallback_reason()` API. `main.py` — fallback 감지 시 `[DEGRADED]` 텔레그램 + `DB_FALLBACK` CRITICAL 이벤트 기록. 회귀 테스트 3건 (`test_n1_supabase_init_failure_falls_back_to_sqlite`, `test_n1_fallback_reason_exposed_for_alert`, `test_n1_sqlite_native_failure_not_swallowed`). 운영 단일 장애점 해소 — Supabase DNS/Pool/스키마 오류가 봇 기동을 차단하지 않음 |
| 2026-04-22 | N3+N4 | `executor.py` — `snapshot_equity()` 헬퍼 (USDT 잔고 + 비-USDT 포지션 평가액 합산) + `_log_event()` 헬퍼 추가. `run_executor` 30분 타이머에 equity snapshot 편승, 6개 지점에 `record_event` 주입 (EXECUTOR_START / KILL_SWITCH / DAILY_STOP / MARKET_FILTER 전환 / RECOVER_STATE 완료·실패 / SUPERVISOR_RESTART `main.py`). 회귀 테스트 3건 (`test_n3_snapshot_equity_records_positions`, `test_n4_market_filter_logs_transition_event`, `test_n4_recover_state_logs_event`) |
| 2026-04-22 | Audit 3/3 | `project-auditor` 전체 감사 — A 트랙·Phase 6·버그픽스 누적 반영. N1~N14 개선 항목 도출. C1 전 선결 Top 3 = N3+N4 → N1 → N8. 주요 발견: A2 `equity_snapshots`/`bot_events` 호출부 미구현 (N3/N4), `SupabaseBackend.init()` 실패 시 봇 기동 불가 단일 장애점 (N1), `recover_state` 청산 `_log_trade` 누락 (N5). 플랜: `~/.claude/plans/deep-jingling-frog.md` |
| 2026-04-22 | N11 | [PROJECT.md:86](PROJECT.md#L86) 파일 구조 표 헤더 "Phase 5 기준" → "Phase 7 기준" 수정. 감사에서 발견된 문서 버전 오래됨 해소 |
| 2026-04-21 | A2 | `persistence.py` 전면 리팩터 — `SqliteBackend` / `SupabaseBackend` 두 클래스, 모듈 레벨 함수는 `config.DB_BACKEND` 싱글톤 분기. 인터페이스를 `async` 로 전환 (호출부 `await persistence.record_trade(...)`). `equity_snapshots`·`bot_events` 테이블·insert 헬퍼 추가. `main.py` / `executor.py` 호출부 수정. asyncpg 지연 임포트로 sqlite 경로는 미설치여도 동작. 회귀 테스트 2건 재작성 + `test_persistence_equity_and_events` 신규 1건 |
| 2026-04-21 | A3 | `config.py` `DB_BACKEND`·`SQLITE_DB_PATH`·`SUPABASE_DB_URL` 환경변수 추가. `.env.example` DB 섹션 + Supabase Pooler URI 안내 주석. `requirements.txt` `asyncpg==0.30.0` |
| 2026-04-21 | A1-code, A5 | `deploy/schema.sql` (Supabase Postgres 스키마 3테이블, IF NOT EXISTS 멱등). `deploy/daily30k.service` (systemd unit, MemoryMax=512M Lightsail OOM 방지). `deploy/setup.sh` (Ubuntu 22.04 초기 프로비저닝). `deploy/update.sh` (git pull + 조건부 pip install + restart) |
| 2026-04-21 | Phase6-a | Phase 6 페이퍼 트레이딩 인프라 구축 — `config.py` MODE=live/testnet 분기 + testnet 전용 API 키 env 분리 로드, `main.py` `set_sandbox_mode(True)` + sandbox URL assert + 부팅 메시지 `[MODE=...]` 표기, `persistence.py` 신규 (SQLite `trades.db`: id/ts/symbol/side/qty/price/fee/pnl/mode, `threading.Lock` + `asyncio.to_thread`), `executor.py` BUY/SELL 양방향 체결 훅 (setup_grid 초기 매수·_handle_buy_fill·_record_trade), `.env.example` testnet 키 필드 + 가입 안내, `.gitignore` sqlite journal 추가. 회귀 테스트 5건 (`test_mode_branch_live/testnet/invalid`, `test_persistence_init_and_roundtrip`, `test_record_trade_hook_called_on_sell`) |
| 2026-04-21 | B5 | `screener.py` — `_score_and_rank()` stability_score 를 후보군 CV min-max 정규화로 전환. 구 공식 `max(0, 1 - cv/0.05)` 은 CV>5% 코인을 전부 0점 clamp → 가중치 20% 실효 없음. ATR·volume 점수와 동일한 상대 정규화 방식으로 통일. 회귀 테스트 1건 (`test_b5_stability_score_minmax_normalized`) |
| 2026-04-21 | B3 | `executor.py` — `setup_grid()` 마지막 레벨에 `fill_qty - placed_sum` 잔량 사용. `_handle_buy_fill()` 에 `total_qty - Σ기배치` 상한 적용. stepSize 반올림 누적으로 매도 총합이 보유량 초과하던 insufficient balance 결함 제거. 회귀 테스트 2건 (`test_b3_setup_grid_sell_qty_within_holdings`, `test_b3_handle_buy_fill_caps_sell_qty`) |
| 2026-04-21 | C2 | `executor.py` — `recover_state()` 추가. 재시작 시 전 심볼 미체결 주문 취소 + 비-USDT/BNB/스테이블 잔고 시장가 매도 (MIN_NOTIONAL 미달 dust 스킵). `run_executor` 메인 루프 진입 전 1회 실행. 회귀 테스트 4건 (`MockExchangeRecovery` subclass) |
| 2026-04-21 | H2 | `notifier.py` — 동일 메시지 60초 dedup + 전체 발송 최소 1초 간격 스로틀. `_deliver` hook 분리로 테스트 격리. 회귀 테스트 2건 추가 |
| 2026-04-21 | B1 | `executor.py` — `_limit_buy_with_retry` `fetch_order` 기반 폴링. 외부 취소/부분체결/filled=0 closed 엣지 분기. `test.py` 회귀 테스트 추가 |
| 2026-04-17 | B2 | `executor.py` — `check_stop_loss()` avg_price·total_invested 미초기화 수정. emergency_sell/regrid와 일관성 확보 |
| 2026-04-17 | B2 | `executor.py` — `check_stop_loss()` `avg_price`·`total_invested` 미초기화 수정 |
| 2026-04-17 | A9 | `config.py` — `SCANNER_CANDLE_LIMIT` 15→30 변경. Wilder's Smoothing 워밍업 확보 |
| 2026-04-17 | H1 | `requirements.txt` 생성 (`pip freeze`, Python 3.14 venv 기반, VPS 배포 준비) |
| 2026-04-17 | C1 | `executor.py` — `setup_grid()` 시장가→지정가 교체. `_limit_buy_with_retry` 헬퍼 도입. setup 실패 시 engine=None 복구. 테스트 1건 추가 |
| 2026-04-15 | A8 | `executor.py` — 수수료 모델 일원화 (매수 시점 차감 / 매도 경로 4곳은 매도 수수료만). 테스트 2건 추가. venv 재생성(python3.14) |
| 2026-04-15 | H4 | `main.py` — `_supervise()` 패턴 (자동 재시작 최대 5회, 한도 초과 시 킬 이벤트) |
| 2026-04-15 | A7 | `executor.py` — 연패 감지 `consecutive_losses ≥ 3` → `is_market_healthy=False` 자동 전환 |
| 2026-04-15 | A6 | `executor.py:339` — `regrid()` 매수 수수료 누락 수정 |
| 2026-04-15 | C4 | `executor.py:481` — regrid 트리거에 `not engine.buy_orders` 조건 추가 |
| 2026-04-02 | H3 | `PROJECT.md` — Phase 4/5 완료 반영 + 파일 구조 표 추가 |
| 2026-04-02 | C3 | `executor.py` — `check_stop_loss()` + `emergency_sell()` 매수 수수료 누락 수정 |

</details>

---

## 작업 방식 원칙
1. **한 번에 하나.** 최상위 항목 하나만 완료 후 다음으로.
2. **테스트 필수.** 코드 수정 후 반드시 `python test.py` 실행.
3. **즉시 기록.** 완료 즉시 이 파일 업데이트 (완료 테이블 추가 + 항목 삭제 + 파일 변경 이력 갱신).
4. **세션 종료 전.** 미완성 작업은 "현재 작업" 섹션에 템플릿대로 기록 (진행도%, 다음 명령어, 블로커).
