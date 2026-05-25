"""
config.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  .env에서 API 키, SEED 값을 로드하고,
  모든 거래 수치(목표, 손실 한도, 포지션 사이징, 스캐너 파라미터)를
  SEED의 백분율 기반으로 자동 계산하는 중앙 설정 관리자.

특징:
  - SEED 값 변경 시 goal, kill_limit, position_risk 등 전부 자동 연동
  - /seed 텔레그램 커맨드로 런타임 수치 즉시 갱신
  - 고정값(손절매, 1% Rule, 킬 스위치 수치)과 적응형(그리드 간격, ATR) 분리

사용처:
  main.py, executor.py (Phase 4), notifier.py 등 모든 모듈에서 import
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── 실행 모드 ────────────────────────────────────────────
# MODE=live: 바이낸스 실거래. MODE=testnet: testnet.binance.vision 가상 자금.
# MODE=paper: mainnet 실시세를 읽되 주문은 로컬 가상 체결 (paper_exchange.PaperExchange).
#   testnet 의 가격 피드 괴리·얇은 호가·짧은 일봉 결함을 회피하고 실시장에서
#   손실 위험 0 으로 전략을 검증하기 위한 모드 (2026-05-25 추가).
# 실거래 키와 testnet 키는 별도 환경변수로 분리 관리한다 (혼용 방지).
MODE = os.getenv("MODE", "live").lower()
assert MODE in ("live", "testnet", "paper"), \
    f"MODE must be 'live', 'testnet', or 'paper', got {MODE!r}"

# ─── DB 백엔드 (Phase 7) ─────────────────────────────────
# sqlite: 로컬 파일 trades.db. 개발·백테스트·기본값.
# supabase: Supabase Postgres (asyncpg). 운영 서버(Lightsail)에서만 사용.
DB_BACKEND       = os.getenv("DB_BACKEND", "sqlite").lower()
assert DB_BACKEND in ("sqlite", "supabase"), \
    f"DB_BACKEND must be 'sqlite' or 'supabase', got {DB_BACKEND!r}"
SQLITE_DB_PATH   = os.getenv("SQLITE_DB_PATH", "trades.db")
SUPABASE_DB_URL  = os.getenv("SUPABASE_DB_URL")  # postgres://...:6543/postgres?pgbouncer=true

# ─── API 키 ───────────────────────────────────────────────
if MODE == "testnet":
    BINANCE_API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY")
elif MODE == "paper":
    # paper 는 mainnet public 데이터(fetch_ticker/ohlcv/tickers)만 읽고
    # 주문은 로컬 가상 체결하므로 API 키가 필요 없다. 있으면 rate limit 상향에만 사용.
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY") or None
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY") or None
else:
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
# inbound 명령 권한 필터용 정수 변환본 (filters.Chat 은 int 만 받음).
# notifier 의 outbound sendMessage 는 str 도 통과하므로 TELEGRAM_CHAT_ID 는 유지.
try:
    TELEGRAM_CHAT_ID_INT = int(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None
except (TypeError, ValueError):
    TELEGRAM_CHAT_ID_INT = None

# ─── 시드머니 ─────────────────────────────────────────────
# .env의 SEED 값을 읽습니다. 텔레그램 /seed 커맨드로 변경 가능.
SEED = int(os.getenv("SEED", "3000000"))  # 원화 (KRW)

# ─── 수익 중단 로직 ───────────────────────────────────────
DAILY_TARGET     = SEED * 0.010  # 1.0% → 30,000원 (하드 스탑)
DAILY_MIN_PROFIT = SEED * 0.005  # 0.5% → 15,000원 (조기 중단 기준)
DAILY_LOSS_LIMIT = SEED * 0.030  # 3.0% → 90,000원 (킬 스위치)

# ─── 리스크 관리 (고정 — 자동 조정 금지) ─────────────────
MAX_POSITION_RATE = 0.010        # 1% Rule: 한 포지션 최대 시드의 1%
STOP_LOSS_RATE    = 0.020        # 개별 손절매 2%

# ─── 스캐너 파라미터 (params.json으로 자동 조정 대상) ──────
SCANNER_INTERVAL_SEC  = 900     # 스캔 주기 (초) — 15분 (Phase 4: 동적 스위칭 반응성)
# 최소 24h 거래량 — testnet 은 마켓 거래량이 mainnet 의 1/100 수준이라
# $100M 임계값으로는 어떤 코인도 통과 불가. testnet 모드에선 $10M 으로 자동 완화
# (BTC/ETH/DOGE/SOL 등 메이저만 통과되는 안전한 수준).
MIN_VOLUME_USD        = 10_000_000 if MODE == "testnet" else 100_000_000
ATR_MIN_RATE          = 0.005   # ATR 최소 비율 (변동성 하한)
ATR_MAX_RATE          = 0.050   # ATR 최대 비율 (펌프앤덤프 차단 상한)

# ─── 그리드 파라미터 (params.json으로 자동 조정 대상) ──────
GRID_COUNT     = 5              # 그리드 레벨 수
GRID_SPACING   = 0.005          # 그리드 간격 비율 (0.5%)

# ─── 스캐너 세부 파라미터 ────────────────────────────────
MIN_PRICE_USD         = 0.10    # 최소 코인 가격 $0.10 (저가 코인 그리드 매매 부적합)
SCANNER_SEMAPHORE     = 10      # 병렬 캔들 조회 동시 요청 수
SCANNER_CANDLE_LIMIT  = 30      # ATR14 계산용 캔들 수 (Wilder's Smoothing 워밍업 포함)
SCANNER_TOP_N         = 5       # 최종 후보 상위 N개
PUMP_THRESHOLD_3H     = 0.07    # 3시간 내 급등 기준 7%
PUMP_THRESHOLD_6H     = 0.10    # 6시간 내 급등 기준 10%
PUMP_VOLUME_SPIKE     = 5.0     # 거래량 스파이크 배수 기준

# ─── 시장 악화 감지 ──────────────────────────────────────
MARKET_FILTER_MA      = 200     # BTC 200MA 기준
RECENT_LOSS_STREAK    = 3       # 연속 손실 n회 시 경고

# ─── 거래 비용 및 초기 매수 ──────────────────────────
FEE_RATE          = 0.001     # 바이낸스 현물 수수료 0.1%
INITIAL_BUY_RATIO = 0.50      # 투입금 중 지정가 즉시 매수 비율 50%
MIN_PROFIT_RATIO  = 0.001     # 최소 순수익 기준 0.1% (수수료 제외 후)
REGRID_ENABLED    = True      # 상단 이탈 시 리그리딩 ON/OFF
KRW_RATE          = 1350      # 원/달러 환율 기본값 (실시간 갱신 대상)

# ─── Paper 모드 (MODE=paper) ─────────────────────────────
# 가상 거래소 상태(잔고·미체결 주문) 영속화 경로 + 시장가 슬리피지 모델.
PAPER_STATE_PATH  = os.getenv("PAPER_STATE_PATH", "paper_state.json")
PAPER_SLIPPAGE    = float(os.getenv("PAPER_SLIPPAGE", "0.0005"))  # 시장가 체결 슬리피지 0.05%
