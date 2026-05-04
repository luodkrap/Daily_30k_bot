# Daily 30K Bot

> 바이낸스 무인 자동매매 봇 — 하루 3만 원 수익을 목표로 하는 그리드 트레이딩 시스템

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Exchange](https://img.shields.io/badge/Exchange-Binance-yellow)
![Status](https://img.shields.io/badge/Phase-7%20%28Observation%20Mode%29-green)
![Deploy](https://img.shields.io/badge/Deploy-Lightsail%20%2B%20Supabase-purple)

---

## 목차

1. [개요](#개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [매매 전략](#매매-전략)
4. [리스크 관리](#리스크-관리)
5. [설치 및 실행](#설치-및-실행)
6. [텔레그램 명령어](#텔레그램-명령어)
7. [파일 구조](#파일-구조)
8. [주요 설정값](#주요-설정값)
9. [개발 현황](#개발-현황)
10. [주의사항](#주의사항)

---

## 개요

**목표:** 300만 원 시드로 하루 30,000원(1%)의 안정적인 자동 수익 창출

**핵심 철학:**

- 큰 기회를 노리지 않고 **확률적 우위 + 기계적 리스크 관리**에 집중
- 인간의 감성 배제, 24시간 완전 무인 운영
- 그리드 매매로 횡보장에서 수익, 4중 안전망으로 손실 차단

**현재 상태:** Phase 7 — Lightsail VPS + Supabase 원격 적재 운영, **관찰 모드(페이퍼 누적)** 진행 중. 14일 누적 후 MODE=live 전환 판단.

---

## 시스템 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│                    main.py                               │
│        asyncio.gather() — 3개 컴포넌트 동시 실행         │
└──────────┬──────────────┬────────────────┬───────────────┘
           │              │                │
    ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
    │  screener   │ │  executor  │ │  telegram   │
    │             │ │            │ │     bot     │
    │ - 15분 주기  │ │ - 그리드   │ │ - /status  │
    │ - 5단계 필터 │ │   매매     │ │ - /stop    │
    │ - 점수 정렬  │ │ - 손절·매도│ │ - /seed    │
    │ - 최적 코인  │ │ - 동적     │ │            │
    │   선정      │ │   스위칭   │ │            │
    └──────┬──────┘ └─────┬──────┘ └────────────┘
           │              │
           └──────┬───────┘
            ┌─────▼──────┐
            │ shared_    │
            │ state.py   │
            │ (BotState) │
            └─────┬──────┘
                  │
            ┌─────▼──────┐
            │ persistence│
            │  (Supabase │
            │   primary, │
            │   SQLite   │
            │  fallback) │
            └────────────┘
```

**저장소 이중화 (Phase 7):** 1차 Supabase Postgres 원격 적재 → 연결 실패 시 SQLite fallback + 텔레그램 `[DEGRADED]` 알림. 부팅 시 journal 첫 줄 `[init_db] backend=supabase|sqlite` 로 현재 모드 명시 (silent fallback 재발 방지, N22 패치).

**공유 상태 (`BotState`):**

| 필드                        | 설명                            |
| --------------------------- | ------------------------------- |
| `kill_event`                | 킬 스위치 (asyncio.Event)       |
| `target_coin`               | 현재 거래 대상 코인             |
| `daily_pnl`                 | 일일 누적 손익                  |
| `trade_count` / `win_count` | 승률 계산용                     |
| `is_market_healthy`         | 200MA + 연속손실 기반 시장 상태 |

---

## 매매 전략

### 1. 스캐너 엔진 (15분 주기)

바이낸스 전체 종목에서 최적 거래 대상을 자동 탐색합니다.

**5단계 필터링:**

| 단계              | 조건                                                       |
| ----------------- | ---------------------------------------------------------- |
| 사전 필터         | USDT 페어, 스테이블/레버리지 토큰 제외, 가격 $0.10 이상    |
| 유동성 필터       | 24h 거래량 $100M 이상                                      |
| 캔들 수집         | `asyncio.Semaphore(10)` 병렬 요청 (API ban 방지)           |
| 변동성 필터       | ATR(14) / 현재가 = 0.5% ~ 5.0%                             |
| 펌프앤덤프 역필터 | 3h 내 7% 급등, 6h 내 10% 급등, 거래량 5배 스파이크 시 제외 |

**점수 정렬 (상위 1위 선정):**

- ATR 적정성 50% + 거래량 30% + 가격 안정성(CV) 20%

### 2. 그리드 트레이딩 엔진 (GridEngine)

```
가격
 ▲
 │   ─── 매도 5 ────────────────────
 │   ─── 매도 4 ────────────────────
 │   ─── 매도 3 ────────────────────
 │   ─── 매도 2 ────────────────────
 │   ─── 진입가 (50% 즉시 매수) ────
 │   ─── 매수 1 ────────────────────
 │   ─── 매수 2 ────────────────────
 │   ─── 매수 3 ────────────────────
 │   ─── 매수 4 ────────────────────  ← 손절선 (-2%)
 └─────────────────────────────────▶ 시간
```

- 진입 시 시드의 50%를 지정가 즉시 매수
- 5단계 그리드를 0.5% 간격으로 배치
- 그리드 상향 돌파 시 단계적 매도

### 3. 동적 코인 스위칭

기존 보유 코인의 변동성 악화 또는 더 높은 점수의 타겟 발견 시:
→ 기존 포지션 전량 청산 → 새 코인으로 그리드 재설정

---

## 리스크 관리

| 안전망        | 조건                              | 동작                         |
| ------------- | --------------------------------- | ---------------------------- |
| **손절매**    | 진입가 -2%                        | 전량 시장가 매도             |
| **1% Rule**   | 1회 매매 최대 손실                | 시드의 1% 이내로 포지션 제한 |
| **시장 필터** | BTC 200MA 아래 또는 연속 손실 3회 | 신규 진입 차단               |
| **킬 스위치** | 일일 손실 시드 × 3% (90,000원)    | 당일 강제 종료               |

**수익 목표 도달 시:**

- 시드 × 1.0% (30,000원) 달성 → 하드 스탑
- 시드 × 0.5% (15,000원) 달성 + 시장 악화 → 조기 중단

---

## 설치 및 실행

### 사전 조건

- Python 3.10 이상
- 바이낸스 계정 및 API 키
- 텔레그램 봇 토큰 + Chat ID

### 1. 저장소 클론

```bash
git clone https://github.com/luodkrap/Daily_30k_bot.git
cd Daily_30k_bot
```

### 2. 가상환경 설정

```bash
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env` 파일을 생성하고 다음을 입력합니다:

```bash
# 실행 모드 (live 또는 testnet)
MODE=testnet

# 실거래 키 (MODE=live 일 때 사용)
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key

# Testnet 키 (MODE=testnet 일 때 사용)
BINANCE_TESTNET_API_KEY=your_testnet_api_key
BINANCE_TESTNET_SECRET_KEY=your_testnet_secret_key

# 텔레그램
TELEGRAM_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# 시드머니 (원화, 기본값 300만 원)
SEED=3000000
```

> **중요:** `MODE=live` 와 `MODE=testnet` 은 서로 다른 API 키를 사용합니다. 실거래 키와 testnet 키를 혼용하지 마세요.

### 4. 테스트 실행

```bash
python test.py
```

43개 단위·통합 테스트가 전부 통과해야 합니다.

### 5. 봇 실행

```bash
python main.py
```

부팅 시 텔레그램으로 `[MODE=testnet]` 또는 `[MODE=live]` 메시지가 전송됩니다.

---

## 텔레그램 명령어

| 명령어         | 설명                                              |
| -------------- | ------------------------------------------------- |
| `/status`      | 현황 보고 (타겟 코인, 일일 손익, 승률, 시장 상태) |
| `/stop`        | 긴급 정지 (킬 스위치 발동, 포지션 청산)           |
| `/seed <금액>` | 시드머니 변경 — 목표·손실 한도 자동 재계산        |

---

## 파일 구조

```
Daily_30k_bot/
├── main.py          — 진입점 (3개 컴포넌트 asyncio 동시 실행)
├── config.py        — .env 로드, MODE 분기, SEED 기반 수치 자동 계산
├── shared_state.py  — BotState dataclass (킬 이벤트, 손익, 시장 상태 공유)
├── notifier.py      — 텔레그램 비동기 알림 (60s dedup + 1s 스로틀)
├── screener.py      — 스캐너 엔진 (5단계 필터 + 점수 정렬)
├── executor.py      — 트레이딩 엔진 (GridEngine + run_executor + 200MA 필터)
├── persistence.py   — Supabase 1차 / SQLite fallback 체결·이벤트 로그
├── test.py          — 단위·통합 테스트
├── deploy/          — Lightsail 배포 스크립트 (setup.sh, update.sh, daily30k.service, schema.sql)
├── skills/          — 온디맨드 운영 가이드 (auto-checkpoint, conventions, deploy-advisor 등)
├── .env             — 환경변수 (git에 포함되지 않음)
└── requirements.txt — 패키지 목록
```

---

## 주요 설정값

`config.py` 에서 관리되며 `.env`의 `SEED` 값을 기준으로 자동 계산됩니다.

| 설정                   | 기본값       | 설명                                    |
| ---------------------- | ------------ | --------------------------------------- |
| `SEED`                 | 3,000,000원  | 시드머니 (텔레그램 `/seed`로 변경 가능) |
| `DAILY_TARGET`         | SEED × 1.0%  | 하루 목표 수익 (30,000원)               |
| `DAILY_LOSS_LIMIT`     | SEED × 3.0%  | 킬 스위치 손실 한도 (90,000원)          |
| `STOP_LOSS_RATE`       | 2%           | 개별 포지션 손절매 기준                 |
| `MAX_POSITION_RATE`    | 1%           | 1회 매매 최대 손실 비율                 |
| `GRID_COUNT`           | 5            | 그리드 레벨 수                          |
| `GRID_SPACING`         | 0.5%         | 그리드 간격                             |
| `ATR_MIN_RATE`         | 0.5%         | 변동성 하한                             |
| `ATR_MAX_RATE`         | 5.0%         | 변동성 상한                             |
| `SCANNER_INTERVAL_SEC` | 900          | 스캔 주기 (15분)                        |
| `MIN_VOLUME_USD`       | $100,000,000 | 최소 거래량 필터                        |
| `FEE_RATE`             | 0.1%         | 바이낸스 수수료                         |

---

## 개발 현황

| Phase    | 내용                                            | 상태        |
| -------- | ----------------------------------------------- | ----------- |
| Phase 1  | 개발 환경, ccxt 연결, 텔레그램 연동             | 완료        |
| Phase 2  | 프로젝트 구조화, BotState, config 모듈화        | 완료        |
| Phase 3  | 스캐너 엔진 (5단계 필터, 점수 정렬)             | 완료        |
| Phase 4  | 그리드 엔진 (GridEngine, 동적 스위칭)           | 완료        |
| Phase 5  | 리스크 관리 (손절, 킬 스위치, 시장 필터)        | 완료        |
| Phase 6  | 페이퍼 트레이딩 인프라 (MODE 분기, SQLite 로그) | 완료        |
| Phase 6a | testnet 소액 실거래 검증                        | 완료        |
| Phase 7  | Lightsail VPS + systemd + Supabase 원격 적재    | 완료        |
| Phase 7+ | 안전 패치 (N12/N19/N20 hang 방지, N22 가시성)   | 완료        |
| **관찰 모드** | 페이퍼 14일 누적 → R1 점검 → B3 라이브 판단 | **진행 중** (~2026-05-18) |
| Phase 6b | 백테스트 (1~3년 데이터)                         | 미착수      |

---

## 주의사항

**금전적 위험:**

- 이 봇은 실제 자금을 운용합니다. 원금 손실 가능성이 있습니다.
- 반드시 `MODE=testnet` 으로 충분히 검증한 후 `MODE=live` 로 전환하세요.
- 이 프로젝트는 투자 권유가 아닙니다.

**API 키 보안:**

- `.env` 파일을 절대 git에 커밋하지 마세요. (`.gitignore`에 포함되어 있습니다)
- 바이낸스 API 키는 거래 권한만 부여하고 출금 권한은 비활성화하세요.
- IP 화이트리스트 설정을 권장합니다.

**운영 환경:**

- 안정적인 인터넷 연결이 필요합니다. 네트워크 단절 시 미체결 주문이 남을 수 있습니다.
- VPS 또는 24시간 가동 가능한 서버에서 운영하는 것을 권장합니다 (현재 운영 환경: AWS Lightsail + systemd `daily30k.service`, 데이터 적재는 Supabase Postgres).
- Supabase 연결이 끊기면 자동으로 SQLite 로 fallback 되며 텔레그램 `[DEGRADED]` 알림이 발송됩니다. journal 의 `[init_db] backend=...` 줄로 현재 적재 백엔드를 즉시 확인하세요.
