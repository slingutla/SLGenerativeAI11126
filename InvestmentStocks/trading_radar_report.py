import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ---------------------------
# Configuration
# ---------------------------

# Start small; scale after verifying stability.
TICKERS = [
    "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","AMD","TSM","PLTR", # Tech + AI leaders
    "XOM","CVX","MPC",                                                           # Energy (watch for OPEC+ news)
    "LLY","UNH","COST","HD","CAT","LOW",                                         # Diverse blue-chips with strong recent momentum
    "JPM","V","MA","BA",                                                         # Financials + Industrials  
    "NFLX",                                                                      # Consumer Discretionary (streaming recovery + content bets)
    "GD","LMT","RTX","NOC","SNA","HII","TXT","SWK","DOV","ITW",                  # Defense / Industrials (watch for geopolitical catalysts)
    "GDX","NEM","GOLD"                                                           # Gold miners (hedge against macro uncertainty + inflation fears)
]

# Sector ETF (Exchange-Traded Fund) proxies (U.S.)
SECTOR_ETFS = {
    "Technology": "XLK",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

LOOKBACK_DAYS = 120
MA_DAYS = 20                      # Moving Average (MA)
VOL_AVG_DAYS = 30
ATR_DAYS = 14                     # Average True Range (ATR)
TOP_N = 10                          # Number of top candidates to display

# Risk policy (edit to taste)
STOP_ATR_MULT = 1.5               # Stop distance = 1.5 × ATR
TARGET_ATR_MULT = 2.5             # Target distance = 2.5 × ATR

# Volume spike threshold (institutional participation heuristic)
VOL_SPIKE_MIN = 1.5

# ---------------------------
# Helpers
# ---------------------------

def download_ohlcv(ticker: str, lookback_days: int) -> pd.DataFrame:
    df = yf.download(ticker, period=f"{lookback_days}d", interval="1d", progress=False)
    if df is None or df.empty:
        return pd.DataFrame()
    # Standardize columns if yfinance returns multi-index (rare but possible)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open","High","Low","Close","Volume"]].dropna()

def compute_atr(df: pd.DataFrame, atr_days: int = 14) -> float:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(atr_days).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else float("nan")

def percent_return(series: pd.Series, periods: int) -> float:
    if len(series) <= periods:
        return float("nan")
    return float((series.iloc[-1] / series.iloc[-(periods+1)] - 1.0) * 100.0)

def score_candidate(df: pd.DataFrame) -> dict | None:
    # Need enough data
    min_len = max(MA_DAYS, VOL_AVG_DAYS, ATR_DAYS) + 6
    if len(df) < min_len:
        return None

    close = df["Close"]
    volume = df["Volume"]

    ma20 = close.rolling(MA_DAYS).mean().iloc[-1]
    vol30 = volume.rolling(VOL_AVG_DAYS).mean().iloc[-1]

    last_close = close.iloc[-1]
    ret5 = percent_return(close, 5)      # 5-day return in %
    ret20 = percent_return(close, 20)    # 20-day return in %

    vol_spike = float(volume.iloc[-1] / vol30) if vol30 and vol30 > 0 else float("nan")
    atr14 = compute_atr(df, ATR_DAYS)

    # Filters: momentum + participation + basic sanity
    if any(pd.isna(x) for x in [ma20, ret5, vol_spike, atr14]):
        return None
    if not (last_close > ma20 and ret5 > 0 and vol_spike >= VOL_SPIKE_MIN and atr14 > 0):
        return None

    # Scoring: simple weighted blend (tune later)
    # ret5 drives short-term, ret20 adds trend confirmation, vol_spike adds conviction
    score = (ret5 * 0.55) + (ret20 * 0.25) + (min(vol_spike, 5.0) * 10.0 * 0.20)

    # Levels using ATR (Average True Range)
    entry = last_close
    stop = entry - (STOP_ATR_MULT * atr14)
    target = entry + (TARGET_ATR_MULT * atr14)

    return {
        "last_close": float(last_close),
        "MA20": float(ma20),
        "ret5_pct": float(ret5),
        "ret20_pct": float(ret20),
        "vol_spike_x": float(vol_spike),
        "ATR14": float(atr14),
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "score": float(score),
    }

def sector_leaderboard() -> pd.DataFrame:
    rows = []
    for sector, etf in SECTOR_ETFS.items():
        df = download_ohlcv(etf, LOOKBACK_DAYS)
        if df.empty:
            continue
        close = df["Close"]
        rows.append({
            "sector": sector,
            "ticker": etf,
            "ret5_pct": percent_return(close, 5),
            "ret20_pct": percent_return(close, 20),
        })
    out = pd.DataFrame(rows).dropna()
    if out.empty:
        return out
    # rank: short-term + medium-term blend
    out["rank_score"] = out["ret5_pct"] * 0.6 + out["ret20_pct"] * 0.4
    return out.sort_values("rank_score", ascending=False)

def catalyst_summary_placeholder(ticker: str) -> str:
    # Placeholder: plug in a News API later (Finnhub / Polygon / Benzinga / etc.)
    # Return a human-readable single line.
    return "Catalyst: (optional) integrate a News API (Application Programming Interface) for headlines + sentiment."

# ---------------------------
# Main
# ---------------------------

def main():
    stamp = datetime.now().strftime("%Y-%m-%d")
    print(f"\n=== Daily Trading Radar Report ({stamp}) ===\n")

    # Sector leaderboard
    sec = sector_leaderboard()
    if sec.empty:
        print("Sector leaderboard: unavailable (data fetch issue).\n")
    else:
        print("Sector leaderboard (top 10):")
        print(sec.head(10)[["sector","ticker","ret5_pct","ret20_pct","rank_score"]].to_string(index=False))
        print()

    # Stock candidates
    results = []
    for t in TICKERS:
        df = download_ohlcv(t, LOOKBACK_DAYS)
        if df.empty:
            continue
        metrics = score_candidate(df)
        if metrics:
            results.append({"ticker": t, **metrics})

    out = pd.DataFrame(results)
    if out.empty:
        print("No candidates met filters today (momentum + volume spike + above MA (Moving Average)).")
        return

    out = out.sort_values("score", ascending=False)

    top = out.head(TOP_N).copy()
    top["catalyst_summary"] = top["ticker"].apply(catalyst_summary_placeholder)

    cols = [
        "ticker","score","last_close","ret5_pct","ret20_pct","vol_spike_x",
        "ATR14","entry","stop","target","catalyst_summary"
    ]

    print("Top short-term candidates:")
    print(top[cols].to_string(index=False))

    # Save outputs
    file_base = datetime.now().strftime("%Y%m%d")
    all_file = f"radar_all_{file_base}.csv"
    top_file = f"radar_top_{file_base}.csv"
    out.to_csv(all_file, index=False)
    top[cols].to_csv(top_file, index=False)

    print(f"\nSaved: {top_file}")
    print(f"Saved: {all_file}")

if __name__ == "__main__":
    main()