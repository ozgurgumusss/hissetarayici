import asyncio
import io
import json
import logging
import math
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
import plotly.graph_objects as go
# =====================================================================
# TA-LIB YERİNE SUNUCUDA ÇALIŞAN UYUMLULUK KÖPRÜSÜ
# =====================================================================
import ta as ta_lib
import pandas as pd
import numpy as np

class SahteTalib:
    @staticmethod
    def RSI(close_prices, timeperiod=14):
        return ta_lib.momentum.rsi(pd.Series(close_prices), window=timeperiod).to_numpy()
        
    @staticmethod
    def SMA(close_prices, timeperiod=30):
        return ta_lib.trend.sma_indicator(pd.Series(close_prices), window=timeperiod).to_numpy()
        
    @staticmethod
    def EMA(close_prices, timeperiod=30):
        return ta_lib.trend.ema_indicator(pd.Series(close_prices), window=timeperiod).to_numpy()

# Koddaki 'talib' çağrılarını bu sahte sınıfa yönlendiriyoruz
talib = SahteTalib()
# =====================================================================
# =====================================================================
# EMERGENTINTEGRATIONS HATASINI BİTİREN KÖKTEN ÇÖZÜM
# =====================================================================
import sys
from types import ModuleType

# Sahte ana modül
mock_emergent = ModuleType("emergentintegrations")
sys.modules["emergentintegrations"] = mock_emergent

# Kodda alt kırılımlar çağrıldıysa patlamasın diye sahte alt modüller
sys.modules["emergentintegrations.knowledge"] = ModuleType("knowledge")
sys.modules["emergentintegrations.prompts"] = ModuleType("prompts")
sys.modules["emergentintegrations.tools"] = ModuleType("tools")
# =====================================================================
import yfinance as yf
# Eski hatalı satırı sil, yerine bunu yapıştır:
yf.set_tz_cache_location(None)
from yfinance import EquityQuery
from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from pymongo import UpdateOne
from scipy.signal import argrelextrema
from starlette.middleware.cors import CORSMiddleware


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
db_name = os.environ["DB_NAME"]
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]
signals_collection = db.signals
fundamentals_collection = db.fundamentals_cache

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
SCAN_INTERVAL_SECONDS = 300

app = FastAPI(title="Algo Signal & Explanation Platform")
api_router = APIRouter(prefix="/api")

STATIC_ROOT = ROOT_DIR / "static"
PATTERN_STATIC_DIR = STATIC_ROOT / "patterns"
PATTERN_STATIC_DIR.mkdir(parents=True, exist_ok=True)
PATTERN_IMAGE_ROUTE_PREFIX = "/api/static/patterns"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("algo-signal-platform")


US_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK-B", "JPM",
    "V", "MA", "LLY", "AVGO", "XOM", "UNH", "JNJ", "WMT", "PG", "HD", "COST", "BAC",
    "ABBV", "KO", "PEP", "MRK", "ORCL", "ADBE", "CRM", "NFLX", "AMD", "CVX", "TMO",
    "ACN", "MCD", "CSCO", "INTU", "LIN", "ABT", "QCOM", "DIS", "DHR", "VZ", "TXN",
    "AMAT", "PFE", "CMCSA", "NKE", "PM", "UNP", "MS", "HON", "IBM", "INTC", "RTX",
    "SPGI", "GS", "CAT", "NOW", "GE", "BKNG", "BLK", "PLD", "ISRG", "AMGN", "SYK",
    "SCHW", "AXP", "COP", "LMT", "SBUX", "DE", "MDT", "ELV", "ADI", "GILD", "MO",
    "TJX", "MMM", "LOW", "C", "PYPL", "T", "VRTX", "REGN", "UPS", "BA", "F", "GM",
    "MU", "PANW", "SNOW", "SHOP", "UBER", "SQ", "COIN", "ROKU", "SOFI", "BABA", "NIO"
]

BIST_SYMBOLS = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKFGY", "AKFYE", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALFAS", "ARCLK", "ASELS", "ASTOR", "AVPGY", "BERA", "BIMAS", "BIOEN", "BOBET", "BRSAN",
    "BUCIM", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "ECZYT", "EGEEN", "ENJSA",
    "ENKAI", "EREGL", "EUPWR", "FROTO", "GARAN", "GESAN", "GLYHO", "GOKNR", "GUBRF", "GWIND",
    "HALKB", "HEKTS", "ISCTR", "ISMEN", "KARSN", "KAYSE", "KCAER", "KCHOL", "KLSER", "KONTR",
    "KOZAA", "KOZAL", "KRDMD", "MAVI", "MGROS", "MIATK", "MPARK", "ODAS", "OTKAR", "OYAKC",
    "PETKM", "PGSUS", "QUAGR", "REEDR", "SAHOL", "SASA", "SISE", "SKBNK", "SMRTG", "SOKM",
    "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM", "TTRAK", "TUKAS",
    "TUPRS", "ULKER", "VAKBN", "VESBE", "VESTL", "YEOTK", "YKBNK", "ZOREN", "AKENR", "ARASE",
    "BNTAS", "CANTE", "KONYA", "SELEC", "TATEN", "YUNSA", "ANHYT", "AKCNS", "ISGYO", "PENTA"
]

MARKET_UNIVERSE = {
    "US": list(dict.fromkeys(US_SYMBOLS))[:100],
    "BIST": [f"{symbol}.IS" for symbol in list(dict.fromkeys(BIST_SYMBOLS))[:100]],
}

DEFAULT_MARKET_UNIVERSE = {
    "US": MARKET_UNIVERSE["US"],
    "BIST": MARKET_UNIVERSE["BIST"],
}

TARGET_UNIVERSE_SIZE = 500
UNIVERSE_CACHE_TTL_SECONDS = 4 * 60 * 60

universe_cache: dict[str, Any] = {
    "US": DEFAULT_MARKET_UNIVERSE["US"],
    "BIST": DEFAULT_MARKET_UNIVERSE["BIST"],
    "updated_at": None,
}

SECTOR_PE_BENCHMARK = {
    "Technology": 28,
    "Financial Services": 14,
    "Healthcare": 22,
    "Consumer Defensive": 20,
    "Consumer Cyclical": 24,
    "Industrials": 21,
    "Energy": 12,
    "Basic Materials": 18,
    "Real Estate": 16,
    "Communication Services": 22,
    "Utilities": 17,
}


class PatternMatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    direction: str
    confirmed: bool
    neckline: float | None = None
    points: list[str] = Field(default_factory=list)
    volume_validated: bool = False
    detail: str
    geometry: dict[str, Any] = Field(default_factory=dict)


class IndicatorsSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ema20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    atr14: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    stochastic_k: float | None = None
    stochastic_d: float | None = None
    adx14: float | None = None
    ichimoku_tenkan: float | None = None
    ichimoku_kijun: float | None = None
    ichimoku_span_a: float | None = None
    ichimoku_span_b: float | None = None
    golden_cross: bool = False
    death_cross: bool = False
    bearish_divergence: bool = False
    volume_confirmation: bool = False


class FundamentalSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pe: float | None = None
    pb: float | None = None
    market_cap: float | None = None
    sector: str = "Unknown"
    sector_pe_avg: float = 22.0
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    eps_growth_qoq: float | None = None
    roe: float | None = None
    net_profit_margin: float | None = None
    dividend_yield: float | None = None
    score: int = 0
    hard_cap_trigger: bool = False
    notes: list[str] = Field(default_factory=list)


