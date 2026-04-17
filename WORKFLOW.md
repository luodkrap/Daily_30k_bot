# WORKFLOW — Daily 30K Bot
> **세션 인수인계 문서.** 새 세션 시작 시 이 파일을 먼저 읽고, 작업 완료 후 즉시 업데이트.
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

**마지막 점검:** 2026-04-15 (project-auditor 전체 감사 완료) | 완료 누적: 2/3 (다음 점검까지)

---

## 현재 작업
없음 — 아래 "다음 작업" 목록 최상위 항목 선택

---

## 완료된 작업

| 날짜 | ID | 내용 |
|------|----|------|
| 2026-04-02 | C3 | `executor.py` — `check_stop_loss()` + `emergency_sell()` 매수 수수료 누락 수정 (손실 과소 계산 → 킬 스위치 지연 버그) |
| 2026-04-02 | H3 | `PROJECT.md` — Phase 4/5 완료 상태 반영 + `executor.py` 파일 구조 표 추가 |
| 2026-04-15 | C4 | `executor.py:481` — regrid 트리거에 `not engine.buy_orders` 조건 추가 (이중 포지션 방지) |
| 2026-04-15 | A6 | `executor.py:339` — `regrid()` 매수 수수료 누락 수정 (양방향 수수료 적용으로 PnL 정확도 확보) |
| 2026-04-15 | A7 | `executor.py` — `consecutive_losses ≥ RECENT_LOSS_STREAK(3)` 도달 시 `is_market_healthy=False` 자동 전환 (`check_loss_streak` 헬퍼 + 매도/손절/긴급매도/리그리딩 4곳에서 호출) |
| 2026-04-15 | H4 | `main.py` — `_supervise()` 패턴 도입. 컴포넌트 1개가 죽어도 자동 재시작(최대 5회), 한도 초과 시 킬 이벤트로 안전 종료 |
| 2026-04-15 | A8 | `executor.py` — 수수료 모델 일원화: 매수 체결 시점(`setup_grid` 초기 매수 + `_handle_buy_fill`)에 매수 수수료 즉시 차감, 매도 경로 4곳(`_handle_sell_fill`/`check_stop_loss`/`emergency_sell`/`regrid`)은 매도 수수료만 차감. 단위 테스트 2건 추가(setup 차감, 10회 회전 PnL=이론값과 일치). venv 재생성(python3.14) + 전 테스트 통과 |
| 2026-04-17 | C1 | `executor.py` — `setup_grid()` 초기 매수를 시장가→지정가로 교체. `_limit_buy_with_retry` 헬퍼(최대 3회 재시도, 회당 15초 타임아웃, 가격 재조정) 도입. `run_executor`에 setup 실패 시 engine=None 복구 추가. 단위 테스트 1건 추가(C1 limit 주문 확인). 전 테스트 통과 |

---

## 다음 작업 목록 (우선순위 순)

### A9 — ATR Wilder's Smoothing 워밍업 부족 [난이도: 쉬움 / ~5분]
**파일:** [config.py:60](config.py), [screener.py:195-203](screener.py)
**문제:** `SCANNER_CANDLE_LIMIT = 15`로는 TR 14개만 생성 → Wilder's Smoothing 루프(`tr_list[14:]`)가 빈 리스트라 미실행. 사실상 SMA(14)로만 동작 중.
**수정 내용:**
```python
SCANNER_CANDLE_LIMIT = 30  # ATR14 Wilder's Smoothing 워밍업 캔들 확보
```
**완료 기준:** config 변경 → `python test.py` 통과

---

### H1 — requirements.txt 생성 [난이도: 쉬움 / ~10분]
**문제:** requirements.txt 없음 → VPS 배포 시 `pip install` 불가 → 실전 투입 블로커
**전제조건:** venv 재생성 후(`python3.14 -m venv venv` + `pip install ccxt python-telegram-bot python-dotenv aiohttp`) 실행
**완료 기준:** requirements.txt 커밋 → 이 파일 업데이트

---

### H2 — 텔레그램 플러드 방지 [난이도: 쉬움 / ~30분]
**파일:** [notifier.py](notifier.py)
**문제:** 오류 루프 발생 시 텔레그램 API 429 (Too Many Requests) 가능
**수정 방향:** 동일 메시지 중복 발송 억제 (deduplicate) + 최소 발송 간격 설정 (rate limit)

---

### C2 — 재시작 시 상태 복구 로직 [난이도: 어려움 / ~3~4시간]
**문제:** 봇 재시작 시 이전 포지션·주문 상태 복구 로직 없음 → 이중 포지션 위험 → 실전 투입 블로커
**수정 방향:**
1. 시작 시 바이낸스 API로 미체결 주문 조회 (`fetch_open_orders`)
2. 기존 포지션 잔고 조회 (`fetch_balance`)
3. 이전 상태 복원 or 안전하게 전량 정리 후 재시작

---

### Phase 6 — 페이퍼 트레이딩
위의 Critical·High 항목 모두 해결 후 진행. [TODO.md](TODO.md) 참조.

---

## 작업 방식 원칙
1. **한 번에 하나.** 위 목록 최상위 항목 하나만 완료 후 다음으로.
2. **테스트 필수.** 코드 수정 후 반드시 `python test.py` 실행.
3. **즉시 기록.** 작업 완료 즉시 이 파일의 완료 테이블에 추가, 해당 항목 삭제.
4. **세션 종료 전.** 현재 작업이 미완성이면 "현재 작업" 섹션에 진행 상황 메모.
