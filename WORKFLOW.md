# WORKFLOW — Daily 30K Bot

> **세션 인수인계 문서.** 새 세션 시작 → 이 파일만 읽으면 10초 내 상태 파악 가능.  
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

---

## 🔲 빠른 상태 (Quick Status)

| 항목 | 값 |
|------|----|
| **현재 Phase** | **Phase 7 운영 — N29 KILL_SWITCH 가시성·사망 알림 패치 완료, 배포 대기 (2026-05-15 KST)**. 5/13 13:09 KST testnet 가짜 폭락(testnet 가격 피드 mainnet 과 -9% 괴리: $81,168 vs $73,706)으로 손절매·KILL_SWITCH 연쇄 발동 → 봇 정상 종료(exit 0) → systemd `Restart=on-failure` 정책상 재시작 안 함 → **34시간 침묵** (도울님 /status 무응답으로 5/14 23:36 발견). Supabase 직접 진단으로 mode=testnet 확정·실손실 없음 확인. 두 결함 추출: **N29-B** `_log_event` 가 텔레그램·Supabase 만 호출하고 stdout 미출력 → KILL_SWITCH 시 journal 에 종료 라인만 4건, 사건 메시지 0건. 패치: `executor._log_event()` 가 CRITICAL/ERROR/WARN/WARNING 시 stdout 동시 출력(INFO 제외로 폭주 방지). **N29-A** 봇 사망 자체에 대한 외부 알림 부재 → 텔레그램 핸들러도 같이 죽어 봇 내부 알림 불가. 패치: `deploy/notify_death.sh` 신규 + `daily30k.service` `ExecStopPost` 훅 — systemd 가 직접 호출하므로 정상 종료·실패·OOM 모두 텔레그램 알림. `Restart=on-failure` 정책 유지(손실 한도 명시적 종료 원칙). 회귀 테스트 2건(`test_n29b_log_event_critical_emits_stdout`, `test_n29a_notify_death_script_valid`). 전체 단위 테스트 통과. **배포 절차**: `git push` → `bash deploy/update.sh` → `sudo systemctl daemon-reload` (.service 수정 반영) → `sudo systemctl restart daily30k`. |
| **마지막 점검** | 2026-05-15 KST (N29 가시성·사망 알림 패치 완료, 배포 대기) |
| **점검 누적** | 6/6 |
| **남은 블로커** | 없음 — 단 N25 원인 await 자체는 실제 재발 stack trace 확보 전까지 미확정. 새 watchdog 이 snapshot 침묵을 재시작으로 전환하며, 재발 시 `py-spy dump --pid <PID>` 로 stack trace 확보 필수 |
| **테스트 상태** | 전체 통과 (`python test.py` 기본 실행으로 Phase 3/4 + bugfix + Phase 6/7 전부 커버) |
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

