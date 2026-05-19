#!/usr/bin/env python3
"""
Daily Market Scanner (US equities by default)

- Reads tickers from watchlist.txt
- Downloads daily OHLCV (Open/High/Low/Close/Volume) via yfinance
- Computes:
  - SMA20 / SMA50 / SMA200 (Simple Moving Average)
  - RSI14 (Relative Strength Index)
  - 20-day average volume
- Applies filter rules and exports results to CSV

Note:
- This is a scanning utility, not financial advice.
- Data quality depends on the free data source.
"""

from __future__ import annotations

import os
import sys
import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Any
import smtplib
from email.message import EmailMessage

import numpy as np
import pandas as pd
import yfinance as yf


# ----------------------------
# Configuration
# ----------------------------

@dataclass
class ScanConfig:
    watchlist_path: str = "watchlist.txt"
    lookback_days: int = 365  # ~1 year of daily candles
    output_dir: str = "output"

    # Rule thresholds (tune these)
    rsi_min: float = 55.0
    volume_multiple_min: float = 1.5  # today's volume >= 1.5 * avg_volume_20

    # Trend rules
    require_uptrend_sma50_over_sma200: bool = True
    require_price_above_sma50: bool = True


CFG = ScanConfig()


# ----------------------------
# Indicators
# ----------------------------

def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """
    RSI using Wilder-like smoothing via exponential moving averages.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Exponential moving average (EMA) with alpha = 1/window is close to Wilder smoothing
    avg_gain = gain.ewm(alpha=1 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val


# ----------------------------
# IO helpers
# ----------------------------

def read_watchlist(path: str) -> List[str]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Watchlist file not found: {path}\n"
            f"Create it with one ticker per line (example: AAPL)."
        )
    tickers = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            t = line.strip().upper()
            if t and not t.startswith("#"):
                tickers.append(t)
    if not tickers:
        raise ValueError("Watchlist is empty. Add at least one ticker.")
    return sorted(list(set(tickers)))


def ensure_output_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


# ----------------------------
# Core scan logic
# ----------------------------

def fetch_history(ticker: str, lookback_days: int) -> pd.DataFrame:
    end = dt.datetime.now(dt.UTC).date()
    start = end - dt.timedelta(days=lookback_days)

    df = yf.download(
        tickers=ticker,
        start=start.isoformat(),
        end=(end + dt.timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance may return MultiIndex columns like (Price, Ticker) for single tickers.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Normalize column names for safety
    df = df.rename(columns=str.title)

    # Ensure expected columns
    expected = {"Open", "High", "Low", "Close", "Volume"}
    if not expected.issubset(set(df.columns)):
        return pd.DataFrame()

    df = df.dropna(subset=["Close", "Volume"])
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    vol = df["Volume"]

    df["Sma20"] = sma(close, 20)
    df["Sma50"] = sma(close, 50)
    df["Sma200"] = sma(close, 200)
    df["Rsi14"] = rsi(close, 14)
    df["AvgVol20"] = vol.rolling(window=20, min_periods=20).mean()
    return df


def passes_rules(latest: pd.Series, cfg: ScanConfig) -> Dict[str, Any] | None:
    """
    Returns a result dict if ticker passes scan rules; otherwise None.
    """
    # Require enough history for all indicators
    required_fields = ["Close", "Volume", "Sma50", "Sma200", "Rsi14", "AvgVol20"]
    if any(pd.isna(latest.get(k)) for k in required_fields):
        return None

    close = float(latest["Close"])
    volume = float(latest["Volume"])
    sma50 = float(latest["Sma50"])
    sma200 = float(latest["Sma200"])
    rsi14 = float(latest["Rsi14"])
    avgvol20 = float(latest["AvgVol20"])

    # Volume multiple
    vol_mult = volume / avgvol20 if avgvol20 > 0 else np.nan

    # Apply rules
    if cfg.require_uptrend_sma50_over_sma200 and not (sma50 > sma200):
        return None
    if cfg.require_price_above_sma50 and not (close > sma50):
        return None
    if not (rsi14 >= cfg.rsi_min):
        return None
    if not (vol_mult >= cfg.volume_multiple_min):
        return None

    return {
        "close": close,
        "volume": volume,
        "avg_volume_20": avgvol20,
        "volume_multiple": vol_mult,
        "sma50": sma50,
        "sma200": sma200,
        "rsi14": rsi14,
    }


def run_scan(cfg: ScanConfig) -> pd.DataFrame:
    tickers = read_watchlist(cfg.watchlist_path)
    ensure_output_dir(cfg.output_dir)

    results = []
    failures = 0

    for t in tickers:
        try:
            df = fetch_history(t, cfg.lookback_days)
            if df.empty or len(df) < 210:
                failures += 1
                continue

            df = compute_features(df)
            latest = df.iloc[-1]

            hit = passes_rules(latest, cfg)
            if hit:
                results.append({"ticker": t, **hit})

        except Exception as e:
            failures += 1
            # Keep going; scanners should be resilient
            print(f"[WARN] {t}: {e}", file=sys.stderr)

    out = pd.DataFrame(results)
    if not out.empty:
        out = out.sort_values(by=["volume_multiple", "rsi14"], ascending=False)

    print(f"Scan complete. Watchlist={len(tickers)} hits={len(out)} failures/insufficient_data={failures}")
    return out


def maybe_send_email(df_hits: pd.DataFrame, out_path: str) -> None:
    smtp_host = os.getenv("SCANNER_SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SCANNER_SMTP_PORT", "587"))
    smtp_user = os.getenv("SCANNER_SMTP_USER", "").strip()
    smtp_pass = os.getenv("SCANNER_SMTP_PASS", "").strip()
    from_addr = os.getenv("SCANNER_FROM_EMAIL", smtp_user).strip()
    to_addr = os.getenv("SCANNER_TO_EMAIL", "saratheas@gmail.com").strip()

    if not all([smtp_host, smtp_user, smtp_pass, from_addr, to_addr]):
        print("Email not sent (missing SMTP env vars).")
        return

    subject = f"Daily Market Scanner - {dt.datetime.now().date().isoformat()}"
    if df_hits.empty:
        body = "No matches found today.\n\n" f"CSV: {os.path.abspath(out_path)}"
    else:
        preview = df_hits.head(10).to_string(index=False)
        body = (
            f"Matches found: {len(df_hits)}\n\n"
            "Top results:\n"
            f"{preview}\n\n"
            f"CSV: {os.path.abspath(out_path)}"
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(smtp_user, smtp_pass)
        smtp.send_message(msg)

    print(f"Email sent to {to_addr}")


def main() -> None:
    today = dt.datetime.now().date().isoformat()
    df_hits = run_scan(CFG)

    out_path = os.path.join(CFG.output_dir, f"scan_{today}.csv")
    df_hits.to_csv(out_path, index=False)

    if df_hits.empty:
        print("No matches today.")
    else:
        print("\nTop matches:")
        print(df_hits.head(15).to_string(index=False))
        print(f"\nSaved: {out_path}")

    try:
        maybe_send_email(df_hits, out_path)
    except Exception as e:
        print(f"[WARN] Email failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
