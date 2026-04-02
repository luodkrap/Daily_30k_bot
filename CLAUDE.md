# CLAUDE.md

> **목표:** 하루 3만 원 수익 — 바이낸스 무인 자동매매 봇 (Project: Daily 30K)  
> 설계자: 도울 | 수석 개발자: Claude  
> **현재 작업 현황 (세션 인수인계) → [WORKFLOW.md](WORKFLOW.md)**  
> 상세 설계·아키텍처·로드맵 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

## 세션 시작 절차

새 대화 시작 시 → **[WORKFLOW.md](WORKFLOW.md) 먼저 읽기** → "현재 작업"이 있으면 이어서, 없으면 "다음 작업 목록" 최상위 항목 선택.

## 문서화 규칙 (Documentation Rules)

1. **PROJECT.md 업데이트:** 로직에 중요한 변화가 생길 때마다(특히 매매 전략이나 API 호출 관련) PROJECT.md를 즉시 업데이트할 것.
2. **TODO.md 즉시 반영:** TODO.md에 명시된 작업이 완료되면, 지체 없이 완료 표시(Check-off)를 할 것.
3. **기록 후 실행:** 새로운 버그가 발견되거나 새로운 기능이 계획되면, 구현을 시작하기 전에 반드시 TODO.md에 먼저 추가할 것.
4. **WORKFLOW.md 즉시 반영:** 작업 완료 즉시 WORKFLOW.md 완료 테이블에 추가하고 해당 항목을 삭제할 것. 세션 종료 전 미완성 작업은 "현재 작업" 섹션에 진행 상황을 기록할 것.

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
executor.py      — 트레이딩 엔진 (GridEngine + run_executor + 200MA 필터)
main.py          — asyncio.gather()로 3개 컴포넌트 동시 실행
test.py          — 단위·통합 테스트
```

## 절대 원칙 (예외 없음)

- 손절매 / 1% Rule / 킬 스위치는 **어떤 상황에서도 최우선 실행**
- `ccxt`: `enableRateLimit=True` 필수
- 모든 주문: 지정가(Limit Order) 우선
- 모든 API 호출: `try-except` 적용, 오류 시 텔레그램 즉시 보고