> **(없음)** — N29 KILL_SWITCH 가시성·사망 알림 패치 완료, 배포 대기 (2026-05-15).
>
> **다음 세션 Claude / 도울님 첫 액션**:
> 1. **봇 재시작 결정** — 5/13 13:09 KST testnet 가짜 폭락으로 KILL_SWITCH 후 34시간 침묵 중. mode=testnet 이라 실손실 없음. SSH `sudo systemctl restart daily30k` 로 즉시 재개 가능. **단 N29 배포가 같이 가야 같은 상황 재발 시 외부 알림 동작**
> 2. **N29 배포 절차**: `git push` → SSH 접속 → `cd ~/Daily_30k_bot && bash deploy/update.sh` → `sudo systemctl daemon-reload` (`.service` 수정 반영 필수) → `sudo systemctl restart daily30k` → `sudo systemctl status daily30k --no-pager`
> 3. 봇 부팅 후 `journalctl -u daily30k -f` 로 다음 4줄 확인:
>    - `[init_db] backend=supabase`
>    - `[Telegram] 허가 chat_id=<int>`
>    - `[INFO]` 이외(WARNING/CRITICAL) 이벤트 발생 시 새 `[severity] EVENT_TYPE: message ctx={...}` 형식으로 journal 출력 확인
>    - 부팅 텔레그램 `[MODE=TESTNET]` 도달
> 4. **N29-A 동작 검증** (선택): 한 번 `sudo systemctl stop daily30k` 후 텔레그램에 `🔴 daily30k 봇 종료 감지 ...` 도착 확인 → `start` 로 재가동
> 5. **장기 관찰** — `equity_snapshots` 30분 주기, `SUPERVISOR_RESTART is_watchdog=true` / `N25_TRADE_IDLE` 발생 여부, KILL_SWITCH 재발 시 journal 에 사건 라인 + 텔레그램 알림 모두 도달 확인
> 6. **정책 결정 보류** — testnet 가격 피드 -9% 괴리는 외부 환경 이슈. mainnet paper 모드로 전환 검토 필요 (도울님 의사결정)
> 7. Day 14 (~2026-05-25) B3 판단 (페이퍼 카운터 5/11 재시작 기준 유지)

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
| 2026-05-15 | [executor.py](executor.py), [deploy/notify_death.sh](deploy/notify_death.sh), [deploy/daily30k.service](deploy/daily30k.service), [test.py](test.py) | **N29 KILL_SWITCH 가시성·사망 알림 패치** — 5/13 13:09 KST testnet 가짜 폭락(mainnet $81,168 vs testnet $73,706, -9% 괴리)으로 손절매·KILL_SWITCH 연쇄 발동 → 봇 정상 종료(exit 0) → systemd `Restart=on-failure` 정책상 재시작 안 함 → 34시간 침묵 (도울님 5/14 23:36 /status 무응답으로 발견). Supabase 직접 진단(`/tmp/diagnose_kill_switch.py`): mode=testnet 확정, 손절 trade 1건 mainnet 차트와 -9% 차이로 testnet 호가창 이상 신호 확정. **N29-B (가시성)**: `_log_event()` 가 텔레그램+Supabase 만 호출하고 stdout 미출력 → KILL_SWITCH 시 journal 에 종료 라인만 4건, 사건 메시지 0건. 패치: `executor._log_event()` 가 severity ∈ {CRITICAL, ERROR, WARN, WARNING} 시 `print(f"[{severity}] {event_type}: {message}{ctx_str}", flush=True)` 동시 호출 (INFO 제외로 폭주 방지). **N29-A (사망 알림)**: 봇 사망 자체 외부 알림 부재 → 텔레그램 핸들러도 함께 죽어 봇 내부 알림 불가. 패치: `deploy/notify_death.sh` 신규 — `.env` 에서 TELEGRAM_TOKEN/CHAT_ID 추출 후 curl 텔레그램 sendMessage 호출, 알림 실패도 exit 0 (systemd 재시작 정책 보호). `daily30k.service` 에 `ExecStopPost=/home/ubuntu/Daily_30k_bot/deploy/notify_death.sh` 추가 — 정상 종료·실패·OOM 모두 캐치. `Restart=on-failure` 유지(손실 한도는 명시적 종료가 정답 원칙). 회귀 테스트 2건(`test_n29b_log_event_critical_emits_stdout` — CRITICAL/WARN 출력 + INFO 침묵 + context payload 포함 검증 / `test_n29a_notify_death_script_valid` — 파일 존재·실행권한·TELEGRAM_TOKEN/CHAT_ID/api.telegram.org/exit 0 패턴 + `ExecStopPost` 와 `notify_death.sh` 연결 정적 검증). 전체 단위 테스트 통과. **배포 절차**: `git push` → SSH → `bash deploy/update.sh` → `sudo systemctl daemon-reload` (.service 수정 반영 필수) → `sudo systemctl restart daily30k` |
| 2026-05-14 | [TODO.md](TODO.md), [WORKFLOW.md](WORKFLOW.md) | **장기 보완 백로그 기록** — 도울님 요청 "보완할 점들 나중에 반영하여 고칠 수 있도록 기록" 반영. TODO 에 2026-05-14 장기 보완 백로그 추가: S1(DB 기반 포지션·주문 resume 모드), S2(거래소 reconciliation 루프), S3(live 전환 preflight 자동화), R4(전략 기대값·리스크 리포트 강화), M1(침묵 알림 확장). C 트랙 백테스트 항목에도 수수료·슬리피지·지정가 미체결·급락장·코인 스위칭 비용 포함 조건 명시. 코드 변경 없음 |
| 2026-05-13 | [shared_state.py](shared_state.py), [main.py](main.py), [executor.py](executor.py), [test.py](test.py) | **N25 engine idle 재발 감시 체계 보강** — 5/5 73시간 정지 + 5/9 14시간+ 재발의 공통 신호였던 `equity_snapshot` 침묵을 watchdog 대상화. `BotState` 에 `executor_last_snapshot_at` / `executor_last_trade_at` / `n25_last_trade_idle_alert_at` 추가. `snapshot_equity()` 성공 시 snapshot progress 갱신, `_log_trade(..., state=...)` 성공 시 trade progress 갱신. `main._supervise()` 에 heartbeat 와 별도 `progress_timeout` / `progress_attr` 추가 — executor heartbeat 가 살아있어도 `executor_last_snapshot_at` 이 45분 이상 무갱신이면 task cancel → `TimeoutError` → 기존 `SUPERVISOR_RESTART` 경로로 재시작(`is_watchdog=true`). 활성 엔진 상태에서 24시간 무거래 시 `N25_TRADE_IDLE` WARNING 이벤트/텔레그램 경고(alert-only, 정상 저변동장 강제 청산 방지). 회귀 테스트 2건 추가(`test_n25_supervise_restarts_when_snapshot_stale`, `test_n25_snapshot_and_trade_mark_progress`). **배포 대기**: `bash deploy/update.sh` |
| 2026-05-13 | [executor.py](executor.py), [main.py](main.py), [config.py](config.py), [test.py](test.py) | **Codex 적대적 리뷰 결함 4건(F1·F2·F3·F4) 패치** — `/codex:adversarial-review` 가 needs-attention 평가로 실거래 자동매매 4결함 적발. **F1(CRITICAL)** 긴급 청산이 열린 sell 주문에 잠긴 잔고로 거절될 수 있음 — `executor.py` 5곳 청산 경로(check_stop_loss·emergency_sell 호출지점 5곳)를 새 헬퍼 `_safe_liquidate(reason)` 으로 통합: `cancel_all()` 선행 → 0.5초 대기 → `fetch_balance` 로 free 재동기화 → `amount_to_precision` 보정 후 시장가 매도 → 실패 시 상태 유지 + `LIQUIDATE_FAILED` CRITICAL 이벤트 + 텔레그램 알림 → 다음 루프에서 재시도. `regrid()` 도 동일 결함이라 같이 수정. **F2(HIGH)** `monitor_orders` 가 open_orders 누락을 무조건 체결로 간주 — 새 헬퍼 `_resolve_missing_order(side)` 에서 `fetch_order` 로 status/filled/average 재확인 후 분기: closed+filled>0 정상 체결, canceled+filled>0 부분만 반영, canceled+filled=0 PnL 무변경 + `ORDER_CANCELED` INFO, pending/open 은 보류. `_handle_buy_fill`/`_handle_sell_fill` 에 `actual_avg_price`·`actual_fill_qty` 옵셔널 인자 추가(기존 호출자 호환). **F3(HIGH)** `_limit_buy_with_retry` 가 타임아웃 시 부분 체결분 미반환 — cancel 직후 `fetch_order` 추가 호출, `filled > 0` 이면 `(avg, filled)` 반환·재시도 중단으로 그리드 미배치 또는 의도 초과 매수 차단. **F4(HIGH)** 텔레그램 명령 권한 검증 부재 — `config.py` 에 `TELEGRAM_CHAT_ID_INT` (int 변환) 추가, `main.py` 의 3개 CommandHandler 에 `filters.Chat(chat_id=TELEGRAM_CHAT_ID_INT)` 적용. 미설정 시 봇이 부팅 텔레그램에 CRITICAL 알림 후 `kill_event` 대기로 안전 멈춤. 부팅 시 `[Telegram] 허가 chat_id=...` 메시지 추가. 회귀 테스트 7건(F1×2 + F2×2 + F3×2 + F4×1) + MockExchange 서브클래스 3종(호출 순서 로그·잠긴 잔고 InsufficientBalance·부분 체결 응답 주입). 기존 `MockExchange.create_order` 가 미체결 주문도 `filled=amount` 로 채우던 결함도 정정(`filled=0`·`average=None`) → `test_b1_external_cancel_not_counted_as_fill` 회귀 안전. 전체 단위 테스트 통과 (Phase 3/4 + bugfix + Phase 6/7 + Codex 4건). 플랜: `~/.claude/plans/enumerated-beaming-galaxy.md`. **배포 대기**: `bash deploy/update.sh` |
| 2026-05-11 | [persistence.py](persistence.py), [test.py](test.py) | **N28 Supabase silent fallback 패치** — N27 commit `fafdf5b` 배포(5/11 17:51 KST) 직후 텔레그램 `[DEGRADED] Supabase 연결 실패 → SQLite fallback` 도착. 사유 `DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_1__" already exists` (asyncpg + pgbouncer Transaction Pool 모드 알려진 충돌). 5/9 배포는 우연히 통과했으나 5/11 배포에서 노출. `[persistence.py:192-194](persistence.py#L192-L194)` `asyncpg.create_pool` 호출에 `statement_cache_size=0` 추가 — server-side prepare 우회, asyncpg 가 매 쿼리 inline parameter 송신 (봇 쿼리 빈도 초당 1회 미만이라 성능 영향 무시). 회귀 테스트 1건(`test_n28_supabase_pool_disables_statement_cache`): 정적 검증 — `SupabaseBackend.init` 소스에 `statement_cache_size=0` 존재 확인 (실제 connection 통합 테스트는 CI 의존성으로 회피). 전체 단위 테스트 통과. **배포 대기**: `bash deploy/update.sh` |
| 2026-05-11 | [executor.py](executor.py), [test.py](test.py) | **N27 DAILY_STOP 봇 종료 결함 패치** — 5/10 20:08 KST 일일 목표 달성 → `state.kill_event.set()` + `break` → main 의 모든 _supervise 종료 → main() 정상 exit(0) → systemd `Restart=on-failure` 정책상 재시작 안 함 → 봇 영구 종료 → 5/11 자정 자동 재개 실패 → 텔레그램·Supabase 둘 다 24시간+ 침묵 (도울님 발견). N26 패치(5/9)에서 spam 방지를 위해 추가된 `kill_event.set()` 이 의도치 않게 봇 전체 종료를 유발. **자정 리셋 분기는 메인 루프 안에 있어 break 후 영원히 도달 불가** 인 게 결정타. 패치: DAILY_STOP 분기에서 `kill_event.set()` 제거 + 자정까지 sleep loop(`asyncio.wait_for(state.kill_event.wait(), timeout=30)` 으로 외부 종료 즉시 응답 + 30초마다 자정 체크) + `state.executor_heartbeat = time.time()` 갱신(watchdog 회피) + 자정 도달 시 `state.reset_daily()` + `[리셋] {today} 일일 집계 초기화 — 매매 재개` 텔레그램 + `DAILY_RESUME` 이벤트 + `engine = None` 후 `continue`. KILL_SWITCH 분기는 그대로(손실 한도는 명시적 종료가 정답). 회귀 테스트 1건(`test_n27_daily_stop_does_not_terminate_supervisor`): spy_log_event 로 DAILY_STOP 기록 직후 `state.kill_event.is_set() is False` 동적 단언 + run_executor 소스 정적 검증(`reset_daily`/`DAILY_RESUME` 존재 + `kill_event.set` 부재). 전체 단위 테스트 통과. **배포 대기**: 도울님 SSH 1차 복구 후 `git push` + `bash deploy/update.sh` |
| 2026-05-09 | [executor.py](executor.py), [test.py](test.py) | **N26 spam 결함 패치** — 5/8 18:48 재시작 5시간 만에 결함 재발 (5/9 00:00:28~00:02:34 KST DAILY_STOP 4초 간격 3,562건 spam, 그 후 14시간+ 매매 정지). 도울님 "수파베이스 한 번 더 확인" 요청 → `/tmp/db_check.py` 실행 → 마지막 trade 5/9 00:02:37, equity_snapshot 5/8 19:21 끊김, EXECUTOR_START 1건+SUPERVISOR_RESTART 0건+KILL_SWITCH 0건+DAILY_STOP 3,562건 확정 → executor.py:734-745 (DAILY_STOP) + 721-732 (KILL_SWITCH) 분기에서 `engine.emergency_sell` ccxt 예외가 outer `except Exception as e:` 에 잡혀 `state.kill_event.set()` / `break` 둘 다 도달 못 한 결함 100% 확정. 패치: 두 분기 모두 `state.kill_event.set()` 을 emergency_sell **앞**으로 옮기고 emergency_sell 자체를 `try/except` 로 감싸 예외 swallow + `notify_error("Executor.emergency_sell on KILL_SWITCH/DAILY_STOP", ...)` 로 가시화 → break 도달 보장. 회귀 테스트 2건 (`_N26FailingEngineBase` 공통 모의 엔진 + `_n26_install_mocks` 공통 셋업 헬퍼 + `test_n26_daily_stop_no_spam_when_emergency_sell_raises` / `test_n26_kill_switch_no_spam_when_emergency_sell_raises`): setup_grid 호출 시 daily_pnl 강제 변경 → iter 2 진입 시 engine 살아있는 상태로 emergency_sell raise → 5초 안전망 + spam 결함이면 N건/패치 후 1건 검증. 전체 단위 테스트 통과. **배포 대기**: `bash deploy/update.sh` 후 활성화 |
| 2026-05-08 | [WORKFLOW.md](WORKFLOW.md) | **73시간 매매 정지 진단 + 봇 재시작 + N25/N26 백로그 등록**. 도울님 "수파베이스 한 번 더 확인" 요청 → `/tmp/db_check.py` 로 trades 누적 231건 5/5 16:48 KST 정지 확인 → SSH journal 진단으로 봇 프로세스(PID 37768)·screener·equity_snapshot 모두 정상이지만 매매만 정지 확정. KILL_SWITCH·DAILY_STOP 흔적 0건이라 메인 루프 break 안 함. `sudo systemctl restart daily30k` (PID 37768→51204) → `[init_db] backend=supabase` 첫 줄 + EXECUTOR_START 이벤트 + recover_state 가 testnet 200+ 자산 huge inventory 청산. **N25 (engine idle 결함, 재발 감시 필요), N26 (DAILY_STOP 4초 spam 결함)** 백로그 등록. 페이퍼 누적 카운터 0일부터 재시작, B3 판단일 5/22+ 검토 필요. 코드 변경 없음 |
| 2026-05-04 | [main.py](main.py), [test.py](test.py) | **N22 가시성 패치** — 5/4 02:43 KST 부팅 시 Supabase 일시 끊김 → SQLite fallback 발동했으나 [DEGRADED] 텔레그램 알림이 일시 NetworkError 로 누락 → 16시간 후 도울님 "DB에 데이터 잘 쌓이고 있어?" 질문으로 발견. 데이터 손실 0건이지만 **fallback 발생 자체가 16시간 무인지** 가 진짜 위험. 처방: `init_db()` 결과를 무조건 stdout 으로 print (`[init_db] backend=...`), fallback 시 stderr 로 사유 (`[init_db] FALLBACK reason=...`). 텔레그램 send 는 외부 의존 (네트워크/dedup) 이라 신뢰성 한계, journal 은 systemd 가 보장 (N12 패치로 이미 timestamp + auto-rotate 확보). main.py 에 `import sys` 추가 + 2줄 print 삽입. 회귀 테스트 1건 (`test_n22_init_db_result_visible_in_journal`: 정적 검사로 print 패턴 검증). 전체 테스트 통과 |
| 2026-05-04 | [deploy/daily30k.service](deploy/daily30k.service), [deploy/setup.sh](deploy/setup.sh), [deploy/update.sh](deploy/update.sh), [deploy/advise.sh](deploy/advise.sh), [shared_state.py](shared_state.py), [main.py](main.py), [executor.py](executor.py), [test.py](test.py) | **N12+N19+N20 안전 패치 풀 패키지** — 4/28~5/4 6일 `run_executor` 단독 hang 사건(예외 없음 → `_supervise` 못 잡음 → SUPERVISOR_RESTART 0건) 재발 방지. **N12**: systemd unit `StandardOutput/Error=journal` + `SyslogIdentifier=daily30k` 전환 (timestamp 자동 부여 + auto-rotate + `journalctl --since` 시간쿼리). 사후 디버깅 가능성 확보가 가장 큰 동기. setup.sh/update.sh/advise.sh 로그 명령 `tail -f logs/*.log` → `journalctl -u daily30k -f` 갱신. **N19**: `BotState.executor_heartbeat` 추가 + `_supervise(watchdog_timeout, heartbeat_attr)` 매개변수 추가 — executor 만 600초 무갱신 시 task 강제 cancel → TimeoutError 변환 → 기존 재시작 경로 재사용 + SUPERVISOR_RESTART 페이로드 `is_watchdog: true`. heartbeat 갱신 위치 2곳: executor 메인 루프 매 iteration 첫 줄, recover_state 매 자산 처리 시작점(testnet 다중 청산 throttle 시간 보호). **N20**: `_retry_api(timeout=60.0)` 매개변수 추가 — 각 시도를 `asyncio.wait_for` 로 감싸 ccxt 외부 await(fetch_balance/fetch_ticker/fetch_ohlcv/fetch_open_orders/cancel_order/create_order)이 영원히 hang 되지 않도록. 타임아웃은 일반 예외와 동일하게 다음 시도로 넘어감. 회귀 테스트 5건 (`test_n12_service_uses_journald`, `test_n19_supervise_cancels_hung_executor`, `test_n19_supervise_normal_executor_no_false_trigger`, `test_n20_retry_api_times_out_on_hung_call`, `test_n20_retry_api_normal_call_unaffected`). 전체 테스트 통과 |
| 2026-04-28 | [deploy/schema.sql](deploy/schema.sql) | **OPS2**: Supabase 대시보드 KST 조회 편의 — `trades_kst` / `equity_snapshots_kst` / `bot_events_kst` 3개 View 추가. `created_at TIMESTAMPTZ` 가 Postgres 표준대로 UTC 저장되어 대시보드에 `+00` offset 으로 표시되던 것을 `(created_at AT TIME ZONE 'Asia/Seoul')::timestamp` 변환 View 로 KST 표시. 멱등 `CREATE OR REPLACE VIEW`. 봇 코드/base 테이블 영향 없음 |
| 2026-04-28 | [config.py](config.py), [deploy/daily30k.service](deploy/daily30k.service), [screener.py](screener.py) | **D1**: 페이퍼 운영 48시간째 trades 14건 정체(전부 recover SELL) → 진단 결과 `testnet 마켓 거래량이 mainnet 대비 1/100` 으로 `MIN_VOLUME_USD=$100M` 임계값을 어떤 코인도 못 넘김(testnet BTC/USDT 24h $82M). 본 패치: `MIN_VOLUME_USD = 10_000_000 if MODE == "testnet" else 100_000_000` 자동 분기. 부수: systemd unit `Environment=PYTHONUNBUFFERED=1` 영구 반영(서버 진단 중 발견된 logger buffer 문제). 진단용 DIAG1 print(_scan/_pre_filter 단계별 컷 분포)는 추가→revert 사이클로 정리. 결과: BTC/USDT 타겟 선정 정상, 4분 만에 그리드 5단 BUY 체결, trades 14→120건(BUY 38/SELL 82, 누적 PnL -1,673원 testnet). 신규 발견 이슈 4건은 N15~N18 백로그 등록 |
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

