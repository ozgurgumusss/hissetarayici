import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import talib
import yfinance as yf
from dotenv import load_dotenv
from emergentintegrations.llm.chat import LlmChat, UserMessage
from fastapi import APIRouter, FastAPI, HTTPException, Query
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


class IndicatorsSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ema20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    rsi14: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    atr14: float | None = None
    golden_cross: bool = False
    death_cross: bool = False
    bearish_divergence: bool = False
    volume_confirmation: bool = False


class FundamentalSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pe: float | None = None
    pb: float | None = None
    sector: str = "Unknown"
    sector_pe_avg: float = 22.0
    current_ratio: float | None = None
    debt_to_equity: float | None = None
    eps_growth_qoq: float | None = None
    score: int = 0
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
    ai_summary: str | None = None
    updated_at: str
    price_history: list[PricePoint]


class ScannerState(BaseModel):
    running: bool
    last_run: str | None = None
    last_error: str | None = None
    last_duration_seconds: float | None = None
    last_scanned_count: int = 0


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


def detect_local_extrema(series: pd.Series, order: int = 4) -> tuple[list[int], list[int]]:
    values = series.to_numpy(dtype=float)
    if len(values) < order * 2 + 5:
        return [], []
    local_high = argrelextrema(values, np.greater, order=order)[0].tolist()
    local_low = argrelextrema(values, np.less, order=order)[0].tolist()
    return local_high, local_low


def detect_double_top_bottom(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 60)
    close_series = df["Close"]
    latest_close = float(close_series.iloc[-1])

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
                confirmed = latest_close < neckline
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
                        "volume_validated": True,
                        "detail": "Son 60 periyotta iki tepe %2 toleransla eşleşti, neckline kapanışla test edildi.",
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
                confirmed = latest_close > neckline
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
                        "volume_validated": True,
                        "detail": "Son 60 periyotta iki dip %2 toleransla eşleşti, neckline kapanışla yukarı kırıldı.",
                    }
                )
                break

    return patterns


