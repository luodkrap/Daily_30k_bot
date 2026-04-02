---
name: project_state
description: Daily 30K 봇 현재 구현 상태, 핵심 파라미터, 발견된 주요 이슈 (2026-04-02 감사 기준)
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

## 발견된 주요 이슈 (2026-04-02 감사)

### CRITICAL
1. setup_grid()에 시장가 매수 사용 — CLAUDE.md 절대 원칙 위반 (모든 주문은 limit order)
2. regrid()에 시장가 매도 사용 — 동일 원칙 위반
3. check_stop_loss()에 시장가 매도 — 손절매는 예외로 볼 수 있으나 설계 문서 검토 필요
4. emergency_sell()에 시장가 매도 — 긴급상황 예외인지 확인 필요
5. PROJECT.md 로드맵이 코드 현실을 반영 못함 (Phase 4 미착수로 표기)

### HIGH
1. stop_loss 후 미체결 주문 취소 순서 버그: check_stop_loss()에서 시장가 매도 → cancel_all() 순서인데, cancel_all()이 실패해도 진행됨 (허용 가능)
2. _handle_sell_fill PnL 계산 오류: fee_usdt = (sell_price * qty + avg_price * qty) * FEE_RATE — 이중 수수료 적용(매도 + 평균매수가에도 수수료). 실제는 매수 시점에 이미 수수료 지불됨. avg_price는 이미 수수료 포함 가격이어야 하는데, 코드상 avg_price가 지정가 주문의 명목가격으로 기록됨. 수수료 과잉 차감 가능성 있음.
3. 포지션 복구 로직 없음: 서버 재부팅 시 기존 포지션 복구 불가 (PROJECT.md Section 8.1에서 요구)
4. SQLite/CSV 거래 기록 없음: PROJECT.md Section 8.1 요구사항 미구현

### MEDIUM
1. requirements.txt 없음
2. 텔레그램 봇 라이브러리 미스매치: main.py는 python-telegram-bot 사용, notifier.py는 aiohttp 직접 사용 — 일관성 부족
3. screener.py에 enableRateLimit 확인 불가 — exchange 인스턴스는 main.py에서 생성되어 전달됨 (OK)
4. test_market_filter가 "unhealthy" 시나리오 미테스트
5. 적응형 파라미터 자동 조정(params.json) 미구현 — config.py에 ADAPTIVE_SAMPLE_SIZE 있으나 로직 없음

## 파일 구조 현황

모든 7개 핵심 파일 존재: config.py, shared_state.py, notifier.py, screener.py, executor.py, main.py, test.py
.env, .gitignore, .env.example 존재. requirements.txt 없음.
