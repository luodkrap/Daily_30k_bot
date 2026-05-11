# TODO — Daily 30K Bot

> **🗓️ 2026-04-22 로드맵 플랜:** `~/.claude/plans/streamed-launching-cascade.md`
> **상세 진행 방식:** [WORKFLOW.md](WORKFLOW.md)

---

## 👤 사용자 액션 남은 것 (외부 서비스 셋업)

> Claude 가 대행 불가한 작업. Claude 의 N 트랙 작업과 **병행 가능**.

### 🟢 지금 즉시 병행 가능

- [x] **A1b** (2026-04-23 완료): Supabase 프로젝트 생성 (서울 리전) + `deploy/schema.sql` 적용 + Pooler(6543) URI `.env` 기입. 로컬 `asyncpg` 검증 통과 — Postgres 17.6 연결 OK, 3개 테이블 컬럼·타입 1:1 일치
- [x] **A4** (2026-04-25 완료): AWS Lightsail $7 플랜 (서울, 1GB RAM, Ubuntu 22.04, IP `3.36.26.177`) → repo 클론 (`luodkrap/Daily_30k_bot` public 전환) → `bash deploy/setup.sh` 통과 → `.env` 작성 (testnet 키 + Supabase Pooler URI 적용) → `sudo systemctl start daily30k` 정상 기동. 첫 부팅에서 testnet 사전 잔고 다중 청산이 binance 429 폭주로 실패 → N5b throttle 코드 패치 후 `update.sh` 재반영 → 13건 청산 성공

### 🟡 A1b + A4 완료 후

- [x] **B1** (2026-04-25 완료): https://testnet.binance.vision HMAC API 키 발급 (`CoinTradingBot`, TRADE/USER_DATA/USER_STREAM 권한) → 서버 `.env` `MODE=testnet` + `BINANCE_TESTNET_API_KEY/SECRET_KEY` 기재 (chmod 600)
- [x] **B2** (2026-04-25 완료): A4 마지막 단계와 동시 검증 — 텔레그램 부팅 메시지 `[MODE=TESTNET]` 확인 + N5b 패치 후 testnet 사전 잔고 13개 청산이 Supabase `trades` 테이블에 기록됨

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

**🟢 관찰 모드 (2026-04-28~)** — 페이퍼 트레이딩 자연 누적 중. 사용자 손 떼고 며칠 지켜본 후 결정.

다음 진입: 🤖 **R1** (`/status` 누적 손익 표시) — Day 7 (~05/05) 즈음 권장, 늦어도 Day 12 (~05/10) 까지. **B3 판단(2026-05-09 전후) 직전 필수.**

보류 (페이퍼 데이터 정확성에 영향 없음): N15(BUY pnl 음수) / N16(WBTC LOT) / N17(fetch_open_orders 경고) / N18(시장 악화 자동 전환). 새 세션에서도 그대로 보류 권장.

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

- [x] 🤖 ~~N12 (2026-05-04 완료): `deploy/daily30k.service` `StandardOutput/Error=journal` + `SyslogIdentifier=daily30k` 전환. systemd-journald 자동 timestamp(microsecond UTC) + auto-rotate + `journalctl --since` 시간쿼리 + `-p err` 에러 필터. setup.sh/update.sh/advise.sh 로그 명령 갱신. 회귀 테스트 1건. 4/28~5/4 6일 hang 사후 디버깅 거의 불가능했던 게 동기~~
- [ ] 🤖 N13: `executor.py:282-299` `monitor_orders` 단일 주문 실패가 사이클 중단 → 체결 핸들러 개별 try-except
- [ ] 🤖 N14: `main.py:125-141` `_supervise` `max_restarts` 초과 시 `kill_event.set()` 호출 검증 테스트 없음

**🔴 안전 패치 (2026-05-04 hang 사건 후 신설, 모두 완료)**

