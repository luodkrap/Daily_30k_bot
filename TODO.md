# TODO — Daily 30K Bot

## 완료 (Done)

- [x] 프로젝트 설계 문서 (PROJECT.md)
- [x] .env 환경변수 설정
- [x] test.py — 텔레그램 연결 테스트
- [x] 바이낸스 ccxt 연동 — BTC 실시간 가격 수신
- [x] GitHub 레포 세팅 및 /push 슬래시 커맨드

## 진행 중 (In Progress)

없음

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
- [ ] C2: 재시작 시 포지션·주문 상태 복구 로직 없음 → 이중 포지션 위험 (실전 투입 블로커)

**높은 우선순위 (High) — 실전 투입 전 해결**
- [x] H3: PROJECT.md 로드맵 Phase 4/5 완료 상태 미반영 (CLAUDE.md Rule 1 위반)
- [x] H4: `asyncio.gather` 컴포넌트 하나 실패 시 전체 봇 중단 → `_supervise()` 패턴으로 격리
- [ ] H1: `requirements.txt` 없음 → VPS 배포 불가 (실전 투입 블로커)
- [ ] H2: 텔레그램 플러드 방지 없음 → 오류 루프 시 API 429

**감사 결과 추가 (2026-04-15)**
- [x] A6: `regrid()` 매수 수수료 누락 → 양방향 수수료 적용
- [x] A7: `consecutive_losses → is_market_healthy` 미연동 → `check_loss_streak` 헬퍼 도입
- [x] A8: `_handle_sell_fill()` 수수료 이중 차감 → 매수 수수료를 매수 체결 시점으로 분리
- [x] A9: ATR `SCANNER_CANDLE_LIMIT=15` 부족 → 30으로 확대 (Wilder's Smoothing 동작)

**감사 결과 추가 (2026-04-17) — Phase 6 블로커 포함**
- [ ] B1: `_limit_buy_with_retry` 외부 취소 주문을 체결로 오인 → 공매도 위험 (**Phase 6 블로커**)
- [ ] B2: `check_stop_loss()` 후 `avg_price` 미초기화 → `emergency_sell`/`regrid`와 일관성 위반
- [ ] B3: `sell_qty` 총합이 `total_qty` 초과 가능 → stepSize 큰 자산에서 insufficient balance 오류
- [ ] B5: `stability_score` 임계값 0.05 실효성 없음 → 가중치 20% 사실상 낭비
- [ ] B7: 캔들 수집 실패 무음 처리 → API 오류 다발 시 후보 코인 집단 탈락 감지 불가

### Phase 6 — 검증

- [ ] 백테스트 (1~3년 데이터)
- [ ] 페이퍼 트레이딩

### Phase 7 — 배포

- [ ] VPS 세팅 (AWS EC2 / Ubuntu)
- [ ] systemd 서비스 등록 (자동 재시작)
