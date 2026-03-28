# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목표

하루 3만 원 수익을 목표로 하는 바이낸스 무인 자동매매 봇 (Project: Daily 30K).
설계자(사용자 도울)와 수석 개발자(Claude) 역할로 협업 중.
상세 설계는 [PROJECT.md](PROJECT.md) 참조.

## 개발 환경

- **Python:** `/opt/homebrew/bin/python3` (Homebrew)
- **가상환경:** `venv/` — 반드시 활성화 후 작업
  ```bash
  source venv/bin/activate
  ```
- **실행:**
  ```bash
  python test.py
  ```
- **패키지 설치:**
  ```bash
  pip install <package>
  ```

## 아키텍처 (목표 구조)

봇은 3개의 독립 모듈로 구성될 예정:

| 모듈 | 파일 (예정) | 역할 |
|------|------------|------|
| 스캐너 엔진 | `screener.py` | 매 1시간 바이낸스 전 종목 스캔, 유동성/변동성 필터로 타겟 코인 선정 |
| 트레이딩 엔진 | `executor.py` | 그리드 매매 실행, 동적 코인 스위칭, 포지션 관리 |
| 알림/제어 모듈 | `notifier.py` | 텔레그램 알림 + `/status`, `/stop` 명령 처리 |

공통 설정은 `.env`에서 로드 (`python-dotenv` 사용).
상태(포지션, 진입가 등)는 SQLite 또는 JSON 파일에 영속화 예정.

## 핵심 설계 원칙

- **ccxt** 사용 시 `enableRateLimit=True` 필수 (바이낸스 IP 차단 방지)
- 모든 주문은 **지정가(Limit Order)** 우선 (슬리피지 최소화)
- 모든 API 호출에 `try-except` 적용, 오류 시 텔레그램으로 즉시 보고
- 손절매 / 1% Rule / 킬 스위치는 어떤 상황에서도 우선 실행

## 현재 진행 상황

- [x] 텔레그램 연결 테스트 (`test.py`)
- [x] `.env` 환경변수 설정 완료 (Binance + Telegram)
- [ ] 바이낸스 API 실제 연동 (ccxt, Phase 1 진행 중)
- [ ] 스캐너 / 트레이딩 / 리스크 모듈 구현
- [ ] 백테스트 → 페이퍼 트레이딩 → VPS 배포
