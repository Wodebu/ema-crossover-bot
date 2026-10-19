import os
import time
import traceback
import asyncio
import requests
import pandas as pd
from telegram import Bot
from telegram.constants import ParseMode

# ----- SETTINGS -----
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")

SYMBOL    = "BTC/USDT"
TIMEFRAME = "15min"

RED_EMA_LEN   = 11
GREEN_EMA_LEN = 5
EMA_SMOOTHING = 9
MIN_SEPARATION_ATR = 0.10
SWING_LOOKBACK = 5
POLL_SECONDS = 120

# ----- DATA FEED -----
def get_candles(symbol: str, interval: str, outputsize: int = 200) -> pd.DataFrame:
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
    }
    r = requests.get(url, params=params, timeout=15).json()
    if "values" not in r:
        raise RuntimeError(f"TwelveData error: {r}")
    df = pd.DataFrame(r["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    return df

# ----- INDICATORS -----
def ema(series: pd.Series, length: int, smoothing: int = 9) -> pd.Series:
    e = series.ewm(span=length, adjust=False).mean()
    return e.rolling(window=smoothing, min_periods=1).mean()

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(length).mean()

def find_swing_low(df: pd.DataFrame, lookback: int = 5) -> float:
    lows = df["low"].values
    for i in range(len(lows) - lookback - 1, lookback - 1, -1):
        window = lows[i - lookback:i + lookback + 1]
        if lows[i] == window.min():
            return float(lows[i])
    return float(df["low"].iloc[-lookback:].min())

def find_swing_high(df: pd.DataFrame, lookback: int = 5) -> float:
    highs = df["high"].values
    for i in range(len(highs) - lookback - 1, lookback - 1, -1):
        window = highs[i - lookback:i + lookback + 1]
        if highs[i] == window.max():
            return float(highs[i])
    return float(df["high"].iloc[-lookback:].max())

# ----- STRATEGY -----
class Strategy:
    def __init__(self):
        self.last_cross_idx = None
        self.traded = False
        self.position = None

    def compute(self, df):
        df = df.copy()
        df["red"]   = ema(df["close"], RED_EMA_LEN, EMA_SMOOTHING)
        df["green"] = ema(df["close"], GREEN_EMA_LEN, EMA_SMOOTHING)
        df["atr"]   = atr(df, 14)
        df["gap"]   = (df["green"] - df["red"]).abs()
        return df

    def detect_crossover(self, df):
        g, r = df["green"].values, df["red"].values
        for i in range(len(df) - 1, 1, -1):
            if (g[i-1] > r[i-1]) != (g[i] > r[i]):
                return ("BUY" if g[i] > r[i] else "SELL"), i
        return None, None

    def separation_ok(self, df, idx):
        gap = df["gap"].iloc[idx]
        a   = df["atr"].iloc[idx]
        if pd.isna(a) or a == 0:
            return False
        return gap >= MIN_SEPARATION_ATR * a

    def evaluate(self, df):
        df = self.compute(df)
        direction, cross_idx = self.detect_crossover(df)
        if direction is None: return None
        if cross_idx >= len(df) - 1: return None
        if self.last_cross_idx == cross_idx and self.traded: return None
        
        latest = len(df) - 1
        if not self.separation_ok(df, latest): return None
        if direction == "BUY" and not (df["green"].iloc[latest] > df["red"].iloc[latest]): return None
        if direction == "SELL" and not (df["green"].iloc[latest] < df["red"].iloc[latest]): return None

        sl = find_swing_low(df, SWING_LOOKBACK) if direction == "BUY" else find_swing_high(df, SWING_LOOKBACK)

        self.last_cross_idx = cross_idx
        self.traded = True
        self.position = direction

        return {
            "side": direction,
            "entry": float(df["close"].iloc[latest]),
            "stop_loss": sl,
            "candle_time": str(df.index[latest]),
        }

    def check_exit(self, df):
        if self.position is None: return None
        df = self.compute(df)
        direction, _ = self.detect_crossover(df)
        if direction and direction != self.position:
            self.position = None
            self.traded = False
            self.last_cross_idx = None
            return f"EXIT_{direction}"
        return None

# ----- TELEGRAM -----
async def send_message_async(text: str):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode=ParseMode.MARKDOWN)

def send(text: str):
    try:
        asyncio.run(send_message_async(text))
    except Exception as e:
        print("Telegram error:", e)

def format_signal(sig, symbol):
    emoji = "🟢 *BUY*" if sig["side"] == "BUY" else "🔴 *SELL*"
    return f"{emoji} — {symbol} M15\nEntry: `{sig['entry']:.2f}`\nSL:    `{sig['stop_loss']:.2f}`\nCandle: `{sig['candle_time']}`"

# ----- MAIN LOOP -----
def main():
    print("Starting bot...")
    send(f"🤖 *EMA Bot online*\n`{SYMBOL}` M15\nSignals only.")
    strat = Strategy()
    last_signal_candle = None

    while True:
        try:
            df = get_candles(SYMBOL, TIMEFRAME)
            if df is None or len(df) < 50:
                time.sleep(POLL_SECONDS)
                continue

            exit_sig = strat.check_exit(df)
            if exit_sig:
                send(f"🚪 *{exit_sig}* on `{SYMBOL}`")

            sig = strat.evaluate(df)
            if sig and sig["candle_time"] != last_signal_candle:
                last_signal_candle = sig["candle_time"]
                send(format_signal(sig, SYMBOL))
                print("Signal:", sig)

        except Exception:
            print(traceback.format_exc())
            time.sleep(10)
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
