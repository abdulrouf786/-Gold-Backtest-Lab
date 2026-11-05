from __future__ import annotations
import os, time, json, urllib.request, urllib.parse
from pathlib import Path
import pandas as pd
import numpy as np

# Public Binance Spot candles; PAXGUSDT is a gold-backed token, NOT broker XAUUSD.
SYMBOL=os.getenv("SYMBOL","PAXGUSDT")
INTERVAL=os.getenv("INTERVAL","15m")
DAYS=int(os.getenv("DAYS","60"))
RR=float(os.getenv("RR","2.0"))
ATR_MULT=float(os.getenv("ATR_MULT","1.5"))
OUT=Path("reports"); OUT.mkdir(exist_ok=True)
BASE="https://api.binance.com/api/v3/klines"
STRATEGIES=["Sweep_MSS_FVG","Sweep_MSS_OB","Failed_Breakout","Sweep_Displacement_FVG","Trend_Pullback"]

def download():
    interval_ms={"1m":60000,"3m":180000,"5m":300000,"15m":900000,"30m":1800000,"1h":3600000,"4h":14400000,"1d":86400000}
    if INTERVAL not in interval_ms: raise ValueError("Unsupported interval")
    end=int(time.time()*1000); start=end-DAYS*86400000; rows=[]
    while start<end:
        q=urllib.parse.urlencode({"symbol":SYMBOL,"interval":INTERVAL,"startTime":start,"endTime":end,"limit":1000})
        req=urllib.request.Request(BASE+"?"+q,headers={"User-Agent":"GoldBacktestLab/1.0"})
        with urllib.request.urlopen(req,timeout=30) as r: batch=json.loads(r.read().decode())
        if not batch: break
        rows.extend(batch); start=int(batch[-1][0])+interval_ms[INTERVAL]
        if len(batch)<1000: break
        time.sleep(.15)
    if not rows: raise RuntimeError(f"No Binance candles returned for {SYMBOL} {INTERVAL}. Check symbol/interval.")
    df=pd.DataFrame(rows,columns=["time","Open","High","Low","Close","Volume","close_time","qav","trades","tbbav","tbqav","ignore"])
    df["time"]=pd.to_datetime(df["time"],unit="ms",utc=True)
    for c in ["Open","High","Low","Close","Volume"]: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.set_index("time")[["Open","High","Low","Close","Volume"]].dropna().sort_index()
    return df[~df.index.duplicated(keep="last")]

def indicators(df):
    d=df.copy()
    d["atr"]=(d["High"]-d["Low"]).rolling(14).mean()
    d["prior_hi"]=d["High"].rolling(20).max().shift(1)
    d["prior_lo"]=d["Low"].rolling(20).min().shift(1)
    d["mss_hi"]=d["High"].rolling(10).max().shift(1)
    d["mss_lo"]=d["Low"].rolling(10).min().shift(1)
    d["fvg_up"]=d["Low"]>d["High"].shift(2)
    d["fvg_dn"]=d["High"]<d["Low"].shift(2)
    d["bull_sweep"]=(d["Low"]<d["prior_lo"])&(d["Close"]>d["prior_lo"])
    d["bear_sweep"]=(d["High"]>d["prior_hi"])&(d["Close"]<d["prior_hi"])
    d["mss_up"]=d["Close"]>d["mss_hi"]; d["mss_dn"]=d["Close"]<d["mss_lo"]
    d["displace"]=(d["Close"]-d["Open"]).abs()>d["atr"]*1.2
    d["ema50"]=d["Close"].ewm(span=50,adjust=False).mean()
    d["ema200"]=d["Close"].ewm(span=200,adjust=False).mean()
    d["fail_lo"]=d["bull_sweep"]; d["fail_hi"]=d["bear_sweep"]
    return d