> **2026-05-14 기록 갱신** — N27/N25 패치 모두 코드 작성 완료, 배포 및 24~48시간 관찰 대기. 페이퍼 누적 카운터는 5/11 재시작 기준 유지, B3 일정 5/25+ 연기. 장기 보완 후보(S1/S2/S3/R4/M1)는 TODO "장기 보완 백로그" 에 기록.

---

### 🎯 현 우선순위 (N25/N27 배포 → 자정 재개·snapshot 검증 → R1 → B3)

| 시점 | 액션 | 비고 |
|------|------|------|
| **2026-05-11 (지금 즉시)** | 👤 **SSH 1차 복구** | `ssh ubuntu@3.36.26.177 'sudo systemctl restart daily30k && journalctl -u daily30k -n 20 --no-pager'` → 텔레그램 `[MODE=TESTNET]` 부팅 메시지 재수신 확인. (N27 패치 배포 전이라도 1일 매매 가능, 다음 DAILY_STOP 까진 정상 동작) |
| **2026-05-11 (지금)** | 👤 **N27 패치 배포** | `git push` + `bash deploy/update.sh` (Lightsail 서버) + journal 로 fast forward + PID 교체 + `[init_db] backend=supabase` + 텔레그램 부팅 메시지 확인. 페이퍼 카운터 또 0일부터 재시작 |
| **05/11~05/18 (Day 0~7)** | 👤 **손 떼고 페이퍼 누적 + 자정 재개/snapshot 검증** | 매일 `/status` 또는 Supabase `trades_kst` 누적 확인. **DAILY_STOP 발동일 자정 직후 `[리셋] ... 매매 재개` 텔레그램 + `bot_events` 테이블 `DAILY_RESUME` 도달 확인** (N27 핵심 검증). N25 감시: `equity_snapshots` 30분 주기 유지, snapshot 침묵 시 45분 내 `SUPERVISOR_RESTART is_watchdog=true` 발생 여부 확인 |
| **05/18~05/21 (Day 7~10)** | 🤖 **R1 진행 권장** | `/status` 응답에 누적 손익 추가. `persistence.get_total_pnl(mode)` 헬퍼 + 회귀 테스트 1건 |
| **05/21~05/24 (선택)** | 🤖 R3 (분석 대시보드) | 승률·MDD·샤프비. R1 만으로도 B3 가능하나 있으면 강력 |
| **2026-05-25 (Day 14)** | 👤 **B3 판단** | 누적 손익 검토 → MODE=live 전환 여부 결정 → 실거래 HMAC 키 발급(IP 화이트리스트, 출금권한 OFF) → `.env` `MODE=live` 전환. N25/N26/N27 재발 안 했어야 가능. 가능하면 S3 live preflight 자동화 후 전환 |