- [x] 🤖 ~~**N19** (2026-05-04 완료): `BotState.executor_heartbeat: float = 0.0` 추가 + `_supervise(watchdog_timeout=600.0, heartbeat_attr="executor_heartbeat")` 매개변수 추가 — executor 만 600초 무갱신 시 task 강제 cancel → TimeoutError 변환 → 기존 재시작 경로 재사용 + SUPERVISOR_RESTART 페이로드 `is_watchdog: true`. heartbeat 갱신 위치 2곳 (executor 메인 루프 1초마다 / recover_state 매 자산 처리 시작점). recover_state 시그니처 `(exchange, state=None)` 옵셔널 추가. 회귀 테스트 2건~~
- [x] 🤖 ~~**N20** (2026-05-04 완료): `_retry_api(timeout=60.0)` 매개변수 추가 — 각 시도를 `asyncio.wait_for` 로 감싸 ccxt 외부 await(fetch_balance/fetch_ticker/fetch_ohlcv/fetch_open_orders/cancel_order/create_order)이 영원히 hang 되지 않도록. 타임아웃은 일반 예외와 동일하게 다음 시도로 넘어감(지수 백오프 1→2→4초). 회귀 테스트 2건~~
- [x] 🤖 ~~**N22** (2026-05-04 완료): `main.py` 의 `init_db()` 결과를 무조건 stdout 으로 `print(f"[init_db] backend={backend_used}")`, fallback 시 stderr 로 `print(f"[init_db] FALLBACK reason={reason}")` 출력. 5/4 02:43 KST 부팅 시 Supabase 일시 끊김 → SQLite fallback 발동했으나 [DEGRADED] 텔레그램 알림이 일시 NetworkError 로 누락 → 16시간 후 도울님 "DB에 데이터 잘 쌓이고 있어?" 질문으로 발견된 사건의 처방. 텔레그램은 외부 의존 (네트워크/dedup) 으로 신뢰성 한계, journal 은 systemd 보장 + N12 이미 timestamp/auto-rotate 확보. 회귀 테스트 1건 (정적 검사). 다음 세션에서 Lightsail 배포 필요~~

**🟡 5/4 사건 후속 (2026-05-04 추가)**

- [ ] 🤖 N23 (Medium): `init_db()` fallback 발생 시 30분마다 백그라운드 task 가 Supabase 재연결 시도 → 성공 시 `_backend` 싱글톤을 SupabaseBackend 로 교체. 5/4 사건처럼 16시간 SQLite 갇혀있는 상황 자동 회복용. R1 진행 시점에 같이 작성. 주의: 교체 시 진행 중 write 와의 race condition 고려 (asyncio.Lock 또는 atomic 교체)
- [ ] 🤖 N24 (Medium): `reports/backfill_sqlite.py` — 5/4 02:43~19:26 SQLite 119건을 Supabase 로 옮기는 일회성 백필. 중복 INSERT 방지 (ts + symbol + side 키로 ON CONFLICT DO NOTHING). R1 분석 직전 1회 사용. trades / equity_snapshots / bot_events 3 테이블 대상

**🔴 5/8~5/11 사건 신규 결함 (2026-05-08 추가, 5/11 갱신)**

