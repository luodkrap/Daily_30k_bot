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

- [ ] 그리드 매매 로직 구현
- [ ] 동적 코인 스위칭
- [ ] `main.py:46` — Executor sleep 5s → 1s (손절 반응 지연 제거)
- [ ] `config.py:43` — SCANNER_INTERVAL_SEC 3600 → 900 (15분, 동적 스위칭 반응성)

### Phase 5 — 리스크 관리

- [ ] 손절매 (Stop-Loss)
- [ ] 1% Rule 포지션 사이징
- [ ] 시장 필터 (200MA 기준)
- [ ] 킬 스위치 + 일일 손실 한도

### Phase 6 — 검증

- [ ] 백테스트 (1~3년 데이터)
- [ ] 페이퍼 트레이딩

### Phase 7 — 배포

- [ ] VPS 세팅 (AWS EC2 / Ubuntu)
- [ ] systemd 서비스 등록 (자동 재시작)