class RiskLevels(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entry_price: float
    atr: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    risk_reward: str | None = None


class PricePoint(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float
    ema20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None


class SignalRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    market: str
    action: str
    bullish_score: int
    score_breakdown: dict[str, int]
    last_price: float
    patterns: list[PatternMatch]
    indicators: IndicatorsSnapshot
    fundamental: FundamentalSnapshot
    risk: RiskLevels
    volume_analysis: dict[str, Any] = Field(default_factory=dict)
    ai_summary: str | None = None
    pattern_image_url: str | None = None
    pattern_image_updated_at: str | None = None
    updated_at: str
    price_history: list[PricePoint]


class ScannerState(BaseModel):
    running: bool
    last_run: str | None = None
    last_error: str | None = None
    last_duration_seconds: float | None = None
    last_scanned_count: int = 0


class ExportFilterRequest(BaseModel):
    markets: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


scan_state = ScannerState(running=False)
scanner_task: asyncio.Task | None = None
scan_lock = asyncio.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value) -> float | None:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def to_round(value, digits: int = 4) -> float | None:
    casted = to_float(value)
    return None if casted is None else round(casted, digits)


def sanitize_for_json(value):
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {key: sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(item) for item in value]
    return value


def fetch_top_symbols_from_screener(exchange_codes: list[str], limit: int) -> list[str]:
    if not exchange_codes:
        return []

    if len(exchange_codes) == 1:
        query = EquityQuery("eq", ["exchange", exchange_codes[0]])
    else:
        query = EquityQuery("is-in", ["exchange", *exchange_codes])

    collected: list[str] = []
    seen: set[str] = set()
    offset = 0

    while len(collected) < limit:
        batch_size = min(250, limit - len(collected))
        response = yf.screen(
            query,
            offset=offset,
            size=batch_size,
            sortField="intradaymarketcap",
            sortAsc=False,
        )
        quotes = response.get("quotes") or []
        if not quotes:
            break

        for quote in quotes:
            symbol = str(quote.get("symbol") or "").upper().strip()
            if not symbol or symbol in seen:
                continue
            quote_type = str(quote.get("quoteType") or "").upper()
            if quote_type and quote_type != "EQUITY":
                continue
            if symbol.startswith("^") or symbol.endswith("W"):
                continue
            seen.add(symbol)
            collected.append(symbol)
            if len(collected) >= limit:
                break

        offset += len(quotes)
        if len(quotes) < batch_size:
            break

    return collected[:limit]


async def get_market_universe(force_refresh: bool = False) -> dict[str, list[str]]:
    updated_at = universe_cache.get("updated_at")
    cache_fresh = False
    if isinstance(updated_at, datetime):
        cache_fresh = (datetime.now(timezone.utc) - updated_at).total_seconds() < UNIVERSE_CACHE_TTL_SECONDS

    if cache_fresh and not force_refresh:
        return {
            "US": universe_cache.get("US", DEFAULT_MARKET_UNIVERSE["US"]),
            "BIST": universe_cache.get("BIST", DEFAULT_MARKET_UNIVERSE["BIST"]),
        }

    try:
        us_symbols, bist_symbols = await asyncio.gather(
            asyncio.to_thread(fetch_top_symbols_from_screener, ["NMS", "NGM", "NCM"], TARGET_UNIVERSE_SIZE),
            asyncio.to_thread(fetch_top_symbols_from_screener, ["IST"], TARGET_UNIVERSE_SIZE),
        )

        if us_symbols:
            universe_cache["US"] = us_symbols
        if bist_symbols:
            universe_cache["BIST"] = [symbol if symbol.endswith(".IS") else f"{symbol}.IS" for symbol in bist_symbols]
        universe_cache["updated_at"] = datetime.now(timezone.utc)
    except Exception as exc:
        logger.warning("Dinamik evren alınamadı, fallback liste kullanılacak: %s", exc)

    return {
        "US": universe_cache.get("US", DEFAULT_MARKET_UNIVERSE["US"]),
        "BIST": universe_cache.get("BIST", DEFAULT_MARKET_UNIVERSE["BIST"]),
    }


def detect_local_extrema(series: pd.Series, order: int = 4) -> tuple[list[int], list[int]]:
    values = series.to_numpy(dtype=float)
    if len(values) < order * 2 + 5:
        return [], []
    local_high = argrelextrema(values, np.greater, order=order)[0].tolist()
    local_low = argrelextrema(values, np.less, order=order)[0].tolist()
    return local_high, local_low


def find_breakout_index(
    close_series: pd.Series,
    start_idx: int,
    threshold_func,
    breakout_direction: str,
) -> int | None:
    for idx in range(start_idx, len(close_series)):
        close_value = float(close_series.iloc[idx])
        threshold = float(threshold_func(idx))
        if breakout_direction == "above" and close_value > threshold:
            return idx
        if breakout_direction == "below" and close_value < threshold:
            return idx
    return None


def line_value(start_idx: int, start_price: float, end_idx: int, end_price: float, query_idx: int) -> float:
    if end_idx == start_idx:
        return float(start_price)
    slope = (end_price - start_price) / (end_idx - start_idx)
    return start_price + slope * (query_idx - start_idx)


def detect_double_top_bottom(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 60)
    close_series = df["Close"]
    volume_series = df["Volume"]
    latest_close = float(close_series.iloc[-1])
    volume_avg_20 = float(volume_series.tail(20).mean())

    recent_highs = [idx for idx in highs if idx >= lookback_start]
    if len(recent_highs) >= 2:
        for i in range(len(recent_highs) - 1, 0, -1):
            left_idx, right_idx = recent_highs[i - 1], recent_highs[i]
            if right_idx - left_idx < 4:
                continue
            left_peak = float(close_series.iloc[left_idx])
            right_peak = float(close_series.iloc[right_idx])
            avg_peak = max((left_peak + right_peak) / 2, 1e-9)
            if abs(left_peak - right_peak) / avg_peak <= 0.02:
                neckline = float(close_series.iloc[left_idx : right_idx + 1].min())
                breakout_idx = find_breakout_index(close_series, right_idx, lambda _: neckline, "below")
                breakout_volume_valid = bool(
                    breakout_idx is not None and float(volume_series.iloc[breakout_idx]) > volume_avg_20
                )
                confirmed = latest_close < neckline and breakout_idx is not None and breakout_volume_valid
                target_price = neckline - (max(left_peak, right_peak) - neckline)
                patterns.append(
                    {
                        "name": "Double Top",
                        "direction": "bearish",
                        "confirmed": confirmed,
                        "neckline": round(neckline, 4),
                        "points": [
                            df.index[left_idx].strftime("%Y-%m-%d"),
                            df.index[right_idx].strftime("%Y-%m-%d"),
                        ],
                        "volume_validated": breakout_volume_valid,
                        "detail": "Son 60 periyotta iki tepe %2 toleransla eşleşti, neckline kapanışla test edildi.",
                        "geometry": {
                            "left_index": left_idx,
                            "right_index": right_idx,
                            "left_price": round(left_peak, 4),
                            "right_price": round(right_peak, 4),
                            "neckline_start_index": left_idx,
                            "neckline_end_index": right_idx,
                            "neckline_start_price": round(neckline, 4),
                            "neckline_end_price": round(neckline, 4),
                            "breakout_index": breakout_idx,
                            "target_price": round(target_price, 4),
                        },
                    }
                )
                break

    recent_lows = [idx for idx in lows if idx >= lookback_start]
    if len(recent_lows) >= 2:
        for i in range(len(recent_lows) - 1, 0, -1):
            left_idx, right_idx = recent_lows[i - 1], recent_lows[i]
            if right_idx - left_idx < 4:
                continue
            left_bottom = float(close_series.iloc[left_idx])
            right_bottom = float(close_series.iloc[right_idx])
            avg_bottom = max((left_bottom + right_bottom) / 2, 1e-9)
            if abs(left_bottom - right_bottom) / avg_bottom <= 0.02:
                neckline = float(close_series.iloc[left_idx : right_idx + 1].max())
                breakout_idx = find_breakout_index(close_series, right_idx, lambda _: neckline, "above")
                breakout_volume_valid = bool(
                    breakout_idx is not None and float(volume_series.iloc[breakout_idx]) > volume_avg_20
                )
                confirmed = latest_close > neckline and breakout_idx is not None and breakout_volume_valid
                target_price = neckline + (neckline - min(left_bottom, right_bottom))
                patterns.append(
                    {
                        "name": "Double Bottom",
                        "direction": "bullish",
                        "confirmed": confirmed,
                        "neckline": round(neckline, 4),
                        "points": [
                            df.index[left_idx].strftime("%Y-%m-%d"),
                            df.index[right_idx].strftime("%Y-%m-%d"),
                        ],
                        "volume_validated": breakout_volume_valid,
                        "detail": "Son 60 periyotta iki dip %2 toleransla eşleşti, neckline kapanışla yukarı kırıldı.",
                        "geometry": {
                            "left_index": left_idx,
                            "right_index": right_idx,
                            "left_price": round(left_bottom, 4),
                            "right_price": round(right_bottom, 4),
                            "neckline_start_index": left_idx,
                            "neckline_end_index": right_idx,
                            "neckline_start_price": round(neckline, 4),
                            "neckline_end_price": round(neckline, 4),
                            "breakout_index": breakout_idx,
                            "target_price": round(target_price, 4),
                        },
                    }
                )
                break

    return patterns


def detect_head_shoulders(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 120)
    close_series = df["Close"]
    volume_series = df["Volume"]
    volume_avg_20 = float(volume_series.tail(20).mean())

    recent_highs = [idx for idx in highs if idx >= lookback_start]
    for i in range(len(recent_highs) - 2):
        left, head, right = recent_highs[i], recent_highs[i + 1], recent_highs[i + 2]
        left_val = float(close_series.iloc[left])
        head_val = float(close_series.iloc[head])
        right_val = float(close_series.iloc[right])

        shoulders_balanced = abs(left_val - right_val) / max(left_val, right_val, 1e-9) <= 0.03
        head_valid = head_val >= max(left_val, right_val) * 1.03
        if not (shoulders_balanced and head_valid):
            continue

        left_trough_segment = close_series.iloc[left : head + 1]
        right_trough_segment = close_series.iloc[head : right + 1]
        left_trough_rel = int(np.argmin(left_trough_segment.to_numpy()))
        right_trough_rel = int(np.argmin(right_trough_segment.to_numpy()))
        left_trough_idx = left + left_trough_rel
        right_trough_idx = head + right_trough_rel
        left_trough = float(close_series.iloc[left_trough_idx])
        right_trough = float(close_series.iloc[right_trough_idx])

        left_volume = float(volume_series.iloc[max(left - 3, 0):left + 1].mean())
        right_volume = float(volume_series.iloc[max(right - 3, 0):right + 1].mean())
        breakout_idx = find_breakout_index(
            close_series,
            right,
            lambda idx: line_value(left_trough_idx, left_trough, right_trough_idx, right_trough, idx),
            "below",
        )
        breakout_volume = float(volume_series.iloc[breakout_idx]) if breakout_idx is not None else 0.0
        volume_validated = right_volume < left_volume and breakout_volume > volume_avg_20
        neckline_latest = line_value(left_trough_idx, left_trough, right_trough_idx, right_trough, len(close_series) - 1)
        confirmed = float(close_series.iloc[-1]) < neckline_latest and breakout_idx is not None and volume_validated
        target_height = head_val - min(left_trough, right_trough)
        target_price = neckline_latest - target_height

        patterns.append(
            {
                "name": "Head and Shoulders",
                "direction": "bearish",
                "confirmed": confirmed,
                "neckline": round(neckline_latest, 4),
                "points": [
                    df.index[left].strftime("%Y-%m-%d"),
                    df.index[head].strftime("%Y-%m-%d"),
                    df.index[right].strftime("%Y-%m-%d"),
                ],
                "volume_validated": volume_validated,
                "detail": "Baş noktası omuzlardan %3+ yüksek; sağ omuz hacim düşüşü ve neckline kırılımında hacim artışı kontrol edildi.",
                "geometry": {
                    "left_index": left,
                    "head_index": head,
                    "right_index": right,
                    "left_price": round(left_val, 4),
                    "head_price": round(head_val, 4),
                    "right_price": round(right_val, 4),
                    "neckline_start_index": left_trough_idx,
                    "neckline_end_index": right_trough_idx,
                    "neckline_start_price": round(left_trough, 4),
                    "neckline_end_price": round(right_trough, 4),
                    "breakout_index": breakout_idx,
                    "target_price": round(target_price, 4),
                },
            }
        )
        break

    recent_lows = [idx for idx in lows if idx >= lookback_start]
    for i in range(len(recent_lows) - 2):
        left, head, right = recent_lows[i], recent_lows[i + 1], recent_lows[i + 2]
        left_val = float(close_series.iloc[left])
        head_val = float(close_series.iloc[head])
        right_val = float(close_series.iloc[right])

        shoulders_balanced = abs(left_val - right_val) / max(left_val, right_val, 1e-9) <= 0.03
        head_valid = head_val <= min(left_val, right_val) * 0.97
        if not (shoulders_balanced and head_valid):
            continue

        left_peak_segment = close_series.iloc[left : head + 1]
        right_peak_segment = close_series.iloc[head : right + 1]
        left_peak_rel = int(np.argmax(left_peak_segment.to_numpy()))
        right_peak_rel = int(np.argmax(right_peak_segment.to_numpy()))
        left_peak_idx = left + left_peak_rel
        right_peak_idx = head + right_peak_rel
        left_peak = float(close_series.iloc[left_peak_idx])
        right_peak = float(close_series.iloc[right_peak_idx])

        left_volume = float(volume_series.iloc[max(left - 3, 0):left + 1].mean())
        right_volume = float(volume_series.iloc[max(right - 3, 0):right + 1].mean())
        breakout_idx = find_breakout_index(
            close_series,
            right,
            lambda idx: line_value(left_peak_idx, left_peak, right_peak_idx, right_peak, idx),
            "above",
        )
        breakout_volume = float(volume_series.iloc[breakout_idx]) if breakout_idx is not None else 0.0
        volume_validated = right_volume < left_volume and breakout_volume > volume_avg_20
        neckline_latest = line_value(left_peak_idx, left_peak, right_peak_idx, right_peak, len(close_series) - 1)
        confirmed = float(close_series.iloc[-1]) > neckline_latest and breakout_idx is not None and volume_validated
        target_height = max(left_peak, right_peak) - head_val
        target_price = neckline_latest + target_height

        patterns.append(
            {
                "name": "Inverse Head and Shoulders",
                "direction": "bullish",
                "confirmed": confirmed,
                "neckline": round(neckline_latest, 4),
                "points": [
                    df.index[left].strftime("%Y-%m-%d"),
                    df.index[head].strftime("%Y-%m-%d"),
                    df.index[right].strftime("%Y-%m-%d"),
                ],
                "volume_validated": volume_validated,
                "detail": "Ters OBO algılandı; sağ omuz hacmi düşük ve neckline kırılımında hacim artışı doğrulandı.",
                "geometry": {
                    "left_index": left,
                    "head_index": head,
                    "right_index": right,
                    "left_price": round(left_val, 4),
                    "head_price": round(head_val, 4),
                    "right_price": round(right_val, 4),
                    "neckline_start_index": left_peak_idx,
                    "neckline_end_index": right_peak_idx,
                    "neckline_start_price": round(left_peak, 4),
                    "neckline_end_price": round(right_peak, 4),
                    "breakout_index": breakout_idx,
                    "target_price": round(target_price, 4),
                },
            }
        )
        break

    return patterns


def detect_symmetrical_triangle(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 90)
    close_series = df["Close"]
    volume_series = df["Volume"]
    volume_avg_20 = float(volume_series.tail(20).mean())

    recent_highs = [idx for idx in highs if idx >= lookback_start]
    recent_lows = [idx for idx in lows if idx >= lookback_start]
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return patterns

    upper_start_idx, upper_end_idx = recent_highs[-2], recent_highs[-1]
    lower_start_idx, lower_end_idx = recent_lows[-2], recent_lows[-1]

    if upper_end_idx <= upper_start_idx or lower_end_idx <= lower_start_idx:
        return patterns

    upper_start_price = float(close_series.iloc[upper_start_idx])
    upper_end_price = float(close_series.iloc[upper_end_idx])
    lower_start_price = float(close_series.iloc[lower_start_idx])
    lower_end_price = float(close_series.iloc[lower_end_idx])

    upper_slope = (upper_end_price - upper_start_price) / (upper_end_idx - upper_start_idx)
    lower_slope = (lower_end_price - lower_start_price) / (lower_end_idx - lower_start_idx)
    if not (upper_slope < 0 and lower_slope > 0):
        return patterns

    start_idx = max(upper_start_idx, lower_start_idx)
    end_idx = len(df) - 1
    upper_start_eval = line_value(upper_start_idx, upper_start_price, upper_end_idx, upper_end_price, start_idx)
    lower_start_eval = line_value(lower_start_idx, lower_start_price, lower_end_idx, lower_end_price, start_idx)
    upper_latest_eval = line_value(upper_start_idx, upper_start_price, upper_end_idx, upper_end_price, end_idx)
    lower_latest_eval = line_value(lower_start_idx, lower_start_price, lower_end_idx, lower_end_price, end_idx)

    initial_width = upper_start_eval - lower_start_eval
    current_width = upper_latest_eval - lower_latest_eval
    if initial_width <= 0 or current_width <= 0:
        return patterns
    if current_width > initial_width * 0.85:
        return patterns

    latest_close = float(close_series.iloc[-1])
    breakout_idx = None
    direction = "neutral"

    if latest_close > upper_latest_eval:
        direction = "bullish"
        breakout_idx = len(df) - 1
    elif latest_close < lower_latest_eval:
        direction = "bearish"
        breakout_idx = len(df) - 1

    breakout_volume_valid = bool(
        breakout_idx is not None and float(volume_series.iloc[breakout_idx]) > volume_avg_20
    )
    confirmed = breakout_idx is not None and breakout_volume_valid
    target_magnitude = initial_width * 0.8
    target_price = latest_close + target_magnitude if direction == "bullish" else latest_close - target_magnitude

    patterns.append(
        {
            "name": "Symmetrical Triangle",
            "direction": direction if direction != "neutral" else "bullish",
            "confirmed": confirmed,
            "neckline": None,
            "points": [
                df.index[upper_start_idx].strftime("%Y-%m-%d"),
                df.index[upper_end_idx].strftime("%Y-%m-%d"),
                df.index[lower_start_idx].strftime("%Y-%m-%d"),
                df.index[lower_end_idx].strftime("%Y-%m-%d"),
            ],
            "volume_validated": breakout_volume_valid,
            "detail": "Daralan tepe-dip yapısı simetrik üçgeni işaret ediyor; kırılım yönü son mum kapanışıyla değerlendirildi.",
            "geometry": {
                "upper_start_index": upper_start_idx,
                "upper_end_index": upper_end_idx,
                "lower_start_index": lower_start_idx,
                "lower_end_index": lower_end_idx,
                "upper_start_price": round(upper_start_price, 4),
                "upper_end_price": round(upper_end_price, 4),
                "lower_start_price": round(lower_start_price, 4),
                "lower_end_price": round(lower_end_price, 4),
                "breakout_index": breakout_idx,
                "target_price": round(target_price, 4),
            },
        }
    )

    return patterns


def detect_cup_handle(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 180)
    close_series = df["Close"]
    volume_series = df["Volume"]
    volume_avg_20 = float(volume_series.tail(20).mean())

    recent_highs = [idx for idx in highs if idx >= lookback_start]
    recent_lows = [idx for idx in lows if idx >= lookback_start]
    if len(recent_highs) < 2 or len(recent_lows) < 1:
        return patterns

    for i in range(len(recent_highs) - 1):
        left_idx = recent_highs[i]
        right_idx = recent_highs[i + 1]
        if right_idx - left_idx < 22:
            continue

        left_peak = float(close_series.iloc[left_idx])
        right_peak = float(close_series.iloc[right_idx])
        peak_similarity = abs(left_peak - right_peak) / max(left_peak, right_peak, 1e-9)
        if peak_similarity > 0.06:
            continue

        cup_window = close_series.iloc[left_idx : right_idx + 1]
        bottom_rel = int(np.argmin(cup_window.to_numpy()))
        bottom_idx = left_idx + bottom_rel
        bottom_price = float(close_series.iloc[bottom_idx])
        if bottom_idx in {left_idx, right_idx}:
            continue

        cup_depth_ratio = (max(left_peak, right_peak) - bottom_price) / max(left_peak, right_peak, 1e-9)
        if cup_depth_ratio < 0.08:
            continue

        handle_end = min(len(close_series) - 1, right_idx + 30)
        if handle_end - right_idx < 4:
            continue
        handle_window = close_series.iloc[right_idx : handle_end + 1]
        handle_rel = int(np.argmin(handle_window.to_numpy()))
        handle_idx = right_idx + handle_rel
        handle_low = float(close_series.iloc[handle_idx])

        handle_drop_ratio = (right_peak - handle_low) / max(right_peak, 1e-9)
        if handle_drop_ratio > 0.15:
            continue
        if handle_low < bottom_price + (max(left_peak, right_peak) - bottom_price) * 0.45:
            continue

        neckline = max(left_peak, right_peak)
        breakout_idx = find_breakout_index(close_series, handle_idx, lambda _: neckline, "above")
        breakout_volume_valid = bool(
            breakout_idx is not None and float(volume_series.iloc[breakout_idx]) > volume_avg_20
        )
        confirmed = breakout_idx is not None and breakout_volume_valid and float(close_series.iloc[-1]) > neckline
        target_price = neckline + (neckline - bottom_price)

        patterns.append(
            {
                "name": "Cup and Handle",
                "direction": "bullish",
                "confirmed": confirmed,
                "neckline": round(neckline, 4),
                "points": [
                    df.index[left_idx].strftime("%Y-%m-%d"),
                    df.index[bottom_idx].strftime("%Y-%m-%d"),
                    df.index[right_idx].strftime("%Y-%m-%d"),
                    df.index[handle_idx].strftime("%Y-%m-%d"),
                ],
                "volume_validated": breakout_volume_valid,
                "detail": "Fincan-kulp formasyonu tespit edildi; kulp sonrası neckline kırılımı ve hacim onayı kontrol edildi.",
                "geometry": {
                    "left_index": left_idx,
                    "bottom_index": bottom_idx,
                    "right_index": right_idx,
                    "handle_index": handle_idx,
                    "left_price": round(left_peak, 4),
                    "bottom_price": round(bottom_price, 4),
                    "right_price": round(right_peak, 4),
                    "handle_price": round(handle_low, 4),
                    "neckline_start_index": left_idx,
                    "neckline_end_index": right_idx,
                    "neckline_start_price": round(neckline, 4),
                    "neckline_end_price": round(neckline, 4),
                    "breakout_index": breakout_idx,
                    "target_price": round(target_price, 4),
                },
            }
        )
        break

    return patterns


def detect_bearish_divergence(df: pd.DataFrame, highs: list[int]) -> bool:
    rsi = df["rsi14"]
    recent_highs = [idx for idx in highs if idx >= max(0, len(df) - 90)]
    if len(recent_highs) < 2:
        return False
    first_idx, second_idx = recent_highs[-2], recent_highs[-1]
    first_price = float(df["Close"].iloc[first_idx])
    second_price = float(df["Close"].iloc[second_idx])
    first_rsi = to_float(rsi.iloc[first_idx])
    second_rsi = to_float(rsi.iloc[second_idx])
    if first_rsi is None or second_rsi is None:
        return False
    return second_price > first_price and second_rsi < first_rsi


def score_to_action(score: int) -> str:
    if score > 75:
        return "GÜÇLÜ AL"
    if 60 <= score <= 75:
        return "AL"
    if 40 <= score < 60:
        return "TUT"
    if 25 <= score < 40:
        return "SAT"
    return "GÜÇLÜ SAT"


def apply_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close_data = df["Close"]
    high_data = df["High"]
    low_data = df["Low"]

    if isinstance(close_data, pd.DataFrame):
        close_data = close_data.iloc[:, 0]
    if isinstance(high_data, pd.DataFrame):
        high_data = high_data.iloc[:, 0]
    if isinstance(low_data, pd.DataFrame):
        low_data = low_data.iloc[:, 0]

    close = close_data.astype(float).to_numpy().ravel()
    high = high_data.astype(float).to_numpy().ravel()
    low = low_data.astype(float).to_numpy().ravel()

    df = df.copy()
    df["ema20"] = talib.EMA(close, timeperiod=20)
    df["sma50"] = talib.SMA(close, timeperiod=50)
    df["sma200"] = talib.SMA(close, timeperiod=200)
    macd, macd_signal, _ = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    df["macd"] = macd
    df["macd_signal"] = macd_signal
    df["rsi14"] = talib.RSI(close, timeperiod=14)
    df["atr14"] = talib.ATR(high, low, close, timeperiod=14)

    bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    df["bb_upper"] = bb_upper
    df["bb_middle"] = bb_middle
    df["bb_lower"] = bb_lower

    stoch_k, stoch_d = talib.STOCH(
        high,
        low,
        close,
        fastk_period=14,
        slowk_period=3,
        slowk_matype=0,
        slowd_period=3,
        slowd_matype=0,
    )
    df["stochastic_k"] = stoch_k
    df["stochastic_d"] = stoch_d
    df["adx14"] = talib.ADX(high, low, close, timeperiod=14)

    high_series = pd.Series(high)
    low_series = pd.Series(low)
    close_series = pd.Series(close)
    tenkan = (high_series.rolling(9).max() + low_series.rolling(9).min()) / 2
    kijun = (high_series.rolling(26).max() + low_series.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high_series.rolling(52).max() + low_series.rolling(52).min()) / 2).shift(26)
    chikou = close_series.shift(-26)

    df["ichimoku_tenkan"] = tenkan.to_numpy()
    df["ichimoku_kijun"] = kijun.to_numpy()
    df["ichimoku_span_a"] = span_a.to_numpy()
    df["ichimoku_span_b"] = span_b.to_numpy()
    df["ichimoku_chikou"] = chikou.to_numpy()
    return df


