# AGENTS.md

> **목표:** 하루 3만 원 수익 — 바이낸스 무인 자동매매 봇 (Project: Daily 30K)
> 설계자: 도울 | 수석 개발자: Codex
> **현재 작업 현황 (세션 인수인계) → [WORKFLOW.md](WORKFLOW.md)**
> 상세 설계·아키텍처·로드맵 → [PROJECT.md](PROJECT.md) | 기능 백로그 → [TODO.md](TODO.md)

## 세션 시작 절차

새 대화 시작 시 → **[WORKFLOW.md](WORKFLOW.md) 먼저 읽기** → "현재 작업"이 있으면 이어서, 없으면 "다음 작업 목록" 최상위 항목 선택.

## 작업 완료 체크리스트 (예외 없음)

작업 하나 완료 시 **반드시 세 파일 갱신** (누락 1건이라도 작업 미완료로 간주):
1. [WORKFLOW.md](WORKFLOW.md) — 완료 테이블 추가 + 다음 작업 목록에서 제거 + 파일 변경 이력 추가
2. [TODO.md](TODO.md) — 해당 항목 `- [ ]` → `- [x]` 체크 + 완료일/설명 추가
3. [PROJECT.md](PROJECT.md) — 매매 전략/API 호출 관련 변경을 동반한 경우에만

## 세션 종료 절차 (예외 없음)

작업 도중 세션이 끝날 가능성이 보이면 **종료 직전 무조건** [WORKFLOW.md](WORKFLOW.md) "현재 작업" 섹션을 채울 것:
- 작업 ID / 제목 / 진행도(%) / 수정 중인 파일 / 다음 실행 명령어 / 블로커·메모

비어있는 채로 종료 금지. 다음 세션 Codex 가 진행도 0% 로 오해해 처음부터 시작하는 사태 방지.

## 사용자 의사결정 변경 시 (예외 없음)

사용자가 우선순위·트랙·일정·전략을 변경하면 **즉시** [WORKFLOW.md](WORKFLOW.md) 의
- **Quick Status "현재 Phase" 줄** — 새 합의 흐름 한 줄 요약
- **"현재 작업" 섹션** — 변경된 다음 액션 + 변경 합의일 + 결정 근거 1줄

이 두 곳을 갱신할 것. 새 세션이 옛 우선순위로 작업 시작하는 사태 방지.

## 토큰 절약 규칙 (4)

1. **이미 읽은 파일 재확인 금지** — 같은 세션에서 동일 파일을 두 번 Read 하지 말 것. 변경 여부 확인이 필요하면 Grep으로 대상 심볼만 확인.
2. **탐색 전 계획** — 파일 구조를 모르는 경우 Glob/Grep으로 위치 확정 후 Read. 추측으로 Read 남발 금지.
3. **WORKFLOW.md 우선 로드** — 세션 시작 시 이 파일만으로 상태 파악. PROJECT.md/TODO.md는 필요 시에만.
4. **스킬 온디맨드** — 자동 점검·문서화 규칙은 트리거 조건 충족 시에만 `skills/*.md`를 읽을 것. 매 세션 기본 로드 금지.

## 온디맨드 스킬 (필요 시에만 참조)

- 자동 점검 규칙 (트리거·명령) → [skills/auto-checkpoint.md](skills/auto-checkpoint.md)
- 문서화 규칙 (PROJECT/TODO/WORKFLOW 갱신 규칙) → [skills/documentation-rules.md](skills/documentation-rules.md)
- 확정 아키텍처·컨벤션 (반복 질문 방지) → [skills/conventions.md](skills/conventions.md)
- 배포 가이드 규칙 (코드 변경 후 Lightsail 반영 단계 안내) → [skills/deploy-advisor.md](skills/deploy-advisor.md)

## 개발 환경

```bash
source venv/bin/activate   # 세션 시작 시 필수
python test.py             # 테스트 실행
pip install <package>      # 패키지 설치
```

## 프로젝트 파일 구조

```
config.py        — .env 로드, MODE(live/testnet) 분기, SEED 기반 수치 자동 계산
shared_state.py  — BotState dataclass (킬 이벤트, 손익, 시장 상태 공유)
notifier.py      — 텔레그램 비동기 알림 모듈
screener.py      — 스캐너 엔진 (유동성·변동성·펌프앤덤프 필터 + 점수 정렬)
executor.py      — 트레이딩 엔진 (GridEngine + run_executor + 200MA 필터)
persistence.py   — SQLite trades.db 체결 로그 (live/testnet mode 컬럼 분리)
main.py          — asyncio.gather()로 3개 컴포넌트 동시 실행 + set_sandbox_mode 분기
test.py          — 단위·통합 테스트
```

## 절대 원칙 (예외 없음)

- 손절매 / 1% Rule / 킬 스위치는 **어떤 상황에서도 최우선 실행**
- `ccxt`: `enableRateLimit=True` 필수
- 모든 주문: 지정가(Limit Order) 우선
- 모든 API 호출: `try-except` 적용, 오류 시 텔레그램 즉시 보고
- **MODE 분리 (Phase 6~):** `MODE=live` 는 `BINANCE_API_KEY`, `MODE=testnet` 은 `BINANCE_TESTNET_API_KEY` — 실거래 키와 testnet 키를 **같은 env var 에 섞지 말 것.** 부팅 텔레그램 메시지의 `[MODE=...]` 로 교차 확인 필수.
