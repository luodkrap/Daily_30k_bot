# WORKFLOW — Daily 30K Bot

> **세션 인수인계 문서.** 새 세션 시작 → 이 파일만 읽으면 10초 내 상태 파악 가능.  
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

---

## 🔲 빠른 상태 (Quick Status)

| 항목 | 값 |
|------|----|
| **현재 Phase** | Phase 6 진행 중 — 페이퍼 트레이딩(Testnet) 인프라 구축 완료, 실연결 검증 단계 |
| **마지막 점검** | 2026-04-17 (project-auditor 전체 감사) |
| **점검 누적** | 2/3 |
| **남은 블로커** | 없음 |
| **테스트 상태** | 전체 통과 (2026-04-21 Phase 6 MODE/SQLite 작업 후 확인) |

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

### Phase 6 실연결 검증 `다음 단계`
인프라(MODE 분기·SQLite 로그) 구축 완료. 이제 실제 testnet API 키 발급 + 소액 실거래 검증 단계.
- (1) https://testnet.binance.vision 가입·HMAC 키 발급 후 `.env` 에 `MODE=testnet` + `BINANCE_TESTNET_*` 기재
- (2) `python main.py` → 텔레그램 부팅 메시지 `[MODE=TESTNET]` 확인
- (3) 그리드 진입·손절·recover 경로를 가상 자금으로 재현 후 `trades.db` 기록 검증
- (4) 결과 문서화 후 백테스트 단계 진입

---

### 백테스트 `후속`
과거 1~3년 캔들 데이터 기반 시뮬레이션. 페이퍼 검증 완료 후 착수. [TODO.md](TODO.md) Phase 6 참조.

---

### B7 — 캔들 수집 실패 감지 `낮음 ~30분`
무음 처리되는 API 오류 누적 시 후보 집단 탈락 감지 불가. 실패율 임계치 넘으면 알림.

---

## 완료된 작업

<details>
<summary>전체 이력 (클릭하여 펼치기)</summary>

| 날짜 | ID | 내용 |
|------|----|------|
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
