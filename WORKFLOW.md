# WORKFLOW — Daily 30K Bot
> **세션 인수인계 문서.** 새 세션 시작 시 이 파일을 먼저 읽고, 작업 완료 후 즉시 업데이트.
> 상세 설계·아키텍처 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

---

## 현재 작업
없음 — 아래 "다음 작업" 목록 최상위 항목 선택

---

## 완료된 작업

| 날짜 | ID | 내용 |
|------|----|------|
| 2026-04-02 | C3 | `executor.py` — `check_stop_loss()` + `emergency_sell()` 매수 수수료 누락 수정 (손실 과소 계산 → 킬 스위치 지연 버그) |
| 2026-04-02 | H3 | `PROJECT.md` — Phase 4/5 완료 상태 반영 + `executor.py` 파일 구조 표 추가 |

---

## 다음 작업 목록 (우선순위 순)

### C4 — 리그리딩 트리거 조건 누락 [난이도: 쉬움 / ~15분]
**파일:** [executor.py:479](executor.py)
**문제:** `not engine.buy_orders` 조건 없음 → 매수 주문 미체결 상태에서 리그리딩 실행 가능 → 이중 포지션 위험
**수정 내용:**
```python
# Before (executor.py:479)
if engine.is_active and engine.total_qty <= 0 and not engine.sell_orders:

# After
if engine.is_active and engine.total_qty <= 0 and not engine.sell_orders and not engine.buy_orders:
```
**완료 기준:** 코드 수정 → `python test.py` 통과 → TODO.md 체크오프 → 이 파일 업데이트

---

### C1 — setup_grid() 시장가 매수 → 지정가로 교체 [난이도: 중간 / ~1시간]
**파일:** [executor.py:120-123](executor.py)
**문제:** `setup_grid()`에서 초기 매수가 `market` 주문 → CLAUDE.md "지정가 우선" 원칙 위반 + 슬리피지 발생
**수정 방향:**
- 현재가 기준 `limit buy` 주문으로 교체
- 지정가 미체결 시 처리 로직 필요 (타임아웃 후 취소 or 가격 재조정)
**완료 기준:** 코드 수정 → `python test.py` 통과 → TODO.md 체크오프 → 이 파일 업데이트

---

### H1 — requirements.txt 생성 [난이도: 쉬움 / ~10분]
**문제:** requirements.txt 없음 → VPS 배포 시 `pip install` 불가 → 실전 투입 블로커
**수정 내용:**
```bash
pip freeze > requirements.txt  # venv 활성화 상태에서 실행
```
이후 불필요한 패키지 제거 및 버전 고정 확인
**완료 기준:** requirements.txt 커밋 → 이 파일 업데이트

---

### C2 — 재시작 시 상태 복구 로직 [난이도: 어려움 / ~3~4시간]
**문제:** 봇 재시작 시 이전 포지션·주문 상태 복구 로직 없음 → 이중 포지션 위험 → 실전 투입 블로커
**수정 방향:**
1. 시작 시 바이낸스 API로 미체결 주문 조회 (`fetch_open_orders`)
2. 기존 포지션 잔고 조회 (`fetch_balance`)
3. 이전 상태 복원 or 안전하게 전량 정리 후 재시작
**완료 기준:** 재시작 테스트 시나리오 통과 → 이 파일 업데이트

---

### H2 — 텔레그램 플러드 방지 [난이도: 쉬움 / ~30분]
**파일:** [notifier.py](notifier.py)
**문제:** 오류 루프 발생 시 텔레그램 API 429 (Too Many Requests) 가능
**수정 방향:** 동일 메시지 중복 발송 억제 (deduplicate) + 최소 발송 간격 설정 (rate limit)
**완료 기준:** 코드 수정 → `python test.py` 통과 → TODO.md 체크오프 → 이 파일 업데이트

---

### H4 — asyncio.gather 장애 격리 [난이도: 중간 / ~1시간]
**파일:** [main.py](main.py)
**문제:** `asyncio.gather()`에서 컴포넌트 하나가 Exception으로 종료되면 전체 봇 중단
**수정 방향:** `return_exceptions=True` + 개별 컴포넌트 재시작 로직
**완료 기준:** 코드 수정 → `python test.py` 통과 → TODO.md 체크오프 → 이 파일 업데이트

---

### Phase 6 — 페이퍼 트레이딩
위의 Critical·High 항목 모두 해결 후 진행. [TODO.md](TODO.md) 참조.

---

## 작업 방식 원칙
1. **한 번에 하나.** 위 목록 최상위 항목 하나만 완료 후 다음으로.
2. **테스트 필수.** 코드 수정 후 반드시 `python test.py` 실행.
3. **즉시 기록.** 작업 완료 즉시 이 파일의 완료 테이블에 추가, 해당 항목 삭제.
4. **세션 종료 전.** 현재 작업이 미완성이면 "현재 작업" 섹션에 진행 상황 메모.
