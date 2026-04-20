# WORKFLOW — Daily 30K Bot

> **세션 인수인계 문서.** 새 세션 시작 → 이 파일만 읽으면 10초 내 상태 파악 가능.  
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

---

## 🔲 빠른 상태 (Quick Status)

| 항목 | 값 |
|------|----|
| **현재 Phase** | Phase 5 (핵심 로직 완성) → Phase 6 (페이퍼 트레이딩) 진입 대기 |
| **마지막 점검** | 2026-04-17 (project-auditor 전체 감사) |
| **점검 누적** | 2/3 |
| **남은 블로커** | C2(상태 복구), B1(_limit_buy_with_retry 결함) — 이 2개 해결 전 Phase 6 진입 불가 |
| **테스트 상태** | 전체 통과 (2026-04-17 C1 작업 후 확인) |

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
| 2026-04-20 | [CLAUDE.md](CLAUDE.md), [.claudeignore](.claudeignore), [skills/](skills/) | 토큰 절약 구조 개편: .claudeignore 추가, CLAUDE.md 슬림화, 자동점검·문서화·컨벤션을 skills/로 분리 |
| 2026-04-17 | [executor.py](executor.py) | B2: `check_stop_loss()` avg_price·total_invested 0 초기화 추가 |
| 2026-04-17 | [requirements.txt](requirements.txt) | H1: `pip freeze` 기반 requirements.txt 생성 (VPS 배포 준비) |
| 2026-04-17 | [config.py](config.py) | A9: `SCANNER_CANDLE_LIMIT` 15→30 (Wilder's Smoothing 워밍업 확보) |
| 2026-04-17 | [executor.py](executor.py) | C1: `setup_grid()` 시장가→지정가 전환, `_limit_buy_with_retry` 헬퍼 추가 |
| 2026-04-17 | [test.py](test.py) | C1: 지정가 매수 단위 테스트 1건 추가 |
| 2026-04-15 | [executor.py](executor.py) | C4+A6+A7+A8: regrid 이중 포지션 방지, 수수료 모델 일원화, 연패 감지 |
| 2026-04-15 | [main.py](main.py) | H4: `_supervise()` 자동 재시작 패턴 도입 |

---

## 다음 작업 목록 (우선순위 순)

### B1 — _limit_buy_with_retry 미체결 감지 결함 `보통 ~1~2시간`
**파일:** [executor.py](executor.py) `:146`  
**문제:** `open_orders`에 없으면 "체결"로 판단 → 외부 취소된 주문도 체결로 오인 → 미보유 수량에 매도 그리드 배치 → **공매도 위험** → **Phase 6 블로커**  
**수정 방향:** `fetch_order(order_id)` 호출로 `status`와 `filled` 수량 직접 확인. `status=="canceled"` → 재시도, `status=="closed"` → `filled` 수량 반환  
**완료 기준:** 취소 주문 케이스 테스트 추가 + `python test.py` 통과

---

### H2 — 텔레그램 플러드 방지 `쉬움 ~30분`
**파일:** [notifier.py](notifier.py)  
**문제:** 오류 루프 시 텔레그램 API 429 (Too Many Requests) 가능  
**수정 방향:** 동일 메시지 60초 이내 중복 억제 (dedup dict) + 전체 발송 최소 간격 1초

---

### C2 — 재시작 시 상태 복구 로직 `어려움 ~3~4시간`
**문제:** 봇 재시작 시 이전 포지션·주문 복구 없음 → 이중 포지션 위험 → **Phase 6 블로커**  
**수정 방향:**
1. `fetch_open_orders` — 미체결 주문 조회
2. `fetch_balance` — 기존 포지션 잔고 조회
3. 이전 상태 복원 or 전량 정리 후 재시작

---

### Phase 6 — 페이퍼 트레이딩
위의 블로커 항목 모두 해결 후 진행. [TODO.md](TODO.md) 참조.

---

## 완료된 작업

<details>
<summary>전체 이력 (클릭하여 펼치기)</summary>

| 날짜 | ID | 내용 |
|------|----|------|
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
