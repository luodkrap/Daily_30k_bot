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
# 실거래 키와 testnet 키는 별도 환경변수로 분리 관리한다 (혼용 방지).
MODE = os.getenv("MODE", "live").lower()
assert MODE in ("live", "testnet"), f"MODE must be 'live' or 'testnet', got {MODE!r}"

# ─── API 키 ───────────────────────────────────────────────
if MODE == "testnet":
    BINANCE_API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY")
else:
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

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
MIN_VOLUME_USD        = 100_000_000  # 최소 24h 거래량 $100M
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