def build_risk_block(action: str, entry: float, atr: float | None) -> dict:
    if atr is None or action not in {"AL", "GÜÇLÜ AL"}:
        return {
            "entry_price": round(entry, 4),
            "atr": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
        }

    stop_loss = entry - (1.5 * atr)
    take_profit = entry + (3.0 * atr)

    return {
        "entry_price": round(entry, 4),
        "atr": round(atr, 4),
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
        "risk_reward": "1:2",
    }


def build_price_history(df: pd.DataFrame) -> list[dict]:
    history = []
    for timestamp, row in df.tail(180).iterrows():
        history.append(
            {
                "date": timestamp.strftime("%Y-%m-%d"),
                "open": to_round(row.get("Open"), 4),
                "high": to_round(row.get("High"), 4),
                "low": to_round(row.get("Low"), 4),
                "close": round(float(row["Close"]), 4),
                "volume": round(float(row["Volume"]), 2),
                "ema20": to_round(row.get("ema20"), 4),
                "sma50": to_round(row.get("sma50"), 4),
                "sma200": to_round(row.get("sma200"), 4),
                "rsi14": to_round(row.get("rsi14"), 4),
            }
        )
    return history


def build_volume_analysis(df: pd.DataFrame, confirmed_patterns: list[dict]) -> dict:
    volume_series = df["Volume"].astype(float)
    recent_avg_20 = float(volume_series.tail(20).mean()) if len(volume_series) >= 20 else float(volume_series.mean())
    recent_avg_10 = float(volume_series.tail(10).mean()) if len(volume_series) >= 10 else float(volume_series.mean())
    prev_avg_10 = (
        float(volume_series.iloc[-20:-10].mean())
        if len(volume_series) >= 20
        else recent_avg_10
    )

    pct_change_10 = 0.0
    if prev_avg_10 > 0:
        pct_change_10 = ((recent_avg_10 - prev_avg_10) / prev_avg_10) * 100

    breakout_ratio = 0.0
    breakout_volume = None
    breakout_avg_ref = recent_avg_20
    volume_confirmed_breakout = False

    for pattern in confirmed_patterns:
        geometry = pattern.get("geometry", {})
        breakout_idx = geometry.get("breakout_index")
        if isinstance(breakout_idx, int) and 0 <= breakout_idx < len(volume_series):
            breakout_volume = float(volume_series.iloc[breakout_idx])
            reference = float(volume_series.iloc[max(0, breakout_idx - 20):breakout_idx].mean()) if breakout_idx > 0 else recent_avg_20
            breakout_avg_ref = reference if reference > 0 else recent_avg_20
            if breakout_avg_ref > 0:
                breakout_ratio = breakout_volume / breakout_avg_ref
                volume_confirmed_breakout = breakout_ratio >= 1.2
            break

    flow_label = "Para girişi"
    if pct_change_10 < -1.0:
        flow_label = "Para çıkışı"

    status_word = "arttı" if pct_change_10 >= 0 else "azaldı"
    abs_pct = round(abs(pct_change_10), 2)

    return {
        "avg_10": round(recent_avg_10, 2),
        "avg_20": round(recent_avg_20, 2),
        "prev_10": round(prev_avg_10, 2),
        "breakout_volume": round(breakout_volume, 2) if breakout_volume is not None else None,
        "breakout_reference_avg": round(breakout_avg_ref, 2) if breakout_avg_ref is not None else None,
        "breakout_ratio": round(breakout_ratio, 4),
        "volume_confirmed_breakout": volume_confirmed_breakout,
        "breakout_note": "Hacim Onaylı Kırılım" if volume_confirmed_breakout else "Hacim Onayı Bekleniyor",
        "change_10d_pct": round(pct_change_10, 2),
        "human_text": f"Hacim son 10 gün ortalamasına göre %{abs_pct} {status_word}. {flow_label} sinyali destekliyor.",
    }


