# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 목표

하루 3만 원 수익을 목표로 하는 바이낸스 무인 자동매매 봇 (Project: Daily 30K).
설계자(사용자 도울)와 수석 개발자(Claude) 역할로 협업 중.
상세 설계 및 진행 상황은 [PROJECT.md](PROJECT.md) 참조.

## 개발 환경

```bash
source venv/bin/activate  # 세션 시작 시 필수
python test.py            # 실행
pip install <package>     # 패키지 설치
```

## 핵심 설계 원칙

- `ccxt` 사용 시 `enableRateLimit=True` 필수
- 모든 주문은 지정가(Limit Order) 우선
- 모든 API 호출에 `try-except` 적용, 오류 시 텔레그램으로 즉시 보고
- 손절매 / 1% Rule / 킬 스위치는 어떤 상황에서도 우선 실행
