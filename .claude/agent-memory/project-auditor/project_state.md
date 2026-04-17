---
name: project_state
description: Daily 30K 봇 현재 구현 상태, 핵심 파라미터, 발견된 이슈 (2026-04-17 감사 기준)
type: project
---

## 구현 완료 단계

Phase 1~5 모두 TODO.md에 완료 표시. 실제 코드 7개 핵심 파일 모두 존재.

**Why:** Phase 4+5는 executor.py에 통합 구현됨.

## 핵심 파라미터 (config.py 확인값)

- SEED: 3,000,000원 (KRW)
- DAILY_TARGET: SEED * 1.0% = 30,000원
- DAILY_LOSS_LIMIT: SEED * 3.0% = 90,000원
- MAX_POSITION_RATE: 1% (1% Rule)
- STOP_LOSS_RATE: 2%
- GRID_COUNT: 5, GRID_SPACING: 0.5%
- FEE_RATE: 0.1%, INITIAL_BUY_RATIO: 50%
- SCANNER_INTERVAL_SEC: 900초 (15분)
- SCANNER_CANDLE_LIMIT: 30 (A9 수정 완료)
- KRW_RATE: 1350 (기본값, 30분마다 갱신)
- ccxt enableRateLimit=True: main.py에서 확인됨

## 2026-04-17 감사 — 버그 현황

### 해결된 이슈

- C1 (setup_grid 시장가→지정가): 완료. _limit_buy_with_retry 헬퍼 도입. 코드 확인.
- C3 (check_stop_loss/emergency_sell 수수료 누락): 완료. 수정 확인.
- C4 (regrid 트리거 buy_orders 조건): 완료. engine.buy_orders 체크 확인.
- A6 (regrid 매수 수수료 누락): 완료. _handle_buy_fill에서 즉시 차감 확인.
- A7 (consecutive_losses → is_market_healthy): 완료. check_loss_streak 헬퍼 확인.
- A8 (수수료 모델 일원화): 완료. 매수 체결 시점 즉시 차감 확인.
- A9 (SCANNER_CANDLE_LIMIT 15→30): 완료.
- H3 (PROJECT.md 완료 반영): 완료.
- H4 (_supervise 패턴): 완료. return_exceptions=True도 확인.

### 미해결 이슈

- C2: 재시작 시 포지션·주문 복구 로직 없음 → Phase 6 블로커
- H1: requirements.txt 없음 → Phase 6 블로커
- H2: 텔레그램 플러드 방지 없음

### 2026-04-17 신규 발견 버그

**HIGH:**

- [B1] _limit_buy_with_retry 미체결 감지 로직 결함: order_id not in open_orders 조건으로
  '체결 또는 취소됨'을 구분 못함. 주문이 외부 요인으로 cancel되어도 fill로 처리됨. 부분 체결
  (partially filled)도 처리 못함. (executor.py:146)

- [B2] check_stop_loss() 이후 avg_price 미초기화: total_qty=0으로 설정하지만 avg_price는
  그대로 남음. 이후 재진입 시 avg_price가 과거값으로 잘못 사용될 위험. (executor.py:329~331)

- [B3] _handle_sell_fill()에서 total_qty 음수 가능성: setup_grid에서 total_qty=fill_qty (초기
  매수량) 설정 후 sell_qty_each = fill_qty / GRID_COUNT로 5개 배치. 모두 체결 시
  total_qty -= qty * 5 → 총 qty 초과 가능. 단, 각 sell_qty가 반올림으로 살짝 다를 경우
  총합이 fill_qty를 초과할 수 있음. (executor.py:295, 207)

- [B4] regrid() 내 시장가 매도 후 _record_trade() 호출 시 total_qty 갱신 전 사용:
  regrid() L386에서 _record_trade(current_price, self.total_qty) 후 L389에서 total_qty=0.
  _record_trade 내부에서 self.consecutive_losses 갱신되는데, 이는 정상. 그러나 avg_price를
  0으로 리셋하지 않고 _record_trade 호출 — _record_trade는 self.avg_price를 사용하므로
  avg_price가 아직 valid한 경우 문제없음. 실제로는 regrid의 흐름상 avg_price는 유효함.
  (minor, 확인 필요)

- [B5] stability_score 고정 임계값 0.05: CV > 5%이면 stability_score=0. 그리드 매매 대상 코인의
  1시간봉 CV가 보통 5~15%이므로 대부분 코인이 0점. ATR 필터(0.5~5%)를 통과한 코인은 어느 정도
  변동성 있으므로 실질적으로 stability_score가 항상 0에 가까울 수 있음 → 가중치 20%가 낭비.
  (screener.py:263)

**MEDIUM:**

- [B6] _limit_buy_with_retry에서 buy_price = self.base_price로 재시도 시 현재가 기준이나,
  2차 시도부터 self.base_price = await self._get_current_price()로 갱신. 그러나 첫 시도에서
  base_price가 최신가가 아닐 수 있음 (setup_grid에서 이미 조회한 후 시간 경과).
  timeout=15초이므로 실제로는 15초 내 가격 변화 반영 안 됨. (executor.py:122~126)

- [B7] screener.py에서 캔들 수집 실패 코인은 조용히 제외됨 (notify 없음). API 오류 다발 시
  정상 코인도 제외될 수 있으나 감지 불가. (screener.py:171)

## 파일 구조 현황

모든 7개 핵심 파일 존재: config.py, shared_state.py, notifier.py, screener.py, executor.py, main.py, test.py
.env, .gitignore, .env.example 존재. requirements.txt 없음.

## Phase 6 진입 블로커 요약

1. C2: 재시작 포지션 복구 (필수)
2. H1: requirements.txt (필수)
3. B1: _limit_buy_with_retry 미체결 감지 오류 (권장)
4. B2: check_stop_loss avg_price 미초기화 (권장)
