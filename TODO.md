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
- [ ] config.py — 설정값 중앙 관리
- [ ] notifier.py — 텔레그램 알림 모듈
- [ ] screener.py — 스캐너 엔진 뼈대

### Phase 3 — 스캐너 엔진
- [ ] 24h 거래량 $100M 이상 필터
- [ ] ATR 기반 변동성 필터
- [ ] 펌프앤덤프 역필터

### Phase 4 — 트레이딩 엔진
- [ ] 그리드 매매 로직 구현
- [ ] 동적 코인 스위칭

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