def enforce_directional_target(signal_doc: dict, target_price: float | None) -> float | None:
    if target_price is None:
        return None

    action = str(signal_doc.get("action") or "")
    last_price = to_float(signal_doc.get("last_price"))
    atr = to_float((signal_doc.get("indicators") or {}).get("atr14"))
    if last_price is None:
        return target_price

    if action in {"AL", "GÜÇLÜ AL"}:
        min_target = last_price + (3.0 * atr if atr is not None else last_price * 0.01)
        return max(target_price, min_target)
    if action in {"SAT", "GÜÇLÜ SAT"}:
        max_target = last_price - (3.0 * atr if atr is not None else last_price * 0.01)
        return min(target_price, max_target)
    return target_price


def estimate_target_duration(patterns: list[dict], action: str) -> str:
    confirmed = [pattern for pattern in patterns if pattern.get("confirmed")]
    if not confirmed:
        return "7-14 Gün"

    primary = confirmed[0].get("name", "")
    mapping = {
        "Double Top": "5-10 Gün",
        "Double Bottom": "5-10 Gün",
        "Head and Shoulders": "10-20 Gün",
        "Inverse Head and Shoulders": "10-20 Gün",
        "Symmetrical Triangle": "7-14 Gün",
        "Cup and Handle": "15-30 Gün",
    }
    if primary in mapping:
        return mapping[primary]

    return "5-10 Gün" if action in {"AL", "GÜÇLÜ AL"} else "7-14 Gün"


def signal_label(action: str) -> str:
    mapping = {
        "GÜÇLÜ AL": "Güçlü Al",
        "AL": "Al",
        "TUT": "Tut",
        "SAT": "Sat",
        "GÜÇLÜ SAT": "Güçlü Sat",
    }
    return mapping.get(action, action)


def build_export_note(signal_doc: dict) -> str:
    volume = signal_doc.get("volume_analysis", {})
    if volume.get("volume_confirmed_breakout"):
        return "Hacim onaylı kırılım"
    return "Hacim onayı zayıf"


def is_strong_action(action: str) -> bool:
    return action in {"GÜÇLÜ AL", "GÜÇLÜ SAT"}


def action_to_direction(action: str) -> str:
    if action in {"AL", "GÜÇLÜ AL"}:
        return "bullish"
    if action in {"SAT", "GÜÇLÜ SAT"}:
        return "bearish"
    return "neutral"


def select_visual_pattern(action: str, patterns: list[dict]) -> dict | None:
    confirmed = [pattern for pattern in patterns if pattern.get("confirmed")]
    if not confirmed:
        return None

    bullish_priority = ["Cup and Handle", "Double Bottom", "Inverse Head and Shoulders", "Symmetrical Triangle"]
    bearish_priority = ["Double Top", "Head and Shoulders", "Symmetrical Triangle"]

    expected_direction = action_to_direction(action)
    if expected_direction == "bullish":
        candidates = [pattern for pattern in confirmed if pattern.get("direction") == "bullish"]
    elif expected_direction == "bearish":
        candidates = [pattern for pattern in confirmed if pattern.get("direction") == "bearish"]
    else:
        candidates = confirmed

    if not candidates:
        return None

    priorities = bullish_priority if expected_direction == "bullish" else bearish_priority
    for candidate_name in priorities:
        for pattern in candidates:
            if pattern.get("name") == candidate_name:
                return pattern

    return candidates[0]