def detect_head_shoulders(df: pd.DataFrame, highs: list[int], lows: list[int]) -> list[dict]:
    patterns: list[dict] = []
    lookback_start = max(0, len(df) - 120)
    close_series = df["Close"]
    volume_series = df["Volume"]
    latest_close = float(close_series.iloc[-1])
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

        left_trough = float(close_series.iloc[left:head + 1].min())
        right_trough = float(close_series.iloc[head:right + 1].min())
        neckline = (left_trough + right_trough) / 2
        left_volume = float(volume_series.iloc[max(left - 3, 0):left + 1].mean())
        right_volume = float(volume_series.iloc[max(right - 3, 0):right + 1].mean())
        breakout_volume = float(volume_series.iloc[-1])
        volume_validated = right_volume < left_volume and breakout_volume > volume_avg_20
        confirmed = latest_close < neckline and volume_validated

        patterns.append(
            {
                "name": "Head and Shoulders",
                "direction": "bearish",
                "confirmed": confirmed,
                "neckline": round(neckline, 4),
                "points": [
                    df.index[left].strftime("%Y-%m-%d"),
                    df.index[head].strftime("%Y-%m-%d"),
                    df.index[right].strftime("%Y-%m-%d"),
                ],
                "volume_validated": volume_validated,
                "detail": "Baş noktası omuzlardan %3+ yüksek; sağ omuz hacim düşüşü ve neckline kırılımında hacim artışı kontrol edildi.",
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

        left_peak = float(close_series.iloc[left:head + 1].max())
        right_peak = float(close_series.iloc[head:right + 1].max())
        neckline = (left_peak + right_peak) / 2
        left_volume = float(volume_series.iloc[max(left - 3, 0):left + 1].mean())
        right_volume = float(volume_series.iloc[max(right - 3, 0):right + 1].mean())
        breakout_volume = float(volume_series.iloc[-1])
        volume_validated = right_volume < left_volume and breakout_volume > volume_avg_20
        confirmed = latest_close > neckline and volume_validated

        patterns.append(
            {
                "name": "Inverse Head and Shoulders",
                "direction": "bullish",
                "confirmed": confirmed,
                "neckline": round(neckline, 4),
                "points": [
                    df.index[left].strftime("%Y-%m-%d"),
                    df.index[head].strftime("%Y-%m-%d"),
                    df.index[right].strftime("%Y-%m-%d"),
                ],
                "volume_validated": volume_validated,
                "detail": "Ters OBO algılandı; sağ omuz hacmi düşük ve neckline kırılımında hacim artışı doğrulandı.",
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
    return df


def build_risk_block(action: str, entry: float, atr: float | None) -> dict:
    if atr is None:
        return {
            "entry_price": round(entry, 4),
            "atr": None,
            "stop_loss": None,
            "take_profit": None,
            "risk_reward": None,
        }

    if action in {"AL", "GÜÇLÜ AL"}:
        stop_loss = entry - (1.5 * atr)
        take_profit = entry + (3.0 * atr)
    elif action in {"SAT", "GÜÇLÜ SAT"}:
        stop_loss = entry + (1.5 * atr)
        take_profit = entry - (3.0 * atr)
    else:
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
                "close": round(float(row["Close"]), 4),
                "volume": round(float(row["Volume"]), 2),
                "ema20": to_round(row.get("ema20"), 4),
                "sma50": to_round(row.get("sma50"), 4),
                "sma200": to_round(row.get("sma200"), 4),
                "rsi14": to_round(row.get("rsi14"), 4),
            }
        )
    return history


def fetch_symbol_ohlcv(symbol: str) -> pd.DataFrame | None:
    history = yf.download(
        tickers=symbol,
        period="2y",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
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
    info = yf.Ticker(symbol).info or {}
    pe = to_float(info.get("trailingPE") or info.get("forwardPE"))
    pb = to_float(info.get("priceToBook"))
    current_ratio = to_float(info.get("currentRatio"))
    debt_to_equity = to_float(info.get("debtToEquity"))
    eps_growth = to_float(info.get("earningsQuarterlyGrowth"))
    sector = str(info.get("sector") or "Unknown")
    sector_pe_avg = float(SECTOR_PE_BENCHMARK.get(sector, 22.0))

    score = 0
    notes: list[str] = []

    valuation_positive = pe is not None and pb is not None and pe < sector_pe_avg and pb < 3
    if valuation_positive:
        score += 10
        notes.append("Değerleme metrikleri sektör ortalamasına göre avantajlı.")
    else:
        notes.append("Değerleme metriklerinde nötr/negatif görünüm var.")

    health_positive = current_ratio is not None and current_ratio > 1.2 and (debt_to_equity is None or debt_to_equity < 180)
    if health_positive:
        score += 10
        notes.append("Likidite ve borç dengesi kabul edilebilir seviyede.")
    else:
        notes.append("Likidite veya borç dengesi ideal eşiklerin altında.")

    growth_positive = eps_growth is not None and eps_growth > 0
    if growth_positive:
        score += 10
        notes.append("Çeyreklik EPS büyümesi pozitif.")
    else:
        notes.append("EPS büyümesinde zayıflık gözleniyor.")

    return {
        "pe": to_round(pe, 4),
        "pb": to_round(pb, 4),
        "sector": sector,
        "sector_pe_avg": sector_pe_avg,
        "current_ratio": to_round(current_ratio, 4),
        "debt_to_equity": to_round(debt_to_equity, 4),
        "eps_growth_qoq": to_round(eps_growth, 4),
        "score": score,
        "notes": notes,
    }


async def get_fundamentals_with_cache(symbol: str) -> dict:
    cached = await fundamentals_collection.find_one({"symbol": symbol}, {"_id": 0})
    if cached and isinstance(cached.get("updated_at"), str):
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
            "sector": "Unknown",
            "sector_pe_avg": 22.0,
            "current_ratio": None,
            "debt_to_equity": None,
            "eps_growth_qoq": None,
            "score": 0,
            "notes": ["Temel veri alınamadı; puan nötr bırakıldı."],
        }


def build_signal(symbol: str, market: str, raw_df: pd.DataFrame, fundamentals: dict) -> dict:
    df = apply_indicators(raw_df)
    highs, lows = detect_local_extrema(df["Close"])

    pattern_candidates = detect_double_top_bottom(df, highs, lows)
    pattern_candidates.extend(detect_head_shoulders(df, highs, lows))
    confirmed_patterns = [pattern for pattern in pattern_candidates if pattern["confirmed"]]

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

    technical_points = 30 if confirmed_patterns else 0
    ma_points = 20 if (ema20 is not None and sma50 is not None and sma200 is not None and close > ema20 and sma50 > sma200) or golden_cross else 0
    volume_points = 20 if volume_confirmation else 0
    fundamental_points = int(max(0, min(30, fundamentals.get("score", 0))))

    bullish_score = technical_points + ma_points + volume_points + fundamental_points
    if bearish_divergence:
        bullish_score = max(0, bullish_score - 10)

    action = score_to_action(bullish_score)
    risk = build_risk_block(action, close, atr14)

    signal_doc = {
        "symbol": symbol,
        "market": market,
        "action": action,
        "bullish_score": int(max(0, min(100, bullish_score))),
        "score_breakdown": {
            "technical": technical_points,
            "moving_average": ma_points,
            "volume": volume_points,
            "fundamental": fundamental_points,
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
            "golden_cross": golden_cross,
            "death_cross": death_cross,
            "bearish_divergence": bearish_divergence,
            "volume_confirmation": volume_confirmation,
        },
        "fundamental": fundamentals,
        "risk": risk,
        "updated_at": now_iso(),
        "price_history": build_price_history(df),
        "ai_summary": None,
    }
    return signal_doc


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

        async def guarded_analysis(symbol: str, market: str):
            async with semaphore:
                return await analyze_symbol(symbol, market)

        for market, symbols in MARKET_UNIVERSE.items():
            for symbol in symbols:
                tasks.append(guarded_analysis(symbol, market))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        scanned_docs = [result for result in results if isinstance(result, dict)]

        if scanned_docs:
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
    patterns = signal_doc.get("patterns", [])
    confirmed = [pattern["name"] for pattern in patterns if pattern.get("confirmed")]
    pattern_text = ", ".join(confirmed) if confirmed else "Onaylı kırılım formasyonu henüz yok"

    return (
        f"1. **Teknik Durum:** {pattern_text}. RSI: {indicators.get('rsi14')} ve MACD: {indicators.get('macd')} seviyelerinde.\n"
        f"2. **Temel Durum:** P/E={fundamentals.get('pe')}, P/B={fundamentals.get('pb')}, Cari Oran={fundamentals.get('current_ratio')}.\n"
        f"3. **Aksiyon ve Risk:** {signal_doc.get('action')} sinyali. Giriş={risk.get('entry_price')}, Stop-Loss={risk.get('stop_loss')}, Take-Profit={risk.get('take_profit')}."
    )


async def generate_ai_summary(signal_doc: dict) -> str:
    if not EMERGENT_LLM_KEY:
        return build_local_summary(signal_doc)

    system_prompt = (
        "Sen bir yatırım danışmanısın. Sana verilen ham skorları ve formasyonları analiz ederek 3 maddelik bir özet çıkar.\n"
        "Format:\n"
        "1. **Teknik Durum:** (Örn: Fiyat 50 günlük ortalamasından sekti ve Çift Dip formasyonu onaylandı. RSI pozitif uyumsuzluk gösteriyor.)\n"
        "2. **Temel Durum:** (Örn: F/K oranı sektörünün %15 altında, son bilançoda net kar beklentileri aştı.)\n"
        "3. **Aksiyon ve Risk:** (Örn: X fiyatından AL sinyali üretildi. Risk yönetimi için Y seviyesine Stop-Loss, Z seviyesine Take-Profit konulmalıdır.)"
    )

    payload = {
        "symbol": signal_doc.get("symbol"),
        "action": signal_doc.get("action"),
        "bullish_score": signal_doc.get("bullish_score"),
        "score_breakdown": signal_doc.get("score_breakdown"),
        "patterns": signal_doc.get("patterns"),
        "indicators": signal_doc.get("indicators"),
        "fundamental": signal_doc.get("fundamental"),
        "risk": signal_doc.get("risk"),
    }

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"signal-summary-{signal_doc.get('symbol')}-{uuid.uuid4()}",
            system_message=system_prompt,
        ).with_model("gemini", "gemini-3-flash-preview")

        user_message = UserMessage(
            text=(
                "Aşağıdaki ham verileri analiz et ve sadece 3 maddelik formatta Türkçe yanıt üret.\n"
                f"Veri:\n{json.dumps(payload, ensure_ascii=False)}"
            )
        )

        response = await asyncio.wait_for(chat.send_message(user_message), timeout=30)
        return str(response).strip()
    except Exception as exc:
        logger.warning("AI summary failed for %s: %s", signal_doc.get("symbol"), exc)
        return build_local_summary(signal_doc)


@api_router.get("/")
async def root():
    return {
        "message": "Algorithmic signal engine is active",
        "scanner_interval_seconds": SCAN_INTERVAL_SECONDS,
        "markets": {"US": len(MARKET_UNIVERSE["US"]), "BIST": len(MARKET_UNIVERSE["BIST"])}
    }


@api_router.get("/config")
async def get_config():
    return {
        "refresh_seconds": SCAN_INTERVAL_SECONDS,
        "markets": {
            "US": MARKET_UNIVERSE["US"],
            "BIST": MARKET_UNIVERSE["BIST"],
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
    asyncio.create_task(run_scan(trigger="manual"))
    return {"status": "started", "message": "Manuel tarama başlatıldı"}


@api_router.get("/signals", response_model=list[SignalRecord])
async def get_signals(
    market: str = Query("ALL"),
    action: str = Query("ALL"),
    limit: int = Query(200, ge=1, le=400),
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
    return docs


@api_router.get("/signals/{symbol}", response_model=SignalRecord)
async def get_signal_detail(symbol: str):
    symbol_upper = symbol.upper()
    document = await signals_collection.find_one({"symbol": symbol_upper}, {"_id": 0})
    if document is None and not symbol_upper.endswith(".IS"):
        document = await signals_collection.find_one({"symbol": f"{symbol_upper}.IS"}, {"_id": 0})
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")
    return document


@api_router.post("/signals/{symbol}/explain")
async def explain_signal(symbol: str):
    symbol_upper = symbol.upper()
    document = await signals_collection.find_one({"symbol": symbol_upper}, {"_id": 0})
    if document is None and not symbol_upper.endswith(".IS"):
        document = await signals_collection.find_one({"symbol": f"{symbol_upper}.IS"}, {"_id": 0})
    if not document:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı")

    summary = await generate_ai_summary(document)
    await signals_collection.update_one(
        {"symbol": document["symbol"]},
        {"$set": {"ai_summary": summary, "ai_summary_updated_at": now_iso()}},
    )
    return {"symbol": document["symbol"], "summary": summary}


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
    scanner_task = asyncio.create_task(scanner_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    global scanner_task
    if scanner_task:
        scanner_task.cancel()
    client.close()