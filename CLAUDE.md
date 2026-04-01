# CLAUDE.md

> **목표:** 하루 3만 원 수익 — 바이낸스 무인 자동매매 봇 (Project: Daily 30K)  
> 설계자: 도울 | 수석 개발자: Claude  
> 상세 설계·아키텍처·로드맵 → [PROJECT.md](PROJECT.md) | 작업 현황 → [TODO.md](TODO.md)

## 개발 환경

```bash
source venv/bin/activate   # 세션 시작 시 필수
python test.py             # 테스트 실행
pip install <package>      # 패키지 설치
```

## 프로젝트 파일 구조

```
config.py        — .env 로드, SEED 기반 수치 자동 계산 (모든 모듈이 import)
shared_state.py  — BotState dataclass (킬 이벤트, 손익, 시장 상태 공유)
notifier.py      — 텔레그램 비동기 알림 모듈
screener.py      — 스캐너 엔진 (유동성·변동성·펌프앤덤프 필터 + 점수 정렬)
main.py          — asyncio.gather()로 3개 컴포넌트 동시 실행
test.py          — 단위·통합 테스트
```

## 절대 원칙 (예외 없음)

- 손절매 / 1% Rule / 킬 스위치는 **어떤 상황에서도 최우선 실행**
- `ccxt`: `enableRateLimit=True` 필수
- 모든 주문: 지정가(Limit Order) 우선
- 모든 API 호출: `try-except` 적용, 오류 시 텔레그램 즉시 보고