- [x] 🤖 ~~**N27** (2026-05-11 완료): **DAILY_STOP 봇 종료 결함 패치** — 5/10 20:08 KST 일일 목표 달성(+16,249원) 후 텔레그램·Supabase 둘 다 24시간+ 침묵 사건. 원인 100% 확정: N26 패치(5/9)에서 spam 방지를 위해 추가된 `state.kill_event.set()` 이 [main.py:147](main.py#L147) `while not state.kill_event.is_set()` 종료 조건과 결합 → main 의 모든 _supervise(screener/executor/telegram) 종료 → main() 정상 exit(0) → systemd `Restart=on-failure` ([deploy/daily30k.service:13](deploy/daily30k.service#L13)) 정책상 정상 종료는 재시작 안 함 → **봇 영구 종료** → 자정 자동 재개 불가능 (자정 리셋 분기 [executor.py:713-718](executor.py#L713-L718) 가 메인 루프 안에 있는데 break 후 영원히 도달 불가). 패치: DAILY_STOP 분기에서 `kill_event.set()` 제거 + 자정까지 sleep loop(`asyncio.wait_for(state.kill_event.wait(), timeout=30)` 폴링으로 외부 종료 즉시 응답 + 30초마다 자정 체크) + `state.executor_heartbeat = time.time()` 갱신(N19 watchdog 회피) + 자정 도달 시 `state.reset_daily()` + `[리셋] {today} 일일 집계 초기화 — 매매 재개` 텔레그램 + `DAILY_RESUME` 이벤트 + `engine = None` 후 `continue`. KILL_SWITCH 분기는 그대로(손실 한도는 명시적 종료가 정답). 회귀 테스트 1건(`test_n27_daily_stop_does_not_terminate_supervisor`): spy_log_event 로 DAILY_STOP 기록 직후 `state.kill_event.is_set() is False` 동적 단언 + run_executor 소스 정적 검증(`reset_daily`/`DAILY_RESUME` 존재 + `kill_event.set` 부재). 전체 단위 테스트 통과. **배포 대기**: `git push` + `bash deploy/update.sh`~~
- [ ] 🤖 **N25 (High, 미해결)**: **engine idle 결함** — 5/5 16:48 KST 73시간 정지 + **5/9 00:02:37 KST 14시간+ 정지 (재발)**. 5/9 사건의 결정타: equity_snapshot 30분 끊김(5/8 19:21 마지막 적재) → executor 메인 루프 line 749 30분 타이머 분기 진입 못 함. KILL_SWITCH/DAILY_STOP 트리거 여부와 무관하게 메인 루프 자체가 어떤 await 에 갇힌 것 확정. N19/N20 watchdog(600초 timeout)이 잡아야 하는데 못 잡았다면 ccxt 가 timeout 안 먹히는 path 가 있다는 신호. 처방 후보: (1) **재발 시 즉시 `py-spy dump --pid <PID>` 로 정확한 stack trace 확보** → 갇힌 await 위치 확정 후 재현 테스트 + 패치, (2) "마지막 거래 시각" watchdog 추가 (예: 4시간 무거래 시 강제 engine=None reset + 스캐너 재진입), (3) `monitor_orders` / `_get_current_price` / `regrid` 내부의 ccxt 호출도 `_retry_api` 경유하도록 통일. **B3 전환 차단 조건 1순위** (5/8 재시작 후 5시간 만에 재발했으므로)
- [x] 🤖 ~~**N26** (2026-05-09 완료): **DAILY_STOP / KILL_SWITCH spam 결함 패치** — 5/5 03:35~08:59 4,679건 + 5/9 00:00:28~00:02:34 3,562건 두 차례 발생. 원인 100% 확정: [executor.py:734-745](executor.py#L734-L745) DAILY_STOP + [executor.py:721-732](executor.py#L721-L732) KILL_SWITCH 두 분기 모두 `if engine: await engine.emergency_sell(reason)` 호출이 ccxt 예외를 던지면 outer `except Exception as e:` (line 805) 가 잡아 `state.kill_event.set()` 와 `break` 둘 다 도달 못 함 → 무한 spam (4초 = 1초 sleep + emergency_sell ccxt timeout 약 3초). 패치: 두 분기 모두 (1) `state.kill_event.set()` 을 emergency_sell **보다 먼저** 호출, (2) emergency_sell 호출을 `try/except Exception: notify_error(...)` 로 감싸 예외 swallow + 가시화, (3) break 가 try 블록 밖에서 무조건 실행. 회귀 테스트 2건 (`test_n26_daily_stop_no_spam_when_emergency_sell_raises`, `test_n26_kill_switch_no_spam_when_emergency_sell_raises`): 5초 안전망 + 결함이면 N건/패치 후 1건 검증. 전체 단위 테스트 통과~~

**페이퍼 운영 중 발견 (2026-04-28 D1 완료 후 추가)**

- [ ] 🤖 **N15** (Medium): BUY 행 pnl 이 -149원 등 음수로 기록됨 (Supabase trades 확인). 매수는 PnL 0이 정상. `_handle_buy_fill` 또는 `setup_grid` 의 `_log_trade("BUY", ...)` 호출부에서 잘못된 인자 전달 의심. 회귀 테스트 1건 + 호출부 점검
- [ ] 🤖 N16 (Low): `recover_state` WBTC 등 일부 자산 청산 시 `MARKET_LOT_SIZE` 필터 위반 → `amount_to_precision` 적용 후에도 stepSize 미정렬. testnet 일부 페어 LOT_SIZE 정밀도 추가 처리
- [ ] 🤖 N17 (Low): `recover_state` `fetch_open_orders` symbol 미지정 호출 시 ccxt 경고 (rate limit 10배). symbol 별 순회 또는 `warnOnFetchOpenOrdersWithoutSymbol=False` 설정
- [ ] 🤖 **N18** (Medium): 페이퍼 운영 중 testnet 작은 손실로도 `RECENT_LOSS_STREAK` 발동 → `is_market_healthy=False` 신규 진입 차단. 회복 조건(현재 없음 — 일일 리셋만) 추가 또는 testnet 모드 임계값 완화 검토. B3 판단 데이터 누적에 직접 영향

### 🤖 리포팅·모니터링 기능 (2026-04-25 추가) — B3 판단 지원

> 테스트넷 페이퍼 트레이딩 가동(2026-04-25) 이후 실제 운영 경험에서 도출 — 현재 `/status` 는 메모리 `daily_pnl` 만 보여주고 누적/추세/리스크 지표는 Supabase SQL 수동 조회만 가능. B3 (~2026-05-09 전후 live 전환 판단) 이 다가오기 전에 핵심 지표를 텔레그램에서 바로 확인할 수 있어야 한다.

**중간 (Medium) — B3 판단 전에 적어도 R1은 필수**

- [ ] 🤖 R1: `/status` 응답에 **누적 손익** 포함 → `notify_status()` 에서 Supabase `trades` 테이블 `SUM(pnl)` 쿼리 (현재 mode 기준) 추가. 일일/누적 병행 표시. `persistence.get_total_pnl(mode)` 헬퍼 신설. 회귀 테스트 1건
- [ ] 🤖 R2: 자동 일간/주간 손익 리포트 텔레그램 발송 → `main.py` 에 `run_reporter()` 컴포넌트 추가 (asyncio.gather 4번째 태스크). 매일 자정 KST + 매주 월요일 오전 9시 발송. 포함 필드: 기간 손익·거래 횟수·승률·최대 낙폭·평균 건당 손익. 중복 방지용 `last_report_date` 상태 저장

**중간-높음 (Medium-High) — B3 시점에 있으면 강력**

- [ ] 🤖 R3: B3 판단용 **분석 대시보드** → `reports/summary.py` 모듈 신설. CLI 도구 (`python -m reports.summary --mode testnet --period 7d`) 로 승률·평균 손익·최대 낙폭(MDD)·샤프 비율·일별 손익 히트맵 출력. `equity_snapshots` + `trades` 조인 기반. R2 자동 리포트의 출력부로 재사용 가능하도록 함수 분리

### 🤖 운영 자동화 (2026-04-25 추가) — 배포 실수 방지

> 페이퍼 운영 중 코드 변경을 Lightsail 에 반영할 때 `update.sh` 만으로는 누락되는 단계(.env 수동 추가 / Supabase ALTER TABLE 선행 / daemon-reload / 매매 로직 재시작 타이밍)가 있어 자동 안내 시스템 구축.

- [x] 🤖 OPS1 (2026-04-25 완료): [deploy/advise.sh](deploy/advise.sh) 진단 엔진 + [skills/deploy-advisor.md](skills/deploy-advisor.md) Claude 규칙. 변경 파일 유형별로 🔴 BEFORE DEPLOY (schema) / 🟠 ENV UPDATE / 🟠 SYSTEMD RELOAD / 🟡 TIMING WARNING / 🟢 AUTO / 🟢 STANDARD 6 등급 가이드 출력. `--files` `--since=` `unpushed` 3가지 모드. 6개 테스트 케이스 수동 검증 통과. [CLAUDE.md](CLAUDE.md) 온디맨드 스킬 섹션에 참조 추가
- [x] 🤖 OPS1b (2026-04-25 완료): **배포 필요성 판정** 추가 — `classify_file()` 헬퍼가 파일을 skip(문서/스킬) / optional(도구·.env.example·test.py) / required(런타임 Python·systemd·schema) 3등급 분류 → 최상단 🚨/🟢/🔘 배지 + 파일별 태그 + 상태별 말미 명령 분기. skills 제외 조건 삭제(판정은 스크립트 전담). "배포해야 하나?" 의문 자동 해소. 4개 케이스 검증 통과

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
