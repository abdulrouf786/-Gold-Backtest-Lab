from __future__ import annotations
import os, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
OUT = Path("reports")
OUT.mkdir(exist_ok=True)
SYMBOL = os.getenv("SYMBOL", "GC=F")
PERIOD = os.getenv("PERIOD", "60d")
INTERVAL = os.getenv("INTERVAL", "15m")
RR = float(os.getenv("RR", "2.0"))
RISK_ATR = float(os.getenv("RISK_ATR", "1.5"))

STRATEGIES = [
    "Sweep_MSS_FVG", "Sweep_MSS_OB", "Failed_Breakout",
    "Sweep_Displacement_FVG", "Asian_Range_Sweep"
]

def get_data():
    df = yf.download(SYMBOL, period=PERIOD, interval=INTERVAL, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError(f"No Yahoo data for {SYMBOL} {PERIOD} {INTERVAL}. Try PERIOD=730d INTERVAL=1h.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.title)
    needed = ["Open", "High", "Low", "Close"]
    df = df[needed].dropna().copy()
    df.index = pd.to_datetime(df.index)
    return df

def indicators(df):
    d = df.copy()
    d["atr"] = (d["High"] - d["Low"]).rolling(14).mean()
    d["prev_high"] = d["High"].rolling(20).max().shift(1)
    d["prev_low"] = d["Low"].rolling(20).min().shift(1)
    d["swing_high"] = d["High"].rolling(5, center=True).max()
    d["swing_low"] = d["Low"].rolling(5, center=True).min()
    d["mss_up"] = d["Close"] > d["High"].rolling(10).max().shift(1)
    d["mss_dn"] = d["Close"] < d["Low"].rolling(10).min().shift(1)
    # Three-candle imbalance proxy
    d["fvg_up"] = d["Low"] > d["High"].shift(2)
    d["fvg_dn"] = d["High"] < d["Low"].shift(2)
    d["bull_sweep"] = (d["Low"] < d["prev_low"]) & (d["Close"] > d["prev_low"])
    d["bear_sweep"] = (d["High"] > d["prev_high"]) & (d["Close"] < d["prev_high"])
    body = (d["Close"] - d["Open"]).abs()
    d["displace"] = body > (d["atr"] * 1.2)
    # Failed breakout: outside prior range, closes back inside
    d["fail_low"] = (d["Low"] < d["prev_low"]) & (d["Close"] > d["prev_low"])
    d["fail_high"] = (d["High"] > d["prev_high"]) & (d["Close"] < d["prev_high"])
    # Time-of-day Asian range proxy (UTC); only use prior Asian range for same day
    idx = d.index
    d["utc_hour"] = idx.hour
    d["utc_day"] = idx.date
    asian = d[d["utc_hour"].between(0, 6)].groupby("utc_day").agg(asian_high=("High","max"), asian_low=("Low","min"))
    d = d.join(asian, on="utc_day")
    d["asian_sweep_low"] = (d["Low"] < d["asian_low"]) & (d["Close"] > d["asian_low"]) & d["utc_hour"].between(7, 20)
    d["asian_sweep_high"] = (d["High"] > d["asian_high"]) & (d["Close"] < d["asian_high"]) & d["utc_hour"].between(7, 20)
    return d

def signal_at(d, i, strategy):
    r = d.iloc[i]
    prev = d.iloc[i-1]
    if not np.isfinite(r["atr"]) or r["atr"] <= 0: return None
    long = short = False
    if strategy == "Sweep_MSS_FVG":
        long = bool(r["bull_sweep"] and r["mss_up"] and r["fvg_up"])
        short = bool(r["bear_sweep"] and r["mss_dn"] and r["fvg_dn"])
    elif strategy == "Sweep_MSS_OB":
        # OB proxy: previous opposite candle, sweep + structure break
        long = bool(r["bull_sweep"] and r["mss_up"] and prev["Close"] < prev["Open"])
        short = bool(r["bear_sweep"] and r["mss_dn"] and prev["Close"] > prev["Open"])
    elif strategy == "Failed_Breakout":
        long = bool(r["fail_low"] and r["mss_up"])
        short = bool(r["fail_high"] and r["mss_dn"])
    elif strategy == "Sweep_Displacement_FVG":
        long = bool(r["bull_sweep"] and r["displace"] and r["fvg_up"])
        short = bool(r["bear_sweep"] and r["displace"] and r["fvg_dn"])
    elif strategy == "Asian_Range_Sweep":
        long = bool(r["asian_sweep_low"] and r["mss_up"])
        short = bool(r["asian_sweep_high"] and r["mss_dn"])
    if long and not short: return "LONG"
    if short and not long: return "SHORT"
    return None

def run_backtest(d, strategy):
    trades=[]
    pos=None
    # signals at candle close; enter at next candle open to avoid look-ahead
    for i in range(30, len(d)-1):
        r=d.iloc[i]; nxt=d.iloc[i+1]
        if pos:
            hit_sl = (r["Low"] <= pos["sl"]) if pos["side"]=="LONG" else (r["High"] >= pos["sl"])
            hit_tp = (r["High"] >= pos["tp"]) if pos["side"]=="LONG" else (r["Low"] <= pos["tp"])
            if hit_sl or hit_tp:
                # conservative if both touched in same bar
                exit_price = pos["sl"] if hit_sl else pos["tp"]
                outcome = -1.0 if hit_sl else RR
                trades.append({**pos, "exit_time": d.index[i], "exit_price": exit_price,
                               "R": outcome, "result": "SL" if hit_sl else "TP"})
                pos=None
        if pos is None:
            side=signal_at(d,i,strategy)
            if not side: continue
            entry=float(nxt["Open"]); atr=float(r["atr"])
            risk=RISK_ATR*atr
            if side=="LONG":
                sl=entry-risk; tp=entry+RR*risk
            else:
                sl=entry+risk; tp=entry-RR*risk
            pos={"strategy":strategy,"side":side,"signal_time":d.index[i],
                 "entry_time":d.index[i+1],"entry":entry,"sl":sl,"tp":tp}
    if pos:
        last=d.iloc[-1]
        trades.append({**pos,"exit_time":d.index[-1],"exit_price":float(last["Close"]),
                       "R":float((last["Close"]-pos["entry"])/(pos["entry"]-pos["sl"])) if pos["side"]=="LONG" else float((pos["entry"]-last["Close"])/(pos["sl"]-pos["entry"])),
                       "result":"EOD"})
    return pd.DataFrame(trades)

def metrics(t, strategy):
    if t.empty:
        return {"strategy":strategy,"trades":0,"win_rate_pct":0,"net_R":0,"profit_factor":0,"max_drawdown_R":0}
    r=t["R"].astype(float)
    wins=r[r>0].sum(); losses=abs(r[r<0].sum())
    equity=r.cumsum(); dd=(equity-equity.cummax()).min()
    return {"strategy":strategy,"trades":len(t),"win_rate_pct":round((r>0).mean()*100,2),
            "net_R":round(r.sum(),2),"profit_factor":round(wins/losses,2) if losses else float("inf"),
            "max_drawdown_R":round(float(dd),2)}

def main():
    print(f"Downloading {SYMBOL} {PERIOD} {INTERVAL} ...")
    data=indicators(get_data())
    all_trades=[]; rows=[]
    for strategy in STRATEGIES:
        trades=run_backtest(data,strategy)
        rows.append(metrics(trades,strategy))
        if not trades.empty: all_trades.append(trades)
    summary=pd.DataFrame(rows).sort_values(["net_R","profit_factor"],ascending=False)
    summary.to_csv(OUT/"strategy_comparison.csv",index=False)
    if all_trades: pd.concat(all_trades,ignore_index=True).to_csv(OUT/"trades.csv",index=False)
    else: pd.DataFrame().to_csv(OUT/"trades.csv",index=False)
    print(summary.to_string(index=False))
    print(f"\nSaved reports under {OUT}/")
if __name__=="__main__": main()
