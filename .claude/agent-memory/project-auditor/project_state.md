---
name: project_state
description: Daily 30K 봇 현재 구현 상태, 핵심 파라미터, 발견된 이슈 (2026-04-15 감사 기준)
type: project
---

## 구현 완료 단계

Phase 1~5 모두 TODO.md에 완료 표시. 실제 코드 7개 핵심 파일 모두 존재.

**Why:** Phase 4+5는 2026-04-01 spec 문서 기반으로 executor.py에 통합 구현됨.
**How to apply:** 코드 리뷰 시 spec 파일(docs/superpowers/specs/2026-04-01-phase4-trading-engine-design.md)과 대조할 것.

## 핵심 파라미터 (config.py 확인값)

- SEED: 3,000,000원 (KRW)
- DAILY_TARGET: SEED * 1.0% = 30,000원
- DAILY_LOSS_LIMIT: SEED * 3.0% = 90,000원
- MAX_POSITION_RATE: 1% (1% Rule)
- STOP_LOSS_RATE: 2%
- GRID_COUNT: 5, GRID_SPACING: 0.5%
- FEE_RATE: 0.1%, INITIAL_BUY_RATIO: 50%
- SCANNER_INTERVAL_SEC: 900초 (15분)
- KRW_RATE: 1350 (기본값, 30분마다 갱신)
- ccxt enableRateLimit=True: main.py에서 확인됨

## 2026-04-15 감사 — 버그 현황

### TODO 상태 vs 실제 코드 불일치

- C3 (check_stop_loss/emergency_sell 수수료 누락): TODO 완료 표시. 코드에서 buy_fee_usdt + sell_fee_usdt 모두 반영됨. 수정 확인.
- H3 (PROJECT.md Phase 4/5 완료 반영): TODO 완료 표시. PROJECT.md에 Phase 4/5 완료 반영됨. 수정 확인.
- C4 (regrid 트리거 buy_orders 조건 누락): TODO 미완료. 코드(executor.py:481)에 not engine.buy_orders 조건 없음. 미수정 확인.
- C1 (setup_grid 시장가 매수): TODO 미완료. executor.py:122에 "market" buy 그대로. 미수정 확인.
- C2 (재시작 상태복구): 미구현.
- H1 (requirements.txt): 없음.
- H2 (텔레그램 플러드 방지): 미구현.
- H4 (asyncio.gather return_exceptions): main.py에 return_exceptions=True 없음.

### 새로 발견된 버그 (2026-04-15)

**CRITICAL:**
- regrid() 수수료 계산 오류: fee_usdt = current_price * qty * FEE_RATE만 계산 (매도 수수료만). 매수 수수료(avg_price * qty * FEE_RATE) 누락. executor.py:339. → PnL 과대계산 → 킬스위치 지연.
- _handle_sell_fill() 수수료 이중 계산 잔존: fee_usdt = (sell_price * qty + avg_price * qty) * FEE_RATE. avg_price * qty * FEE_RATE는 이미 setup_grid 시장가 매수 시 지불됨. 그리드 매매에서 매수 체결은 지정가이므로 매도 시점에 매수 수수료까지 차감하는 것은 맞으나, 초기 시장가 매수 수수료는 avg_price에 미포함되어 실제로는 이 계산이 옳을 수 있음 — 단, setup_grid에서 avg_price = fill_price (명목가격)로 기록하므로 매수 수수료가 avg_price에 포함되지 않음. 이 경우 이중 차감임.

**HIGH:**
- SCANNER_CANDLE_LIMIT=15로 TR이 14개 → Wilder's Smoothing이 사실상 실행 안 됨 (tr_list[14:]가 빈 리스트). 단순 SMA(14)로 동작. screener.py:202.
- consecutive_losses → is_market_healthy 연동 미구현: config.py에 RECENT_LOSS_STREAK=3 정의되어 있으나 executor.py에서 참조 안 함. 연속 손실 3회 경고/진입 차단 기능 미동작.
- 단일 후보 코인 시 vol_score 계산 오류: v_range = max(v_max - v_min, 1)인데 후보 1개면 v_min=v_max → v_range=1 → vol_score=(volume - volume)/1=0. 사실상 무해하지만 논리적 불일치.
- stability_score 임계값 0.05 고정: 시장 상황에 따라 매우 변동성이 높은 코인만 남는 상황에서 모두 0점이 될 수 있음.

## 파일 구조 현황

모든 7개 핵심 파일 존재: config.py, shared_state.py, notifier.py, screener.py, executor.py, main.py, test.py
.env, .gitignore, .env.example 존재. requirements.txt 없음.