> 💡 **보류 항목 (페이퍼 데이터 정확성에 영향 없음 — 새 세션에서도 그대로 보류 권장)**
> - **N15** (Med): BUY 행 pnl 음수 기록 → 분석 시 `WHERE side='SELL'` 만 합산하면 영향 0
> - **N16** (Low): WBTC LOT_SIZE 청산 실패 → 매 재시작 시 텔레그램 [오류] 1건, 매매 무관
> - **N17** (Low): fetch_open_orders symbol 미지정 ccxt 경고 → 동작 정상
> - **N18** (Med): 시장 악화 자동 전환 → 30분 후 200MA 기반 자동 회복, 영구 차단 아님

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
- [x] ~~**N12** (2026-05-04 완료): `deploy/daily30k.service` `StandardOutput/Error=journal` + `SyslogIdentifier=daily30k` 전환. setup/update/advise 로그 명령 `journalctl -u daily30k -f` 로 갱신. 회귀 테스트 1건~~
- [ ] N13: [executor.py:282-299](executor.py#L282-L299) `monitor_orders` 체결 핸들러 개별 try-except (단일 주문 실패 격리)
- [ ] N14: [main.py:125-141](main.py#L125-L141) `_supervise` `max_restarts` 초과 시 `kill_event.set()` 검증 테스트
- [ ] B7: 캔들 수집 실패 감지 — 무음 처리되는 API 오류 누적 시 실패율 임계치 넘으면 알림 (screener.py)

**🔴 안전 패치 (2026-05-04 hang 사건 후 신설, 모두 완료)**
- [x] ~~**N19** (2026-05-04 완료): `BotState.executor_heartbeat` + `_supervise(watchdog_timeout=600, heartbeat_attr)` — executor 단독 hang 감지 및 강제 재시작. 회귀 테스트 2건 (hang/normal)~~
- [x] ~~**N20** (2026-05-04 완료): `_retry_api(timeout=60.0)` 매개변수 추가 — 각 시도를 `asyncio.wait_for` 로 감싸 ccxt 외부 await hang 방지. 회귀 테스트 2건 (hang/normal)~~
- [x] ~~**N22** (2026-05-04 완료): `main.py` 의 `init_db()` 결과를 무조건 stdout `print("[init_db] backend=...")` + fallback 시 stderr `print("[init_db] FALLBACK reason=...")` 으로 journal 가시화. 5/4 02:43 KST Supabase fallback 사건이 [DEGRADED] 텔레그램 누락으로 16시간 무인지된 사건의 처방. 회귀 테스트 1건 (정적 검사). 다음 세션에서 배포 필요~~

**🟡 후속 개선 (5/4 사건 추가 백로그)**
- [ ] N23 (Med): `init_db()` fallback 발생 시 30분마다 Supabase 재연결 시도 (싱글톤 자동 복구). 5/4 사건처럼 16시간 SQLite 갇혀있는 상황 자동 회복용. R1 진행 시점에 같이 작성
- [ ] N24 (Med): SQLite → Supabase 백필 스크립트 (`reports/backfill_sqlite.py`) — 5/4 02:43~19:26 SQLite 119건을 Supabase 로 옮겨 통합 분석. R1 분석 직전에 1회 사용

**🔴 신규 결함 (5/8~5/9 사건)**
- [x] ~~**N25** (2026-05-13 완료): **engine idle 재발 감시 체계 보강** — `equity_snapshot` 30분 타이머 침묵을 supervisor progress watchdog 으로 승격. `executor_last_snapshot_at` 45분 무갱신 시 executor task cancel → `SUPERVISOR_RESTART is_watchdog=true`. 24시간 무거래 활성 엔진은 `N25_TRADE_IDLE` WARNING 이벤트/텔레그램 경고(alert-only). 실제 원인 await 는 재발 시 `py-spy dump --pid <PID>` 로 확보~~
- [x] ~~**N26** (2026-05-09 완료): **DAILY_STOP / KILL_SWITCH spam 결함 패치** — 5/5 03:35~08:59 KST 4,679건 + 5/9 00:00:28~00:02:34 KST 3,562건 두 차례 발생. 원인: [executor.py:734-745](executor.py#L734-L745) DAILY_STOP + [executor.py:721-732](executor.py#L721-L732) KILL_SWITCH 분기에서 `engine.emergency_sell` 가 ccxt 예외 → outer `except Exception as e:` (line 805) 가 잡음 → `state.kill_event.set()` / `break` 둘 다 도달 못 함. 패치: 두 분기 모두 `kill_event.set()` 을 emergency_sell 앞으로 이동 + emergency_sell 자체를 try/except 로 감싸 swallow + `notify_error` 로 가시화. 회귀 테스트 2건 (`test_n26_daily_stop_no_spam_when_emergency_sell_raises`, `test_n26_kill_switch_no_spam_when_emergency_sell_raises`). 전체 단위 테스트 통과~~

---

### 🤖 Claude 트랙 (R 트랙 — 리포팅·모니터링) `B3 판단 지원 · 2026-04-25 추가`

> testnet 페이퍼 가동 이후 도출. 현재 `/status` 는 메모리 `daily_pnl` 만 보여주고 누적 손익·추세·리스크 지표는 Supabase SQL 수동 조회만 가능. B3 전환 판단일 (~2026-05-09 전후) 전에 적어도 **R1** 은 필수.

- [ ] R1: `/status` 응답에 **누적 손익** 포함 — `notify_status()` 에서 Supabase `trades` `SUM(pnl)` 조회 추가. `persistence.get_total_pnl(mode)` 헬퍼 신설 + 회귀 테스트 1건
- [ ] R2: 일간/주간 손익 리포트 **자동 텔레그램 발송** — `run_reporter()` 컴포넌트 신설 (asyncio.gather 4번째 태스크). 자정 KST + 매주 월 오전 9시 발송. 손익·승률·MDD·평균 손익 포함
- [ ] R3: B3 판단용 **분석 대시보드** — `reports/summary.py` CLI (`python -m reports.summary --mode testnet --period 7d`) 승률·평균 손익·MDD·샤프비·일별 히트맵. `equity_snapshots` + `trades` 조인 기반. R2 출력부로 재사용

---

### 🤖 Claude 트랙 (S/M/R4 — 장기 보완 백로그) `2026-05-14 사용자 요청 기록`

> 목적: 지금 당장 구현하지 않더라도 live 전환 전후에 하나씩 고칠 수 있도록 설계 보완 포인트를 보존. 상세는 [TODO.md](TODO.md) "장기 보완 백로그".

- [ ] S1: DB 기반 포지션·주문 상태 복구 모드 — 기존 전량정리 외 "resume" 모드 설계
- [ ] S2: 거래소 reconciliation 루프 — 내부 GridEngine 상태 vs Binance 실제 잔고/주문/체결 대조
- [ ] S3: live 전환 preflight 체크리스트 자동화 — 키/권한/IP/텔레그램/Supabase/test 상태 가드
- [ ] R4: 전략 기대값·리스크 리포트 강화 — 월간 기대값, MDD, 연속 손실일, 수수료/스위칭 비용
- [ ] M1: 침묵 알림 확장 — screener/Telegram/Supabase/status/거래 부재 통합 health monitor

---

### 🤖 Claude 트랙 (C 트랙 — 백테스트 엔진) `N 트랙 Top 3 후 진행`

A 와 독립. 로컬 개발 환경에서 진행. **C1 전 반드시 N3+N4 → N1 → N8 해소 (감사 권고).** 2026-05-14 보완 기록: 수수료·슬리피지·지정가 미체결·급락장·코인 스위칭 비용을 시뮬레이션에 반드시 포함.
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
- [x] **A4** (2026-04-25 완료): AWS Lightsail $7 (서울, IP `3.36.26.177`, Ubuntu 22.04) 생성 + `bash deploy/setup.sh` 통과 + `.env` 작성 + `sudo systemctl start daily30k`

#### 🟡 A 완료 후 진행

**B 트랙 — 페이퍼 트레이딩 실연결**

- [x] **B1** (2026-04-25 완료): https://testnet.binance.vision 가입 + HMAC 키(`CoinTradingBot`) 발급 + 서버 `.env` 에 `MODE=testnet` + 키 기재
- [x] **B2** (2026-04-25 완료): `sudo systemctl restart daily30k` → 텔레그램 `[MODE=TESTNET]` 부팅 + recover_state 13건 청산 + 매매 사이클 진입 확인 (D1 패치 후 정상)

#### 🔴 1~2주 페이퍼 누적 후 (~2026-05-09)

- [ ] **B3** (사용자, ~Day 14): 누적 손익 리포트(R1) 리뷰 → `MODE=live` 전환 여부 판단 → 실거래 바이낸스 HMAC 키 발급 (IP 화이트리스트·출금권한 OFF) → `.env` `MODE=live` + `BINANCE_API_KEY`/`BINANCE_SECRET_KEY` 기재 → `sudo systemctl restart daily30k`

---

## 완료된 작업

<details>
<summary>전체 이력 (클릭하여 펼치기)</summary>

| 날짜 | ID | 내용 |
|------|----|------|
| 2026-05-13 | N25 | **engine idle 재발 감시 체계 보강** — 5/5 73시간 정지 + 5/9 14시간+ 재발의 공통 신호가 `equity_snapshot` 30분 타이머 침묵이었으므로 heartbeat 와 별도 progress watchdog 추가. `BotState` 에 `executor_last_snapshot_at` / `executor_last_trade_at` / `n25_last_trade_idle_alert_at` 추가. `snapshot_equity()` 성공 시 snapshot progress 갱신, `_log_trade(..., state=...)` 성공 시 trade progress 갱신. `main._supervise()` 에 `progress_timeout` / `progress_attr` 추가 — executor heartbeat 가 살아있어도 `executor_last_snapshot_at` 이 45분 이상 무갱신이면 task cancel → `TimeoutError` → 기존 `SUPERVISOR_RESTART` 경로로 재시작(`is_watchdog=true`). `run_executor()` 부팅 시 progress 초기화, 활성 엔진 상태에서 24시간 무거래면 `N25_TRADE_IDLE` WARNING 이벤트/텔레그램 경고(alert-only, 정상 저변동장 강제 청산 방지). 회귀 테스트 2건 추가(`test_n25_supervise_restarts_when_snapshot_stale`, `test_n25_snapshot_and_trade_mark_progress`). 배포 후 Supabase `equity_snapshots` 30분 주기와 `bot_events` 의 `SUPERVISOR_RESTART`/`N25_TRADE_IDLE` 관찰 필요 |
| 2026-05-13 | B3-ADV-01 | **Codex 적대적 리뷰 결함 4건 패치 (F1·F2·F3·F4)** — `/codex:adversarial-review` 의 needs-attention 평가가 실거래 자동매매에 치명적인 결함 4건 적발. F1(CRITICAL) `check_stop_loss`/`emergency_sell` 가 시장가 매도 선행 → `cancel_all` 후행 순서라 Binance spot 의 열린 limit sell 잠긴 잔고로 시장가 매도 거절될 수 있음. 호출지점 5곳(손절·일일손실·수익중단·코인스위칭·봇종료) 모두 동일 결함. F2(HIGH) `monitor_orders` 가 `fetch_open_orders` 누락 ID 를 `fetch_order` 재확인 없이 무조건 `_handle_*_fill` 호출 → 외부 취소·expired·rejected·부분 체결 후 취소가 전부 "완전 체결" 로 처리되어 `total_qty`/`avg_price`/PnL 오염. F3(HIGH) `_limit_buy_with_retry` 가 타임아웃 시 `cancel_order` 만 호출하고 `filled` 미확인 → 부분 체결분이 (0.0, 0.0) 으로 반환되어 그리드 미배치 또는 재시도로 의도 초과 매수. F4(HIGH) `run_telegram_bot` 의 `/status`·`/stop`·`/seed` 핸들러에 `update.effective_chat.id` 검증 부재 → 봇 사용자명·토큰 노출 시 제3자가 즉시 봇 중단·SEED 변경 가능. **패치**: `_safe_liquidate(reason) -> bool` 헬퍼로 청산 5곳 통합 (`cancel_all` 선행 → 0.5초 대기 → `fetch_balance.free` 재동기화 → precision 후 시장가 매도 → 실패 시 상태 유지 + `LIQUIDATE_FAILED` CRITICAL + 텔레그램 알림 + 다음 루프 재시도, regrid 동일 결함 같이 정리). `_resolve_missing_order(side)` 헬퍼로 `fetch_order` 분기 (closed+filled>0 정상 / canceled+filled>0 부분반영 + `ORDER_PARTIAL_CANCEL` WARNING / canceled+filled=0 무변경 + `ORDER_CANCELED` INFO / pending 보류). `_handle_buy_fill`/`_handle_sell_fill` 에 `actual_avg_price`·`actual_fill_qty` 옵셔널 인자 추가 (기존 호출자 호환). `_limit_buy_with_retry` 에 cancel 직후 `fetch_order` 재조회 추가 (filled>0 이면 그 값 반환·재시도 중단). `config.TELEGRAM_CHAT_ID_INT` (int 변환, None 가드 포함) + `main.py` `filters.Chat(chat_id=TELEGRAM_CHAT_ID_INT)` 3개 CommandHandler 적용 + 미설정 시 봇 안전 멈춤. 회귀 테스트 7건: `test_codex_f1_emergency_sell_cancels_first` (호출 순서 로그 검증), `test_codex_f1_emergency_sell_uses_free_balance` (잠긴 잔고 시뮬레이션 + InsufficientBalance 예외), `test_codex_f2_open_order_missing_fetches_status` (canceled 시 PnL 무변경), `test_codex_f2_partial_fill_uses_actual_filled` (actual_fill_qty=0.3 vs info.qty=1.0 분리 검증), `test_codex_f3_limit_buy_returns_partial_fill` (cancel 직후 filled=0.6 회수), `test_codex_f3_limit_buy_full_zero_retries` (filled=0 회귀 방지), `test_codex_f4_unauthorized_chat_rejected` (`filters.Chat.chat_ids` 검증 + `TELEGRAM_CHAT_ID_INT` 변환 검증). MockExchange 서브클래스 3종(`MockExchangeOrderLog`·`MockExchangeWithLockedBalance`·`MockExchangePartialFill`) + 기존 `MockExchange.create_order` 의 미체결 `filled=amount` 오류 정정(`filled=0`·`average=None`). 전체 단위 테스트 통과. 플랜 `~/.claude/plans/enumerated-beaming-galaxy.md` |
| 2026-05-09 | N26 | **DAILY_STOP / KILL_SWITCH spam 결함 패치** — 5/5 4,679건 + 5/9 3,562건 두 차례 발생한 4초 간격 spam 결함 처방. 원인 100% 확정: [executor.py:734-745](executor.py#L734-L745) DAILY_STOP 분기 + [executor.py:721-732](executor.py#L721-L732) KILL_SWITCH 분기가 모두 `if engine: await engine.emergency_sell(reason)` 호출 후 `state.kill_event.set()` + `break` 순서. emergency_sell ccxt 예외(401/timeout 등)가 outer `except Exception as e:` (line 805) 에 잡히면 `kill_event.set()` 와 `break` 둘 다 절대 도달 못 함 → `asyncio.sleep(1)` → 다음 iteration → should_stop_profit / 손실한도 여전히 트리거 → 무한 spam (4초 = 1초 sleep + emergency_sell ccxt timeout 약 3초). 결함 코드는 set/break 가 emergency_sell **이후** 줄에 있어 emergency_sell 가 무사 통과해야만 작동. 5/9 사건의 경우 5/8 19:21 이후 equity_snapshot 끊겨 엔진/시장상태 stale 인 채로 자정 reset_daily → 매매 → daily_pnl 16,611원 (DAILY_MIN_PROFIT 충족) + is_market_healthy=False → should_stop_profit=True → emergency_sell 실패 → spam. 패치: 두 분기 모두 (1) `state.kill_event.set()` 을 emergency_sell **보다 먼저** 호출하여 set 자체는 무조건 보장, (2) emergency_sell 호출을 `try/except Exception as _emsell_err: await notify_error("Executor.emergency_sell on KILL_SWITCH/DAILY_STOP", _emsell_err)` 로 감싸 예외 swallow + 가시화, (3) break 가 try/except 밖에서 무조건 실행되도록 ordering. 회귀 테스트 2건 (`_N26FailingEngineBase` 공통 모의 엔진 + `_n26_install_mocks` 공통 셋업 헬퍼 도입): `test_n26_daily_stop_no_spam_when_emergency_sell_raises` 는 setup_grid 시 `daily_pnl=DAILY_TARGET+100` 강제 설정 → iter 2 line 735 트리거, `test_n26_kill_switch_no_spam_when_emergency_sell_raises` 는 `-DAILY_LOSS_LIMIT-100` 강제 설정 → iter 2 line 721 트리거. 5초 force_stop 안전망 + 결함이면 spam N건/패치 후 1건 검증. 전체 단위 테스트 통과 |
| 2026-05-04 | N22 | **init_db 결과 journal 가시화** — 5/4 02:43 KST Supabase 일시 끊김 → SQLite fallback 발동했으나 [DEGRADED] 텔레그램 알림이 일시 NetworkError 로 누락 → 16시간 후에야 도울님 "DB에 데이터 잘 쌓이고 있어?" 질문으로 발견된 사건 처방. 데이터 손실 0건 (5/4 02:43~19:26 분 119건은 서버 SQLite 에 안전, 19:26 사용자 재시작 후 Supabase 정상 적재). 진단 시 결정타였던 정보: (1) `lsof -p $PID | grep trades.db` 의 fd 15u → SqliteBackend 사용 확정, (2) `lsof | grep "->.*:6543"` 의 ESTABLISHED → Supabase Pooler 정상 연결 확정, (3) `journalctl --since` UTC 표기 vs Supabase view KST 표기 시간대 혼동이 조기 hang 오진의 원인이었음. 처방: [main.py](main.py) `import sys` + `init_db()` 결과 후 `print(f"[init_db] backend={backend_used}", flush=True)` + fallback 시 `print(f"[init_db] FALLBACK reason={reason}", file=sys.stderr, flush=True)`. 텔레그램은 외부 의존 (네트워크/dedup) 으로 신뢰성 한계, journal 은 systemd 보장 + N12 패치로 이미 timestamp/auto-rotate 확보. 회귀 테스트 1건 (`test_n22_init_db_result_visible_in_journal`: 정적 검사 — print 패턴 + sys import + stderr 분리 검증). 전체 테스트 통과 |
| 2026-05-04 | N12+N19+N20 | **안전 패치 풀 패키지** — 4/28 02:25 KST 이후 6일간 `run_executor` 단독 hang 사건(예외 없음 → `_supervise` 못 잡음) 재발 방지. 사용자 합의 흐름 변경: B3 판단일 5/9 → 5/18+ 연기, 페이퍼 카운트 0일부터 재개. **N12** (로그 가시성): `deploy/daily30k.service` `StandardOutput/Error=journal` + `SyslogIdentifier=daily30k` 전환. systemd-journald 자동 timestamp(microsecond UTC) + auto-rotate(SystemMaxUse 기본 10% disk) + `journalctl --since "Apr 28 02:00"` 시간 쿼리 + `-p err` 에러 필터 가능. setup.sh/update.sh/advise.sh 로그 명령 `tail -f logs/*.log` → `journalctl -u daily30k -f` 갱신. 사후 디버깅 거의 불가능했던 게 이번 사건의 가장 큰 교훈. **N19** (watchdog): `BotState.executor_heartbeat: float = 0.0` 추가 + `_supervise(watchdog_timeout=600.0, heartbeat_attr="executor_heartbeat")` 매개변수 추가. 폴링 주기 `min(60, watchdog_timeout/4)` 로 `asyncio.wait_for(asyncio.shield(task), poll_interval)` 반복 → 600초 무갱신 시 `task.cancel()` + `TimeoutError` 발생 → 기존 except 블록이 잡고 SUPERVISOR_RESTART 페이로드에 `is_watchdog: true` 기록. heartbeat 갱신 위치 2곳: executor 메인 while 루프 첫 줄(매 1초마다 갱신), `recover_state` 매 자산 처리 시작점(testnet 다중 청산 throttle 0.3s × N 동안에도 watchdog 가 hang 으로 오인하지 않도록). recover_state 시그니처 `(exchange, state=None)` 으로 옵셔널 추가, 기존 테스트 호환 유지. **N20** (await timeout): `_retry_api(timeout=60.0)` 매개변수 추가, 각 시도를 `asyncio.wait_for(fn(*args, **kwargs), timeout=timeout)` 으로 감쌈. ccxt 호출 6종(fetch_balance/fetch_ticker/fetch_ohlcv/fetch_open_orders/cancel_order/create_order) 단일 진입점이라 파급 최소. 타임아웃은 일반 예외와 동일하게 다음 시도로 넘어감(지수 백오프 1→2→4초), 최종 시도까지 실패 시 raise. 회귀 테스트 5건: `test_n12_service_uses_journald` (StandardOutput=journal+SyslogIdentifier+append: 잔재 검사), `test_n19_supervise_cancels_hung_executor` (heartbeat 무갱신 → watchdog cancel → 재시작 1회 + is_watchdog 페이로드), `test_n19_supervise_normal_executor_no_false_trigger` (정상 heartbeat → 재시작 0건), `test_n20_retry_api_times_out_on_hung_call` (max_retries=2 모두 timeout → TimeoutError raise), `test_n20_retry_api_normal_call_unaffected` (정상 호출 결과 반환). 전체 테스트 통과 |
| 2026-04-28 | OPS2 | **Supabase KST View 3개 추가** — 대시보드 `created_at` 컬럼이 UTC `+00` 으로 표시되어 한국 시간 환산 불편 해소. [deploy/schema.sql](deploy/schema.sql) 끝에 `trades_kst` / `equity_snapshots_kst` / `bot_events_kst` 3개 `CREATE OR REPLACE VIEW` 추가, 각 View 가 원본 컬럼 그대로 노출하되 `(created_at AT TIME ZONE 'Asia/Seoul')::timestamp` 변환으로 KST timezone-naive 표시. 봇 base 테이블/persistence/test 영향 없음. 사용자 액션: Supabase SQL Editor 에서 신규 View 부분만 실행(멱등). 봇 재시작 불필요 |
| 2026-04-28 | D1 | **페이퍼 매매 정상화** — testnet 가동 48시간째 trades 14건 정체 원인 진단 + 본 패치 + 정리. (1) **진단(DIAG1)**: `screener._scan()`/`_pre_filter()` 에 단계별 통과 카운터 + 거래량/ATR Top 샘플 print 추가 → 1사이클(15분) 만에 "USDT 페어 432개 전부 low_volume 컷, testnet 1위 BTC/USDT $82M < MIN_VOLUME_USD $100M" 확정. (2) **부수**: 서버 systemd unit `Environment=PYTHONUNBUFFERED=1` 누락으로 `print()` 가 buffer 에 갇혀 logs/daily30k.out.log 0줄. 서버 즉시 적용 + repo [deploy/daily30k.service](deploy/daily30k.service) 영구 반영. (3) **본 패치**: [config.py](config.py) `MIN_VOLUME_USD = 10_000_000 if MODE == "testnet" else 100_000_000` (testnet BTC/ETH/DOGE/SOL 4개 메이저만 통과, live 진입 시 자동 복원). (4) **정리**: DIAG1 print revert. 결과 검증: 봇이 BTC/USDT 타겟 선정 → 4분 만에 5단 그리드 BUY 전부 체결 → SELL 트리거 작동, trades 14→120건(BUY 38/SELL 82), PnL -1,673원(testnet, 정상 변동). (5) **신규 백로그**: N15(BUY 행 pnl 음수 기록 결함) / N16(WBTC LOT_SIZE 청산 실패) / N17(fetch_open_orders 경고) / N18(testnet 작은 손실로 시장 악화 자동 전환 → 회복 조건 부재) |
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