def sanitize_symbol(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", symbol)


def signal_to_dataframe(signal_doc: dict) -> pd.DataFrame | None:
    price_history = signal_doc.get("price_history") or []
    if not price_history:
        return None

    parsed_rows = []
    for row in price_history:
        parsed_rows.append(
            {
                "date": pd.to_datetime(row.get("date")),
                "Open": to_float(row.get("open") if row.get("open") is not None else row.get("close")),
                "High": to_float(row.get("high") if row.get("high") is not None else row.get("close")),
                "Low": to_float(row.get("low") if row.get("low") is not None else row.get("close")),
                "Close": to_float(row.get("close")),
                "Volume": to_float(row.get("volume") if row.get("volume") is not None else 0.0),
            }
        )

    frame = pd.DataFrame(parsed_rows).dropna(subset=["date", "Close"]).copy()
    if frame.empty:
        return None

    frame.set_index("date", inplace=True)
    frame.sort_index(inplace=True)
    return frame


def generate_pattern_image(signal_doc: dict, force: bool = False, require_strong: bool = False) -> str | None:
    action = signal_doc.get("action", "")
    if require_strong and not is_strong_action(action):
        return None
    if signal_doc.get("pattern_image_url") and not force:
        return signal_doc.get("pattern_image_url")

    pattern = select_visual_pattern(action, signal_doc.get("patterns", []))
    if not pattern:
        return None

    chart_df = signal_to_dataframe(signal_doc)
    if chart_df is None or chart_df.empty:
        return None

    geometry = pattern.get("geometry", {})
    all_geometry_indices = [
        value
        for key, value in geometry.items()
        if key.endswith("_index") and isinstance(value, int) and value >= 0
    ]
    focus_start = max(0, min(all_geometry_indices) - 40) if all_geometry_indices else max(0, len(chart_df) - 140)
    chart_window = chart_df.iloc[focus_start:].copy()
    if chart_window.empty:
        chart_window = chart_df.tail(min(len(chart_df), 140)).copy()
    if chart_window.empty:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=chart_window.index,
            open=chart_window["Open"],
            high=chart_window["High"],
            low=chart_window["Low"],
            close=chart_window["Close"],
            increasing_line_color="#00E096",
            decreasing_line_color="#FF2D55",
            name="Fiyat",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_window.index,
            y=chart_window["Close"],
            mode="lines",
            line={"color": "#cbd5e1", "width": 1.1},
            name="Kapanış",
        )
    )

    def idx_to_xy(index_key: str, price_key: str | None = None):
        idx = geometry.get(index_key)
        if not isinstance(idx, int) or idx < 0 or idx >= len(chart_df):
            return None, None
        x_value = chart_df.index[idx]
        if price_key and geometry.get(price_key) is not None:
            y_value = float(geometry.get(price_key))
        else:
            y_value = float(chart_df["Close"].iloc[idx])
        return x_value, y_value

    def add_point(index_key: str, price_key: str, label: str, color: str):
        x_value, y_value = idx_to_xy(index_key, price_key)
        if x_value is None:
            return
        fig.add_trace(
            go.Scatter(
                x=[x_value],
                y=[y_value],
                mode="markers+text",
                text=[label],
                textposition="top center",
                marker={"size": 10, "color": color, "line": {"color": "#ffffff", "width": 1}},
                showlegend=False,
            )
        )

    def add_line(
        start_index_key: str,
        start_price_key: str,
        end_index_key: str,
        end_price_key: str,
        color: str,
        dash: str = "solid",
        width: float = 2,
    ):
        x0, y0 = idx_to_xy(start_index_key, start_price_key)
        x1, y1 = idx_to_xy(end_index_key, end_price_key)
        if x0 is None or x1 is None:
            return
        fig.add_trace(
            go.Scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line={"color": color, "dash": dash, "width": width},
                showlegend=False,
            )
        )

    breakout_x, breakout_y = idx_to_xy("breakout_index", None)
    if breakout_x is not None:
        fig.add_trace(
            go.Scatter(
                x=[breakout_x],
                y=[breakout_y],
                mode="markers+text",
                text=["Breakout"],
                textposition="bottom center",
                marker={"symbol": "star", "size": 13, "color": "#F59E0B"},
                showlegend=False,
            )
        )

    pattern_name = pattern.get("name")
    if pattern_name == "Double Top":
        add_point("left_index", "left_price", "T1", "#FF2D55")
        add_point("right_index", "right_price", "T2", "#FF2D55")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Double Bottom":
        add_point("left_index", "left_price", "D1", "#00E096")
        add_point("right_index", "right_price", "D2", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Head and Shoulders":
        add_point("left_index", "left_price", "Sol Omuz", "#FF2D55")
        add_point("head_index", "head_price", "Baş", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Omuz", "#FF2D55")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Inverse Head and Shoulders":
        add_point("left_index", "left_price", "Sol Omuz", "#00E096")
        add_point("head_index", "head_price", "Baş", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Omuz", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
        if breakout_x is not None:
            fig.add_annotation(
                x=breakout_x,
                y=breakout_y,
                text="TOBO Onaylandı",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#00E096",
                font={"color": "#00E096", "size": 12},
                bgcolor="rgba(9,9,11,0.8)",
            )
    elif pattern_name == "Symmetrical Triangle":
        add_line("upper_start_index", "upper_start_price", "upper_end_index", "upper_end_price", "#FF2D55")
        add_line("lower_start_index", "lower_start_price", "lower_end_index", "lower_end_price", "#00E096")
        if breakout_x is not None:
            fig.add_annotation(
                x=breakout_x,
                y=breakout_y,
                text="Breakout",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#F59E0B",
                font={"color": "#F59E0B", "size": 12},
                bgcolor="rgba(9,9,11,0.8)",
            )
    elif pattern_name == "Cup and Handle":
        add_point("left_index", "left_price", "Sol Rim", "#38BDF8")
        add_point("bottom_index", "bottom_price", "Cup Dip", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Rim", "#38BDF8")
        add_point("handle_index", "handle_price", "Kulp", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
        if breakout_x is not None:
            fig.add_annotation(
                x=breakout_x,
                y=breakout_y,
                text="Breakout",
                showarrow=True,
                arrowhead=2,
                arrowcolor="#F59E0B",
                font={"color": "#F59E0B", "size": 12},
                bgcolor="rgba(9,9,11,0.8)",
            )

    target_price = enforce_directional_target(signal_doc, to_float(geometry.get("target_price")))
    if target_price is not None:
        target_x = breakout_x if breakout_x is not None else chart_window.index[-1]
        fig.add_trace(
            go.Scatter(
                x=[chart_window.index[0], chart_window.index[-1]],
                y=[target_price, target_price],
                mode="lines",
                line={"color": "#F59E0B", "dash": "dot", "width": 1.6},
                name="Hedef",
            )
        )
        fig.add_annotation(
            x=target_x,
            y=target_price,
            text=f"HEDEF: {round(target_price, 4)}",
            showarrow=True,
            arrowhead=3,
            arrowcolor="#F59E0B",
            ax=60,
            ay=-40 if action == "GÜÇLÜ AL" else 40,
            font={"color": "#F59E0B", "size": 11},
            bgcolor="rgba(9,9,11,0.8)",
        )

    fig.update_layout(
        title=f"{signal_doc.get('symbol')} · {pattern_name} Onay Grafiği",
        paper_bgcolor="#09090b",
        plot_bgcolor="#09090b",
        font={"color": "#e4e4e7", "family": "Manrope"},
        margin={"l": 40, "r": 40, "t": 70, "b": 35},
        xaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,0.07)", "rangeslider": {"visible": False}},
        yaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,0.07)"},
    )

    safe_symbol = sanitize_symbol(str(signal_doc.get("symbol", "unknown")))
    pattern_slug = sanitize_symbol(pattern_name.lower().replace(" ", "_"))
    filename = f"{safe_symbol}_{pattern_slug}.png"
    output_path = PATTERN_STATIC_DIR / filename

    try:
        fig.write_image(str(output_path), format="png", width=1500, height=860, scale=1)
        return f"{PATTERN_IMAGE_ROUTE_PREFIX}/{filename}"
    except Exception as exc:
        logger.warning("Plotly image export failed for %s, matplotlib fallback çalışacak: %s", signal_doc.get("symbol"), exc)
        try:
            write_pattern_image_matplotlib(
                signal_doc=signal_doc,
                pattern=pattern,
                geometry=geometry,
                chart_df=chart_df,
                chart_window=chart_window,
                action=action,
                output_path=output_path,
            )
            return f"{PATTERN_IMAGE_ROUTE_PREFIX}/{filename}"
        except Exception as fallback_exc:
            logger.warning("Pattern image fallback da başarısız oldu %s: %s", signal_doc.get("symbol"), fallback_exc)
            return None


async def ensure_pattern_visualization(signal_doc: dict, force: bool = False, require_strong: bool = False) -> str | None:
    return await asyncio.to_thread(generate_pattern_image, signal_doc, force, require_strong)


def write_pattern_image_matplotlib(
    signal_doc: dict,
    pattern: dict,
    geometry: dict,
    chart_df: pd.DataFrame,
    chart_window: pd.DataFrame,
    action: str,
    output_path: Path,
) -> bool:
    fig, ax = plt.subplots(figsize=(15, 8.6), dpi=120)
    fig.patch.set_facecolor("#09090b")
    ax.set_facecolor("#09090b")

    x_vals = mdates.date2num(chart_window.index.to_pydatetime())
    candle_width = 0.6

    for idx, (_, row) in enumerate(chart_window.iterrows()):
        open_price = float(row["Open"])
        high_price = float(row["High"])
        low_price = float(row["Low"])
        close_price = float(row["Close"])
        color = "#00E096" if close_price >= open_price else "#FF2D55"

        ax.vlines(x_vals[idx], low_price, high_price, color=color, linewidth=1.1, alpha=0.9)
        body_bottom = min(open_price, close_price)
        body_height = max(abs(close_price - open_price), 1e-5)
        ax.add_patch(
            Rectangle(
                (x_vals[idx] - candle_width / 2, body_bottom),
                candle_width,
                body_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.75,
            )
        )

    ax.plot(x_vals, chart_window["Close"].to_numpy(), color="#d4d4d8", linewidth=1.2, alpha=0.9)

    def idx_to_xy(index_key: str, price_key: str | None = None):
        idx = geometry.get(index_key)
        if not isinstance(idx, int) or idx < 0 or idx >= len(chart_df):
            return None, None
        timestamp = chart_df.index[idx]
        x = mdates.date2num(timestamp.to_pydatetime())
        if price_key and geometry.get(price_key) is not None:
            y = float(geometry.get(price_key))
        else:
            y = float(chart_df["Close"].iloc[idx])
        return x, y

    def add_point(index_key: str, price_key: str, label: str, color: str):
        x, y = idx_to_xy(index_key, price_key)
        if x is None:
            return
        ax.scatter([x], [y], color=color, s=62, edgecolor="white", linewidth=0.8, zorder=6)
        ax.text(x, y, label, color=color, fontsize=10, fontweight="bold", ha="center", va="bottom")

    def add_line(start_index_key: str, start_price_key: str, end_index_key: str, end_price_key: str, color: str, style: str = "-"):
        x0, y0 = idx_to_xy(start_index_key, start_price_key)
        x1, y1 = idx_to_xy(end_index_key, end_price_key)
        if x0 is None or x1 is None:
            return
        ax.plot([x0, x1], [y0, y1], color=color, linewidth=1.8, linestyle=style, alpha=0.95)

    breakout_x, breakout_y = idx_to_xy("breakout_index", None)
    if breakout_x is not None:
        ax.scatter([breakout_x], [breakout_y], color="#F59E0B", s=95, marker="*", zorder=7)
        ax.text(breakout_x, breakout_y, "Breakout", color="#F59E0B", fontsize=10, ha="left", va="bottom")

    pattern_name = pattern.get("name")
    if pattern_name == "Double Top":
        add_point("left_index", "left_price", "T1", "#FF2D55")
        add_point("right_index", "right_price", "T2", "#FF2D55")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Double Bottom":
        add_point("left_index", "left_price", "D1", "#00E096")
        add_point("right_index", "right_price", "D2", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Head and Shoulders":
        add_point("left_index", "left_price", "Sol Omuz", "#FF2D55")
        add_point("head_index", "head_price", "Baş", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Omuz", "#FF2D55")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
    elif pattern_name == "Inverse Head and Shoulders":
        add_point("left_index", "left_price", "Sol Omuz", "#00E096")
        add_point("head_index", "head_price", "Baş", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Omuz", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
        if breakout_x is not None:
            ax.text(breakout_x, breakout_y, "TOBO Onaylandı", color="#00E096", fontsize=10, ha="left", va="top")
    elif pattern_name == "Symmetrical Triangle":
        add_line("upper_start_index", "upper_start_price", "upper_end_index", "upper_end_price", "#FF2D55")
        add_line("lower_start_index", "lower_start_price", "lower_end_index", "lower_end_price", "#00E096")
    elif pattern_name == "Cup and Handle":
        add_point("left_index", "left_price", "Sol Rim", "#38BDF8")
        add_point("bottom_index", "bottom_price", "Cup Dip", "#F59E0B")
        add_point("right_index", "right_price", "Sağ Rim", "#38BDF8")
        add_point("handle_index", "handle_price", "Kulp", "#00E096")
        add_line("neckline_start_index", "neckline_start_price", "neckline_end_index", "neckline_end_price", "#38BDF8")
        if breakout_x is not None:
            ax.text(breakout_x, breakout_y, "Breakout", color="#F59E0B", fontsize=10, ha="left", va="top")

    target_price = enforce_directional_target(signal_doc, to_float(geometry.get("target_price")))
    if target_price is not None:
        ax.axhline(y=target_price, color="#F59E0B", linestyle=":", linewidth=1.6)
        ref_x = breakout_x if breakout_x is not None else x_vals[-1]
        ax.annotate(
            f"HEDEF: {round(target_price, 4)}",
            xy=(ref_x, target_price),
            xytext=(ref_x + 14, target_price + (target_price * 0.03 if action == "GÜÇLÜ AL" else -target_price * 0.03)),
            color="#F59E0B",
            fontsize=10,
            arrowprops={"arrowstyle": "->", "color": "#F59E0B", "lw": 1.2},
        )

    ax.grid(True, color="#27272a", linestyle="--", alpha=0.35)
    ax.set_title(f"{signal_doc.get('symbol')} · {pattern_name} Onay Grafiği", color="#f4f4f5", fontsize=14, fontweight="bold")
    ax.tick_params(axis="x", colors="#a1a1aa")
    ax.tick_params(axis="y", colors="#a1a1aa")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=25)

    plt.tight_layout()
    fig.savefig(output_path, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    return True


def fetch_symbol_ohlcv(symbol: str) -> pd.DataFrame | None:
    history = yf.download(
        tickers=symbol,
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        ignore_tz=True,  # İŞTE O KİLİDİ KIRAN ALTIN PARAMETRE!
    )
    
    if history is None or history.empty:
        return None
        
    return history
    if history is None or history.empty:
        return None

    if isinstance(history.columns, pd.MultiIndex):
        history.columns = [col[0] if isinstance(col, tuple) else col for col in history.columns]

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    if not all(col in history.columns for col in required_cols):
        return None

    prepared = history[required_cols].copy()
    prepared = prepared.loc[:, ~prepared.columns.duplicated()]
    for column in required_cols:
        column_data = prepared[column]
        if isinstance(column_data, pd.DataFrame):
            prepared[column] = column_data.iloc[:, 0]

    prepared = prepared.dropna().copy()
    prepared = prepared[~prepared.index.duplicated(keep="last")]
    prepared.sort_index(inplace=True)
    if len(prepared) < 120:
        return None
    return prepared


def fetch_fundamentals(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    try:
        info = dict(ticker.info or {})
    except Exception:
        info = {}

    try:
        fast_info = dict(ticker.fast_info or {})
    except Exception:
        fast_info = {}

    pe = to_float(info.get("trailingPE") or info.get("forwardPE"))
    pb = to_float(info.get("priceToBook"))
    current_ratio = to_float(info.get("currentRatio"))
    debt_to_equity = to_float(info.get("debtToEquity"))
    eps_growth = to_float(info.get("earningsQuarterlyGrowth"))
    market_cap = to_float(fast_info.get("marketCap"))
    roe = to_float(info.get("returnOnEquity"))
    net_profit_margin = to_float(info.get("profitMargins"))
    dividend_yield = to_float(info.get("dividendYield"))
    sector = str(info.get("sector") or "Unknown")
    sector_pe_avg = float(SECTOR_PE_BENCHMARK.get(sector, 22.0))

    quality_score = 0
    notes: list[str] = []
    hard_cap_trigger = False

    valuation_positive = pe is not None and pb is not None and pe < sector_pe_avg and pb < 3
    if valuation_positive:
        quality_score += 35
        notes.append("Değerleme metrikleri sektör ortalamasına göre avantajlı.")
    else:
        notes.append("Değerleme metriklerinde nötr/negatif görünüm var.")

    health_positive = current_ratio is not None and current_ratio >= 1.0 and (debt_to_equity is None or debt_to_equity < 220)
    if health_positive:
        quality_score += 30
        notes.append("Likidite ve borç dengesi kabul edilebilir seviyede.")
    else:
        notes.append("Likidite veya borç dengesi ideal eşiklerin altında.")

    growth_positive = eps_growth is not None and eps_growth > 0
    if growth_positive:
        quality_score += 35
        notes.append("Çeyreklik EPS büyümesi pozitif.")
    else:
        notes.append("EPS büyümesinde zayıflık gözleniyor.")

    if current_ratio is not None and current_ratio < 0.75:
        hard_cap_trigger = True
        notes.append("Cari oran 0.75 altında: skora güvenlik sınırı uygulanır.")

    if eps_growth is not None and eps_growth < 0:
        hard_cap_trigger = True
        notes.append("EPS büyümesi negatif: skora güvenlik sınırı uygulanır.")

    return {
        "pe": to_round(pe, 4),
        "pb": to_round(pb, 4),
        "market_cap": to_round(market_cap, 2),
        "sector": sector,
        "sector_pe_avg": sector_pe_avg,
        "current_ratio": to_round(current_ratio, 4),
        "debt_to_equity": to_round(debt_to_equity, 4),
        "eps_growth_qoq": to_round(eps_growth, 4),
        "roe": to_round(roe, 4),
        "net_profit_margin": to_round(net_profit_margin, 4),
        "dividend_yield": to_round(dividend_yield, 4),
        "score": int(max(0, min(100, quality_score))),
        "hard_cap_trigger": hard_cap_trigger,
        "notes": notes,
    }


async def get_fundamentals_with_cache(symbol: str, force_refresh: bool = False) -> dict:
    cached = await fundamentals_collection.find_one({"symbol": symbol}, {"_id": 0})
    if not force_refresh and cached and isinstance(cached.get("updated_at"), str):
        try:
            updated_at = datetime.fromisoformat(cached["updated_at"])
            if datetime.now(timezone.utc) - updated_at < timedelta(hours=24):
                return cached.get("data", {})
        except ValueError:
            logger.warning("Fundamental cache timestamp parse failed for %s", symbol)

    try:
        fundamentals = await asyncio.to_thread(fetch_fundamentals, symbol)
        await fundamentals_collection.update_one(
            {"symbol": symbol},
            {"$set": {"symbol": symbol, "data": fundamentals, "updated_at": now_iso()}},
            upsert=True,
        )
        return fundamentals
    except Exception as exc:
        logger.warning("Fundamental fetch failed for %s: %s", symbol, exc)
        return {
            "pe": None,
            "pb": None,
            "market_cap": None,
            "sector": "Unknown",
            "sector_pe_avg": 22.0,
            "current_ratio": None,
            "debt_to_equity": None,
            "eps_growth_qoq": None,
            "roe": None,
            "net_profit_margin": None,
            "dividend_yield": None,
            "score": 0,
            "hard_cap_trigger": False,
            "notes": ["Temel veri alınamadı; puan nötr bırakıldı."],
        }


def build_signal(symbol: str, market: str, raw_df: pd.DataFrame, fundamentals: dict) -> dict:
    df = apply_indicators(raw_df)
    highs, lows = detect_local_extrema(df["Close"])

    pattern_candidates = detect_double_top_bottom(df, highs, lows)
    pattern_candidates.extend(detect_head_shoulders(df, highs, lows))
    pattern_candidates.extend(detect_symmetrical_triangle(df, highs, lows))
    pattern_candidates.extend(detect_cup_handle(df, highs, lows))
    confirmed_patterns = [pattern for pattern in pattern_candidates if pattern["confirmed"]]
    volume_analysis = build_volume_analysis(df, confirmed_patterns)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    close = float(latest["Close"])
    ema20 = to_float(latest["ema20"])
    sma50 = to_float(latest["sma50"])
    sma200 = to_float(latest["sma200"])
    atr14 = to_float(latest["atr14"])

    volume_confirmation = float(df["Volume"].tail(3).mean()) > float(df["Volume"].tail(20).mean())
    golden_cross = (
        to_float(prev.get("sma50")) is not None
        and to_float(prev.get("sma200")) is not None
        and sma50 is not None
        and sma200 is not None
        and float(prev["sma50"]) <= float(prev["sma200"])
        and sma50 > sma200
    )
    death_cross = (
        to_float(prev.get("sma50")) is not None
        and to_float(prev.get("sma200")) is not None
        and sma50 is not None
        and sma200 is not None
        and float(prev["sma50"]) >= float(prev["sma200"])
        and sma50 < sma200
    )
    bearish_divergence = detect_bearish_divergence(df, highs)

    rsi_val = to_float(latest.get("rsi14"))
    macd_val = to_float(latest.get("macd"))
    macd_signal_val = to_float(latest.get("macd_signal"))

    trend_positive = bool(
        ema20 is not None and sma50 is not None and sma200 is not None and close > ema20 and sma50 > sma200
    )
    momentum_positive = bool(
        rsi_val is not None
        and macd_val is not None
        and macd_signal_val is not None
        and 38 <= rsi_val <= 72
        and macd_val >= macd_signal_val
    )

    technical_raw = 20
    if confirmed_patterns:
        technical_raw += 45
    if trend_positive or golden_cross:
        technical_raw += 20
    if momentum_positive:
        technical_raw += 15
    if death_cross:
        technical_raw -= 20
    if bearish_divergence:
        technical_raw -= 15
    technical_raw = int(max(0, min(100, technical_raw)))

    fundamental_raw = int(max(0, min(100, fundamentals.get("score", 0))))
    volume_raw = 70 if volume_confirmation else 20
    if volume_analysis.get("volume_confirmed_breakout"):
        volume_raw = 100

    technical_points = int(round(technical_raw * 0.40))
    fundamental_points = int(round(fundamental_raw * 0.30))
    volume_points = int(round(volume_raw * 0.30))

    bullish_score = int(max(0, min(100, technical_points + fundamental_points + volume_points)))

    if volume_analysis.get("volume_confirmed_breakout"):
        bullish_score = min(100, bullish_score + 8)

    if fundamentals.get("hard_cap_trigger"):
        bullish_score = min(bullish_score, 45)

    action = score_to_action(bullish_score)
    risk = build_risk_block(action, close, atr14)

    signal_doc = {
        "symbol": symbol,
        "market": market,
        "action": action,
        "bullish_score": int(max(0, min(100, bullish_score))),
        "score_breakdown": {
            "technical": technical_points,
            "volume": volume_points,
            "fundamental": fundamental_points,
            "raw_technical": technical_raw,
            "raw_fundamental": fundamental_raw,
            "raw_volume": volume_raw,
            "volume_breakout_bonus": 8 if volume_analysis.get("volume_confirmed_breakout") else 0,
        },
        "last_price": round(close, 4),
        "patterns": pattern_candidates,
        "indicators": {
            "ema20": to_round(ema20, 4),
            "sma50": to_round(sma50, 4),
            "sma200": to_round(sma200, 4),
            "rsi14": to_round(latest.get("rsi14"), 4),
            "macd": to_round(latest.get("macd"), 4),
            "macd_signal": to_round(latest.get("macd_signal"), 4),
            "atr14": to_round(atr14, 4),
            "bb_upper": to_round(latest.get("bb_upper"), 4),
            "bb_middle": to_round(latest.get("bb_middle"), 4),
            "bb_lower": to_round(latest.get("bb_lower"), 4),
            "stochastic_k": to_round(latest.get("stochastic_k"), 4),
            "stochastic_d": to_round(latest.get("stochastic_d"), 4),
            "adx14": to_round(latest.get("adx14"), 4),
            "ichimoku_tenkan": to_round(latest.get("ichimoku_tenkan"), 4),
            "ichimoku_kijun": to_round(latest.get("ichimoku_kijun"), 4),
            "ichimoku_span_a": to_round(latest.get("ichimoku_span_a"), 4),
            "ichimoku_span_b": to_round(latest.get("ichimoku_span_b"), 4),
            "golden_cross": golden_cross,
            "death_cross": death_cross,
            "bearish_divergence": bearish_divergence,
            "volume_confirmation": volume_confirmation,
        },
        "fundamental": fundamentals,
        "risk": risk,
        "volume_analysis": volume_analysis,
        "updated_at": now_iso(),
        "price_history": build_price_history(df),
        "ai_summary": None,
        "pattern_image_url": None,
        "pattern_image_updated_at": None,
    }
    return sanitize_for_json(signal_doc)


async def analyze_symbol(symbol: str, market: str) -> dict | None:
    try:
        raw_df = await asyncio.to_thread(fetch_symbol_ohlcv, symbol)
        if raw_df is None:
            return None
        fundamentals = await get_fundamentals_with_cache(symbol)
        return build_signal(symbol, market, raw_df, fundamentals)
    except Exception as exc:
        logger.warning("Analysis failed for %s: %s", symbol, exc)
        return None


async def resolve_symbol_and_market(symbol_input: str) -> tuple[str | None, str | None, pd.DataFrame | None]:
    raw_symbol = symbol_input.strip().upper()
    if not raw_symbol:
        return None, None, None

    variants = [raw_symbol]
    if not raw_symbol.endswith(".IS"):
        variants.append(f"{raw_symbol}.IS")

    for candidate in variants:
        raw_df = await asyncio.to_thread(fetch_symbol_ohlcv, candidate)
        if raw_df is not None:
            market = "BIST" if candidate.endswith(".IS") else "US"
            return candidate, market, raw_df

    return None, None, None


async def analyze_and_store_symbol(
    symbol_input: str,
    include_ai_summary: bool = True,
    include_pattern_image: bool = True,
    force_live_data: bool = False,
    prefer_stream_consistency: bool = False,
) -> dict:
    existing_document = await fetch_signal_document(symbol_input)
    if prefer_stream_consistency and existing_document and isinstance(existing_document.get("updated_at"), str):
        try:
            updated = datetime.fromisoformat(existing_document["updated_at"])
            age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
            if age_seconds <= SCAN_INTERVAL_SECONDS:
                return existing_document
        except ValueError:
            pass

    symbol, market, raw_df = await resolve_symbol_and_market(symbol_input)
    if symbol is None or raw_df is None or market is None:
        raise HTTPException(status_code=404, detail="Sembol için veri bulunamadı")

    fundamentals = await get_fundamentals_with_cache(symbol, force_refresh=force_live_data)
    signal_doc = build_signal(symbol, market, raw_df, fundamentals)

    update_payload = signal_doc.copy()
    if include_pattern_image:
        image_url = await ensure_pattern_visualization(signal_doc, force=True, require_strong=False)
        update_payload["pattern_image_url"] = image_url
        update_payload["pattern_image_updated_at"] = now_iso()

    if include_ai_summary:
        summary = await generate_ai_summary(update_payload)
        update_payload["ai_summary"] = summary
        update_payload["ai_summary_updated_at"] = now_iso()

    await signals_collection.update_one(
        {"symbol": symbol},
        {"$set": update_payload},
        upsert=True,
    )
    return update_payload


async def run_scan(trigger: str = "scheduler") -> dict:
    async with scan_lock:
        if scan_state.running:
            return {"status": "already_running"}

        started_at = datetime.now(timezone.utc)
        scan_state.running = True
        scan_state.last_error = None
        logger.info("Scan started by %s", trigger)

        tasks = []
        semaphore = asyncio.Semaphore(16)
        market_universe = await get_market_universe(force_refresh=False)

        async def guarded_analysis(symbol: str, market: str):
            async with semaphore:
                return await analyze_symbol(symbol, market)

        for market, symbols in market_universe.items():
            for symbol in symbols:
                tasks.append(guarded_analysis(symbol, market))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        scanned_docs = [result for result in results if isinstance(result, dict)]

        if scanned_docs:
            symbols = [doc["symbol"] for doc in scanned_docs]
            existing_docs = await signals_collection.find(
                {"symbol": {"$in": symbols}},
                {
                    "_id": 0,
                    "symbol": 1,
                    "ai_summary": 1,
                    "ai_summary_updated_at": 1,
                    "pattern_image_url": 1,
                    "pattern_image_updated_at": 1,
                },
            ).to_list(len(symbols))
            existing_map = {item["symbol"]: item for item in existing_docs}

            for doc in scanned_docs:
                existing = existing_map.get(doc["symbol"])
                if not existing:
                    continue
                if existing.get("ai_summary"):
                    doc["ai_summary"] = existing.get("ai_summary")
                    doc["ai_summary_updated_at"] = existing.get("ai_summary_updated_at")

                compatible_pattern = select_visual_pattern(doc.get("action", ""), doc.get("patterns", []))
                if compatible_pattern:
                    doc["pattern_image_url"] = existing.get("pattern_image_url")
                    doc["pattern_image_updated_at"] = existing.get("pattern_image_updated_at")
                else:
                    doc["pattern_image_url"] = None
                    doc["pattern_image_updated_at"] = None

            operations = [
                UpdateOne({"symbol": doc["symbol"]}, {"$set": doc}, upsert=True)
                for doc in scanned_docs
            ]
            await signals_collection.bulk_write(operations, ordered=False)

        ended_at = datetime.now(timezone.utc)
        scan_state.running = False
        scan_state.last_run = ended_at.isoformat()
        scan_state.last_duration_seconds = round((ended_at - started_at).total_seconds(), 2)
        scan_state.last_scanned_count = len(scanned_docs)
        logger.info("Scan finished: %s symbols processed", len(scanned_docs))
        return {
            "status": "completed",
            "processed": len(scanned_docs),
            "duration_seconds": scan_state.last_duration_seconds,
        }


async def scanner_loop():
    while True:
        try:
            await run_scan(trigger="scheduler")
        except Exception as exc:
            scan_state.running = False
            scan_state.last_error = str(exc)
            logger.exception("Scheduler cycle failed: %s", exc)
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


def build_local_summary(signal_doc: dict) -> str:
    indicators = signal_doc.get("indicators", {})
    fundamentals = signal_doc.get("fundamental", {})
    risk = signal_doc.get("risk", {})
    volume = signal_doc.get("volume_analysis", {})
    patterns = signal_doc.get("patterns", [])
    pattern_image_url = signal_doc.get("pattern_image_url")
    confirmed = [pattern["name"] for pattern in patterns if pattern.get("confirmed")]
    pattern_text = ", ".join(confirmed) if confirmed else "Onaylı kırılım formasyonu henüz yok"

    summary = (
        f"1. **Teknik Durum:** {pattern_text}. RSI: {indicators.get('rsi14')} ve MACD: {indicators.get('macd')} seviyelerinde.\n"
        f"2. **Temel Durum:** P/E={fundamentals.get('pe')}, P/B={fundamentals.get('pb')}, Cari Oran={fundamentals.get('current_ratio')}.\n"
        f"3. **Hacim Durumu:** {volume.get('human_text', 'Hacim analizi hesaplanamadı.')}\n"
        f"4. **Aksiyon ve Risk:** {signal_doc.get('action')} sinyali. Giriş={risk.get('entry_price')}, Stop-Loss={risk.get('stop_loss')}, Take-Profit={risk.get('take_profit')}."
    )
    if pattern_image_url:
        summary += f"\n\nFormasyon görseli: {pattern_image_url}"
    return summary


async def generate_ai_summary(signal_doc: dict) -> str:
    if not EMERGENT_LLM_KEY:
        return build_local_summary(signal_doc)

    system_prompt = (
        "Sen bir yatırım danışmanısın. Sana verilen ham skorları ve formasyonları analiz ederek 4 maddelik bir özet çıkar.\n"
        "Format:\n"
        "1. **Teknik Durum:** (Örn: Fiyat 50 günlük ortalamasından sekti ve Çift Dip formasyonu onaylandı. RSI pozitif uyumsuzluk gösteriyor.)\n"
        "2. **Temel Durum:** (Örn: F/K oranı sektörünün %15 altında, son bilançoda net kar beklentileri aştı.)\n"
        "3. **Hacim Durumu:** (Örn: Hacim son 10 gün ortalamasına göre %18 arttı, para girişi sinyali destekliyor.)\n"
        "4. **Aksiyon ve Risk:** (Örn: X fiyatından AL sinyali üretildi. Risk yönetimi için Y seviyesine Stop-Loss, Z seviyesine Take-Profit konulmalıdır.)"
    )

    payload = {
        "symbol": signal_doc.get("symbol"),
        "action": signal_doc.get("action"),
        "bullish_score": signal_doc.get("bullish_score"),
        "score_breakdown": signal_doc.get("score_breakdown"),
        "patterns": signal_doc.get("patterns"),
        "indicators": signal_doc.get("indicators"),
        "fundamental": signal_doc.get("fundamental"),
        "volume_analysis": signal_doc.get("volume_analysis"),
        "risk": signal_doc.get("risk"),
        "pattern_image_url": signal_doc.get("pattern_image_url"),
    }

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"signal-summary-{signal_doc.get('symbol')}-{uuid.uuid4()}",
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")

        user_message = UserMessage(
            text=(
                "Aşağıdaki ham verileri analiz et ve sadece 4 maddelik formatta Türkçe yanıt üret. "
                "4 başlık dışına çıkma. "
                "Eğer pattern_image_url doluysa yanıtın sonunda 'Formasyon Görseli: <url>' satırını ekle.\n"
                f"Veri:\n{json.dumps(payload, ensure_ascii=False)}"
            )
        )

        response = await asyncio.wait_for(chat.send_message(user_message), timeout=30)
        return str(response).strip()
    except Exception as exc:
        logger.warning("AI summary failed for %s: %s", signal_doc.get("symbol"), exc)
        return build_local_summary(signal_doc)


async def fetch_signal_document(symbol: str) -> dict | None:
    symbol_upper = symbol.upper()
    document = await signals_collection.find_one({"symbol": symbol_upper}, {"_id": 0})
    if document is None and not symbol_upper.endswith(".IS"):
        document = await signals_collection.find_one({"symbol": f"{symbol_upper}.IS"}, {"_id": 0})
    return document


@api_router.get("/")
async def root():
    market_universe = await get_market_universe(force_refresh=False)
    return {
        "message": "Algorithmic signal engine is active",
        "scanner_interval_seconds": SCAN_INTERVAL_SECONDS,
        "markets": {"US": len(market_universe["US"]), "BIST": len(market_universe["BIST"])}
    }


@api_router.get("/config")
async def get_config():
    market_universe = await get_market_universe(force_refresh=False)
    return {
        "refresh_seconds": SCAN_INTERVAL_SECONDS,
        "markets": {
            "US": market_universe["US"],
            "BIST": market_universe["BIST"],
        },
        "default_interval": "1d",
        "data_source": "Yahoo Finance (US + BIST .IS)",
        "llm_provider": "Gemini 3 Flash",
    }


@api_router.get("/scanner/state", response_model=ScannerState)
async def get_scanner_state():
    return scan_state


@api_router.post("/scanner/run")
async def trigger_manual_scan():
    if scan_state.running:
        return {"status": "already_running"}
    await get_market_universe(force_refresh=True)
    asyncio.create_task(run_scan(trigger="manual"))
    return {"status": "started", "message": "Manuel tarama başlatıldı"}


@api_router.get("/signals", response_model=list[SignalRecord])
async def get_signals(
    market: str = Query("ALL"),
    action: str = Query("ALL"),
    limit: int = Query(600, ge=1, le=1200),
    search: str | None = Query(default=None),
):
    query: dict = {}
    if market in {"US", "BIST"}:
        query["market"] = market
    if action != "ALL":
        query["action"] = action
    if search:
        query["symbol"] = {"$regex": f"^{search.upper()}"}

    docs = (
        await signals_collection.find(query, {"_id": 0})
        .sort([("bullish_score", -1), ("updated_at", -1)])
        .limit(limit)
        .to_list(limit)
    )
    return [sanitize_for_json(doc) for doc in docs]


@api_router.post("/signals/export/excel")
async def export_signals_excel(filters: ExportFilterRequest):
    market_map = {"NASDAQ": "US", "US": "US", "BIST": "BIST"}
    action_map = {
        "GÜÇLÜ AL": "GÜÇLÜ AL",
        "GÜÇLÜAL": "GÜÇLÜ AL",
        "GUÇLÜ AL": "GÜÇLÜ AL",
        "GÜÇLÜ SAT": "GÜÇLÜ SAT",
        "GÜÇLÜSAT": "GÜÇLÜ SAT",
        "GUÇLÜ SAT": "GÜÇLÜ SAT",
        "AL": "AL",
        "TUT": "TUT",
        "SAT": "SAT",
    }

    selected_markets = [market_map.get(str(item).upper(), None) for item in filters.markets]
    selected_markets = [item for item in selected_markets if item in {"US", "BIST"}]

    selected_actions = []
    for item in filters.actions:
        normalized = str(item).upper().strip()
        mapped = action_map.get(normalized)
        if mapped:
            selected_actions.append(mapped)

    query: dict[str, Any] = {}
    if selected_markets:
        query["market"] = {"$in": selected_markets}
    if selected_actions:
        query["action"] = {"$in": selected_actions}

    docs = await signals_collection.find(query, {"_id": 0}).sort([("bullish_score", -1), ("updated_at", -1)]).to_list(5000)

    rows: list[dict[str, Any]] = []
    for doc in docs:
        rows.append(
            {
                "Hisse Kodu": doc.get("symbol"),
                "Mevcut Sinyal": signal_label(str(doc.get("action", ""))),
                "Hedef Süresi": estimate_target_duration(doc.get("patterns", []), str(doc.get("action", ""))),
                "Take Profit": (doc.get("risk") or {}).get("take_profit"),
                "Stop Loss": (doc.get("risk") or {}).get("stop_loss"),
                "Analiz Notu": build_export_note(doc),
            }
        )

    columns = [
        "Hisse Kodu",
        "Mevcut Sinyal",
        "Hedef Süresi",
        "Take Profit",
        "Stop Loss",
        "Analiz Notu",
    ]
    dataframe = pd.DataFrame(rows, columns=columns)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Sinyaller")
        worksheet = writer.sheets["Sinyaller"]
        worksheet.column_dimensions["A"].width = 16
        worksheet.column_dimensions["B"].width = 16
        worksheet.column_dimensions["C"].width = 14
        worksheet.column_dimensions["D"].width = 18
        worksheet.column_dimensions["E"].width = 20
        worksheet.column_dimensions["F"].width = 36

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sinyal_raporu.xlsx"'},
    )


@api_router.post("/signals/analyze/{symbol}", response_model=SignalRecord)
async def analyze_symbol_on_demand(symbol: str):
    analyzed = await analyze_and_store_symbol(
        symbol,
        include_ai_summary=True,
        include_pattern_image=True,
        force_live_data=True,
        prefer_stream_consistency=True,
    )
    return sanitize_for_json(analyzed)


@api_router.get("/signals/{symbol}", response_model=SignalRecord)
async def get_signal_detail(symbol: str):
    document = await fetch_signal_document(symbol)
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")
    return sanitize_for_json(document)


@api_router.post("/signals/{symbol}/reanalyze", response_model=SignalRecord)
async def reanalyze_signal(symbol: str):
    document = await fetch_signal_document(symbol)
    if not document:
        analyzed = await analyze_and_store_symbol(
            symbol,
            include_ai_summary=True,
            include_pattern_image=True,
            force_live_data=False,
            prefer_stream_consistency=True,
        )
        return sanitize_for_json(analyzed)

    image_url = await ensure_pattern_visualization(document, force=False, require_strong=False)
    update_payload: dict[str, Any] = {
        "reanalyzed_at": now_iso(),
    }
    if image_url != document.get("pattern_image_url"):
        update_payload["pattern_image_url"] = image_url
        update_payload["pattern_image_updated_at"] = now_iso()

    if update_payload:
        await signals_collection.update_one({"symbol": document["symbol"]}, {"$set": update_payload})

    refreshed = await fetch_signal_document(document["symbol"])
    return sanitize_for_json(refreshed or document)


@api_router.post("/signals/{symbol}/visualize")
async def generate_signal_visual(symbol: str):
    document = await fetch_signal_document(symbol)
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")

    image_url = await ensure_pattern_visualization(document, force=True, require_strong=False)
    await signals_collection.update_one(
        {"symbol": document["symbol"]},
        {"$set": {"pattern_image_url": image_url, "pattern_image_updated_at": now_iso()}},
    )
    return {"symbol": document["symbol"], "pattern_image_url": image_url}


@api_router.post("/signals/{symbol}/auto-enrich")
async def auto_enrich_signal(symbol: str):
    document = await fetch_signal_document(symbol)
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")

    update_payload: dict[str, Any] = {}

    image_url = await ensure_pattern_visualization(document, force=not bool(document.get("pattern_image_url")), require_strong=False)
    update_payload["pattern_image_url"] = image_url
    update_payload["pattern_image_updated_at"] = now_iso()
    document["pattern_image_url"] = image_url

    should_refresh_summary = not document.get("ai_summary")
    if document.get("pattern_image_url") and document.get("ai_summary"):
        should_refresh_summary = document["pattern_image_url"] not in document["ai_summary"]
    if image_url is None and document.get("ai_summary") and "Formasyon görseli:" in document["ai_summary"]:
        should_refresh_summary = True

    if should_refresh_summary:
        summary = await generate_ai_summary(document)
        update_payload["ai_summary"] = summary
        update_payload["ai_summary_updated_at"] = now_iso()

    await signals_collection.update_one({"symbol": document["symbol"]}, {"$set": update_payload})

    refreshed = await fetch_signal_document(document["symbol"])
    return {
        "symbol": document["symbol"],
        "pattern_image_url": (refreshed or document).get("pattern_image_url"),
        "summary": (refreshed or document).get("ai_summary"),
    }


@api_router.post("/signals/{symbol}/explain")
async def explain_signal(symbol: str):
    document = await fetch_signal_document(symbol)
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")

    image_url = await ensure_pattern_visualization(document, force=True, require_strong=False)
    if image_url:
        document["pattern_image_url"] = image_url

    summary = await generate_ai_summary(document)
    update_payload = {
        "ai_summary": summary,
        "ai_summary_updated_at": now_iso(),
        "pattern_image_url": image_url,
        "pattern_image_updated_at": now_iso(),
    }

    await signals_collection.update_one({"symbol": document["symbol"]}, {"$set": update_payload})
    return {
        "symbol": document["symbol"],
        "summary": summary,
        "pattern_image_url": image_url,
    }


app.mount("/api/static", StaticFiles(directory=STATIC_ROOT), name="signal-static")
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    global scanner_task
    await get_market_universe(force_refresh=True)
    scanner_task = asyncio.create_task(scanner_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    global scanner_task
    if scanner_task:
        scanner_task.cancel()
    client.close()