def signal(d,i,strategy):
    r=d.iloc[i]; p=d.iloc[i-1]
    if not np.isfinite(r["atr"]) or r["atr"]<=0: return None
    L=S=False
    if strategy=="Sweep_MSS_FVG": L=r.bull_sweep and r.mss_up and r.fvg_up; S=r.bear_sweep and r.mss_dn and r.fvg_dn
    elif strategy=="Sweep_MSS_OB": L=r.bull_sweep and r.mss_up and p.Close<p.Open; S=r.bear_sweep and r.mss_dn and p.Close>p.Open
    elif strategy=="Failed_Breakout": L=r.fail_lo and r.mss_up; S=r.fail_hi and r.mss_dn
    elif strategy=="Sweep_Displacement_FVG": L=r.bull_sweep and r.displace and r.fvg_up; S=r.bear_sweep and r.displace and r.fvg_dn
    elif strategy=="Trend_Pullback": L=r.Close>r.ema200 and r.ema50>r.ema200 and r.Close>r.Open and r.Low<=r.ema50; S=r.Close<r.ema200 and r.ema50<r.ema200 and r.Close<r.Open and r.High>=r.ema50
    if bool(L) and not bool(S): return "LONG"
    if bool(S) and not bool(L): return "SHORT"
    return None

def backtest(d,strategy):
    trades=[]; pos=None
    for i in range(210,len(d)-1):
        r=d.iloc[i]
        if pos:
            slhit=(r.Low<=pos["sl"]) if pos["side"]=="LONG" else (r.High>=pos["sl"])
            tphit=(r.High>=pos["tp"]) if pos["side"]=="LONG" else (r.Low<=pos["tp"])
            if slhit or tphit:
                # Conservative tie-break: if SL and TP are touched in same candle, count SL.
                result="SL" if slhit else "TP"; R=-1.0 if slhit else RR
                trades.append({**pos,"exit_time":d.index[i].isoformat(),"exit":pos["sl"] if slhit else pos["tp"],"R":R,"result":result})
                pos=None
        if pos is None:
            side=signal(d,i,strategy)
            if side:
                entry=float(d.iloc[i+1].Open); risk=float(r.atr)*ATR_MULT
                if risk<=0: continue
                sl=entry-risk if side=="LONG" else entry+risk
                tp=entry+RR*risk if side=="LONG" else entry-RR*risk
                pos={"strategy":strategy,"side":side,"signal_time":d.index[i].isoformat(),"entry_time":d.index[i+1].name.isoformat(),"entry":entry,"sl":sl,"tp":tp}
    if pos:
        last=d.iloc[-1]; R=((last.Close-pos["entry"])/(pos["entry"]-pos["sl"])) if pos["side"]=="LONG" else ((pos["entry"]-last.Close)/(pos["sl"]-pos["entry"]))
        trades.append({**pos,"exit_time":d.index[-1].isoformat(),"exit":float(last.Close),"R":float(R),"result":"OPEN/EOD"})
    return pd.DataFrame(trades)

def stats(t,s):
    if t.empty: return {"strategy":s,"trades":0,"wins":0,"losses":0,"win_rate_pct":0,"net_R":0,"profit_factor":0,"max_drawdown_R":0}
    r=t.R.astype(float); wins=r[r>0].sum(); losses=abs(r[r<0].sum()); eq=r.cumsum(); dd=(eq-eq.cummax()).min()
    return {"strategy":s,"trades":len(t),"wins":int((r>0).sum()),"losses":int((r<0).sum()),"win_rate_pct":round((r>0).mean()*100,2),"net_R":round(r.sum(),2),"profit_factor":round(wins/losses,2) if losses else "inf","max_drawdown_R":round(float(dd),2)}

def main():
    print(f"Fetching Binance {SYMBOL} {INTERVAL} candles for ~{DAYS} days")
    d=indicators(download()); results=[]; alltrades=[]
    for s in STRATEGIES:
        t=backtest(d,s); results.append(stats(t,s))
        if not t.empty: alltrades.append(t)
    summary=pd.DataFrame(results).sort_values("net_R",ascending=False)
    summary.to_csv(OUT/"strategy_comparison.csv",index=False)
    (pd.concat(alltrades,ignore_index=True) if alltrades else pd.DataFrame()).to_csv(OUT/"trades.csv",index=False)
    print(summary.to_string(index=False))
    print(f"\nCandles: {len(d)} | First: {d.index[0]} | Last: {d.index[-1]}")
    print("Saved reports to reports/")
if __name__=="__main__": main()
