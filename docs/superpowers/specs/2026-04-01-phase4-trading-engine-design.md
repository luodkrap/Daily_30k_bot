# Phase 4+5 통합 설계: 트레이딩 엔진 + 리스크 관리

> 작성일: 2026-04-01 | 프로젝트: Daily 30K Bot

## 1. 목적

스캐너(Phase 3)가 선정한 타겟 코인에 대해 그리드 매매를 실행하고, 손절매·킬 스위치·시장 필터 등 리스크 관리를 통합한 완전한 트레이딩 엔진 구현.

## 2. 파일 구조

| 파일 | 변경 | 내용 |
|---|---|---|
| `executor.py` | **신규** | GridEngine 클래스 + run_executor 루프 |
| `config.py` | 수정 | FEE_RATE, INITIAL_BUY_RATIO 등 상수 추가 |
| `shared_state.py` | 수정 | BotState 포지션 추적 필드 보강 |
| `main.py` | 수정 | run_executor를 executor.py에서 import, sleep 1s |

## 3. config.py 추가 상수

```python
FEE_RATE          = 0.001     # 바이낸스 현물 수수료 0.1%
INITIAL_BUY_RATIO = 0.50      # 투입금 중 시장가 즉시 매수 비율 50%
MIN_PROFIT_RATIO  = 0.001     # 최소 순수익 기준 0.1% (수수료 제외)
REGRID_ENABLED    = True      # 상단 이탈 시 리그리딩 ON/OFF
```

## 4. shared_state.py 보강

기존 `current_position: dict`, `grid_orders: list` 필드를 활용.

```python
current_position: dict   # {"symbol", "qty", "avg_price", "invested_usdt"}
grid_orders: list        # [{"id", "side", "price", "qty", "grid_level"}, ...]
```

## 5. executor.py 설계

### 5.1 GridEngine 클래스

```python
class GridEngine:
    symbol: str              # "ETH/USDT"
    base_price: float        # 그리드 기준가
    qty_per_grid: float      # 그리드 레벨당 수량
    buy_orders: dict         # {order_id: grid_info}
    sell_orders: dict        # {order_id: grid_info}
    total_invested: float    # 투입 USDT
    total_qty: float         # 보유 코인 수량
    avg_price: float         # 평균 매수가
    is_active: bool          # 그리드 활성 여부
```

**메서드:**

- `setup_grid()`: 수수료 검증 → 1% Rule 포지션 사이징 → 시장가 50% 매수 → 매도 5개 + 매수 5개 배치
- `monitor_orders()`: 1초 폴링, fetch_open_orders로 체결 감지
- `handle_fill(order)`: 매수 체결 → 위에 매도 생성 / 매도 체결 → 아래에 매수 재배치 + 수익 기록
- `check_stop_loss(current_price)`: 현재가 < avg_price × (1 - STOP_LOSS_RATE) → 전량 시장가 매도
- `cancel_all()`: 거래소 미체결 주문 전부 취소
- `regrid()`: 현재가 기준으로 그리드 새로 배치 (REGRID_ENABLED일 때)

### 5.2 그리드 배치 상세

```
현재가 $100, GRID_COUNT=5, GRID_SPACING=0.5%

매도 Grid +5: $102.5
매도 Grid +4: $102.0
매도 Grid +3: $101.5
매도 Grid +2: $101.0
매도 Grid +1: $100.5
────── 현재가 $100.0 ──────
매수 Grid -1: $99.5
매수 Grid -2: $99.0
매수 Grid -3: $98.5
매수 Grid -4: $98.0
매수 Grid -5: $97.5
```

### 5.3 초기 매수 (Initial Buy)

현물 매매이므로 매도 그리드 물량 확보가 필요:
1. 1% Rule로 최대 투입금 계산: `max_invest = (SEED_USDT × MAX_POSITION_RATE) / STOP_LOSS_RATE`
2. 시장가 매수: `max_invest × INITIAL_BUY_RATIO` (50%)
3. 매수한 물량을 매도 그리드 5개에 균등 배분
4. 나머지 50%는 매수 그리드 5개에 균등 배분

### 5.4 수수료 검증

진입 전 체크: `GRID_SPACING - (FEE_RATE × 2) >= MIN_PROFIT_RATIO`
- 0.5% - 0.2% = 0.3% >= 0.1% → OK
- 실패 시 진입 거부 + 텔레그램 알림

### 5.5 체결 대응 (handle_fill)

**매수 체결:**
- 보유량·평균가 갱신
- 체결가 × (1 + GRID_SPACING) 에 매도 지정가 주문 생성

**매도 체결:**
- 실현 수익 계산: `(매도가 - 매수가) × 수량 - 왕복수수료`
- state.daily_pnl += 실현 수익
- state.trade_count += 1 (수익이면 win_count도 +1)
- 체결가 × (1 - GRID_SPACING) 에 매수 지정가 주문 재배치

### 5.6 상단 이탈 리그리딩

조건: 모든 매도 주문 체결 + 보유량 = 0
- REGRID_ENABLED=True → 현재가 fetch → regrid() 호출
- REGRID_ENABLED=False → 대기 (스캐너의 다음 타겟 기다림)

### 5.7 동적 코인 스위칭

매 폴링마다 `state.target_coin != engine.symbol` 체크:
1. 현재 포지션 있음 → 시장가 전량 매도 + cancel_all()
2. 손익 기록
3. 새 GridEngine 생성 → setup_grid()

## 6. 안전장치 (매 루프 체크 순서)

```
1. kill_event           → 전 주문 취소 + 전량 매도 + 종료
2. 일일 손실 한도 초과  → 킬 스위치 발동
3. 일일 목표 수익 달성  → 하드 스탑
4. 손절매               → 전량 매도 + 그리드 취소
5. 200MA 필터 (BTC)    → 신규 진입만 차단 (기존 포지션 유지)
6. 일반 매매 로직 실행
```

### 6.1 200MA 시장 필터

- `fetch_ohlcv("BTC/USDT", "1d", limit=201)` → 200일 이동평균 계산
- 30분마다 갱신 (별도 타이머)
- BTC 현재가 < 200MA → `state.is_market_healthy = False`
- 신규 진입 차단, 기존 포지션은 그리드 계속 운영

### 6.2 에러 복구

- API 오류 시 3회 재시도 (지수 백오프: 1s → 2s → 4s)
- 3회 실패 → 텔레그램 알림 + 해당 사이클 스킵
- 네트워크 장애 시 기존 지정가 주문은 거래소에 유지 (안전)

## 7. main.py 수정

```python
from executor import run_executor  # 기존 뼈대 교체
# Executor sleep: 5s → 1s (executor.py 내부)
```

## 8. 포지션 사이징 계산 예시

```
SEED = 3,000,000원, 환율 1350
USDT 시드 ≈ $2,222
1% Rule: 최대 손실 = $22.2
손절 2%: 투입 가능 = $22.2 / 0.02 = $1,111
초기 매수: $1,111 × 50% = $555.5
매도 그리드: $555.5 상당 코인 ÷ 5 레벨
매수 그리드: $555.5 ÷ 5 레벨
```

## 9. 검증 방법

1. 단위 테스트: GridEngine 각 메서드 (mock exchange)
2. 통합 테스트: 시나리오별 시뮬레이션 (매수체결 → 매도생성, 손절, 리그리딩)
3. `python test.py` 전체 통과
4. Phase 6 페이퍼 트레이딩으로 실전 검증
