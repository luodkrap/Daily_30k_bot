"""
paper_exchange.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
  MODE=paper 전용 거래소 객체. mainnet 실시세·실호가·실캔들을 읽되(read 위임),
  주문만 거래소로 보내지 않고 로컬에서 가상 체결하는 PaperExchange.

설계 (2026-05-25 결정):
  - testnet.binance.vision 의 가격 피드 괴리·얇은 호가·짧은 일봉 결함을 회피하고
    진짜 시장에서 손실 위험 0 으로 전략을 검증하기 위한 모드.
  - executor / screener / GridEngine 코드는 한 줄도 바꾸지 않는다.
    ccxt.binance 인터페이스를 덕 타이핑으로 흉내내어 거래소 객체만 교체한다.
  - 가상 상태(잔고·미체결 주문)는 JSON(config.PAPER_STATE_PATH) 에 영속화 →
    재시작/배포/watchdog 후에도 복원 (며칠~2주 누적 검증이 목적).

체결 모델 (MVP):
  - 지정가(limit): 현재가가 지정가에 닿으면 즉시 전량 체결 (부분체결 없음).
      buy  → 현재가 <= 지정가, sell → 현재가 >= 지정가
  - 시장가(market): 현재가 ± config.PAPER_SLIPPAGE 로 즉시 체결.
  - 수수료(config.FEE_RATE)는 USDT 측에서 양방향 차감 → 코인 수량은 명목 그대로
    유지되어 그리드 매도 수량 일관성 보장.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json
import os
import sys
import time

import config


class PaperExchange:
    """mainnet 실시세 + 로컬 가상 체결. ccxt.binance 인터페이스 덕 타이핑."""

    def __init__(self, reader, state_path: str | None = None):
        # reader: 실제 ccxt.async_support.binance 인스턴스 (mainnet, sandbox 아님).
        #         읽기 전용(fetch_ticker/ohlcv/tickers/load_markets/precision) 위임 대상.
        self._reader = reader
        self._state_path = state_path or config.PAPER_STATE_PATH

        # 가상 상태
        self.balance: dict[str, float] = {}   # {currency: 보유 총량}
        self.open_orders: dict[str, dict] = {}  # {id: {symbol, side, type, qty, price, filled, status, ts}}
        self._next_id: int = 1

    # ── 읽기 메서드 (실제 거래소 위임) ───────────────────
    @property
    def markets(self):
        return getattr(self._reader, "markets", None)

    @property
    def urls(self):
        return getattr(self._reader, "urls", {})

    async def load_markets(self, *args, **kwargs):
        return await self._reader.load_markets(*args, **kwargs)

    def amount_to_precision(self, symbol, amount):
        return self._reader.amount_to_precision(symbol, amount)

    def price_to_precision(self, symbol, price):
        return self._reader.price_to_precision(symbol, price)

    async def fetch_ticker(self, symbol, *args, **kwargs):
        return await self._reader.fetch_ticker(symbol, *args, **kwargs)

    async def fetch_tickers(self, *args, **kwargs):
        return await self._reader.fetch_tickers(*args, **kwargs)

    async def fetch_ohlcv(self, *args, **kwargs):
        return await self._reader.fetch_ohlcv(*args, **kwargs)

    async def close(self):
        return await self._reader.close()

    # ── 현재가 헬퍼 ──────────────────────────────────────
    async def _last_price(self, symbol: str) -> float:
        ticker = await self._reader.fetch_ticker(symbol)
        return float(ticker["last"])

    # ── 잔고 (가상) ──────────────────────────────────────
    def _locked(self) -> dict[str, float]:
        """미체결 limit 주문에 잠긴 수량 — buy:USDT, sell:coin."""
        used: dict[str, float] = {}
        for o in self.open_orders.values():
            if o["status"] != "open" or o["type"] != "limit":
                continue
            base = o["symbol"].split("/")[0]
            if o["side"] == "buy":
                used["USDT"] = used.get("USDT", 0.0) + o["qty"] * o["price"]
            else:
                used[base] = used.get(base, 0.0) + o["qty"]
        return used

    async def fetch_balance(self, *args, **kwargs) -> dict:
        used = self._locked()
        total = {c: a for c, a in self.balance.items() if a}
        free = {c: max(0.0, a - used.get(c, 0.0)) for c, a in total.items()}
        result: dict = {"free": dict(free), "used": dict(used), "total": dict(total)}
        for c in total:
            result[c] = {
                "free": free.get(c, 0.0),
                "used": used.get(c, 0.0),
                "total": total[c],
            }
        # USDT 키는 항상 존재시켜 setup_grid 의 balance["USDT"]["free"] 안전 보장
        if "USDT" not in result:
            result["USDT"] = {"free": 0.0, "used": 0.0, "total": 0.0}
        return result

    # ── 주문 (가상 체결) ─────────────────────────────────
    async def create_order(self, symbol, type, side, amount, price=None,
                           params=None):
        amount = float(amount)
        otype = str(type).lower()
        oside = str(side).lower()
        oid = str(self._next_id)
        self._next_id += 1

        order = {
            "id": oid, "symbol": symbol, "type": otype, "side": oside,
            "qty": amount, "amount": amount, "price": price,
            "filled": 0.0, "average": None, "status": "open",
            "ts": time.time(),
        }
        self.open_orders[oid] = order

        if otype == "market":
            last = await self._last_price(symbol)
            slip = config.PAPER_SLIPPAGE
            fill_price = last * (1 + slip) if oside == "buy" else last * (1 - slip)
            self._fill(order, fill_price)
        else:
            last = await self._last_price(symbol)
            self._match_one(order, last)

        self._save_state()
        return self._as_ccxt(order)

    async def fetch_order(self, order_id, symbol=None, params=None):
        order = self.open_orders.get(str(order_id))
        if order is None:
            # 이미 처리되어 사라진 주문 — closed 로 간주 (executor 는 filled 로 분기)
            return {"id": str(order_id), "symbol": symbol, "status": "closed",
                    "filled": 0.0, "average": None}
        if order["status"] == "open" and order["type"] == "limit":
            last = await self._last_price(order["symbol"])
            self._match_one(order, last)
            self._save_state()
        return self._as_ccxt(order)

    async def fetch_open_orders(self, symbol=None, *args, **kwargs) -> list:
        await self._match_all(symbol)
        out = []
        for o in self.open_orders.values():
            if o["status"] != "open":
                continue
            if symbol and o["symbol"] != symbol:
                continue
            out.append(self._as_ccxt(o))
        return out

    async def cancel_order(self, order_id, symbol=None, params=None):
        order = self.open_orders.get(str(order_id))
        if order and order["status"] == "open":
            order["status"] = "canceled"
            self._save_state()
        return self._as_ccxt(order) if order else {"id": str(order_id),
                                                   "status": "canceled"}

    # ── 체결 엔진 ────────────────────────────────────────
    async def _match_all(self, symbol: str | None) -> None:
        # symbol 별 1회만 현재가 조회 (rate limit 절약)
        symbols = {o["symbol"] for o in self.open_orders.values()
                   if o["status"] == "open" and o["type"] == "limit"
                   and (not symbol or o["symbol"] == symbol)}
        for sym in symbols:
            last = await self._last_price(sym)
            for o in list(self.open_orders.values()):
                if (o["status"] == "open" and o["type"] == "limit"
                        and o["symbol"] == sym):
                    self._match_one(o, last)
        if symbols:
            self._save_state()

    def _match_one(self, order: dict, last_price: float) -> None:
        """지정가 체결 판정. buy: 현재가<=지정가 / sell: 현재가>=지정가."""
        if order["status"] != "open" or order["type"] != "limit":
            return
        hit = (order["side"] == "buy" and last_price <= order["price"]) or \
              (order["side"] == "sell" and last_price >= order["price"])
        if hit:
            self._fill(order, order["price"])

    def _fill(self, order: dict, fill_price: float) -> None:
        """가상 잔고 이동 + 주문 closed 마킹. 수수료는 USDT 측 양방향 차감."""
        base = order["symbol"].split("/")[0]
        qty = order["qty"]
        fee = fill_price * qty * config.FEE_RATE
        if order["side"] == "buy":
            self.balance["USDT"] = self.balance.get("USDT", 0.0) - qty * fill_price - fee
            self.balance[base] = self.balance.get(base, 0.0) + qty
        else:
            self.balance[base] = self.balance.get(base, 0.0) - qty
            self.balance["USDT"] = self.balance.get("USDT", 0.0) + qty * fill_price - fee
        order["filled"] = qty
        order["average"] = fill_price
        order["status"] = "closed"

    # ── ccxt order dict 변환 ─────────────────────────────
    @staticmethod
    def _as_ccxt(order: dict) -> dict:
        return {
            "id": order["id"], "symbol": order["symbol"],
            "type": order["type"], "side": order["side"],
            "amount": order["qty"], "price": order["price"],
            "filled": order["filled"], "average": order["average"],
            "status": order["status"],
        }

    # ── 영속화 ───────────────────────────────────────────
    def _save_state(self) -> None:
        try:
            tmp = self._state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({
                    "balance": self.balance,
                    "open_orders": self.open_orders,
                    "next_id": self._next_id,
                }, f)
            os.replace(tmp, self._state_path)  # 원자적 교체 (부분 쓰기 방지)
        except Exception as e:
            print(f"[paper] state save 실패: {e}", file=sys.stderr, flush=True)

    def load_state(self) -> None:
        """부팅 시 호출. 파일 있으면 복원, 없으면 SEED 환산 USDT 초기 시드."""
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path) as f:
                    data = json.load(f)
                self.balance = {k: float(v) for k, v in data.get("balance", {}).items()}
                self.open_orders = data.get("open_orders", {})
                self._next_id = int(data.get("next_id", 1))
                print(f"[paper] state 복원: USDT={self.balance.get('USDT', 0):,.2f} "
                      f"open_orders={len([o for o in self.open_orders.values() if o['status']=='open'])}",
                      flush=True)
                return
            except Exception as e:
                print(f"[paper] state 복원 실패 — 초기 시드로 시작: {e}",
                      file=sys.stderr, flush=True)
        # 초기 시드: SEED(원) → USDT 환산. calc_position_size 가 이 USDT free 를 사용.
        seed_usdt = config.SEED / config.KRW_RATE
        self.balance = {"USDT": seed_usdt}
        self.open_orders = {}
        self._next_id = 1
        print(f"[paper] 초기 시드 USDT={seed_usdt:,.2f} (SEED={config.SEED:,}원)",
              flush=True)
