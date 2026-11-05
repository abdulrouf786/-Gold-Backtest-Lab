import os, json, urllib.request, urllib.parse, csv
from datetime import datetime, timezone
from pathlib import Path

# 1-minute candle directional bias. This is a heuristic score, NOT a calibrated probability.
INST=os.getenv("OKX_INST_ID","PAXG-USDT")
TOKEN=os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN","")
CHAT=os.getenv("TELEGRAM_CHAT_ID","")
URL="https://www.okx.com/api/v5/market/candles"

def candles():
    q=urllib.parse.urlencode({"instId":INST,"bar":"1m","limit":"120"})
    req=urllib.request.Request(URL+"?"+q,headers={"User-Agent":"GoldCandlePredictor/1.0"})
    with urllib.request.urlopen(req,timeout=20) as r: data=json.loads(r.read().decode())
    if data.get("code")!="0" or not data.get("data"): raise RuntimeError("OKX candle API returned no data")
    rows=list(reversed(data["data"]))
    # OKX fields: timestamp, open, high, low, close, volume, ...
    return [{"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"confirm":x[8]} for x in rows]

def ema(vals,n):
    a=2/(n+1); out=vals[0]
    for x in vals[1:]: out=a*x+(1-a)*out
    return out

def rsi(vals,n=14):
    dif=[vals[i]-vals[i-1] for i in range(1,len(vals))]
    up=sum(max(x,0) for x in dif[-n:])/n
    dn=sum(max(-x,0) for x in dif[-n:])/n
    return 100 if dn==0 else 100-100/(1+up/dn)

def predict():
    d=candles()
    # Use only completed candles; discard current forming bar if OKX marks it unconfirmed.
    d=[x for x in d if x["confirm"]=="1"]
    if len(d)<50: raise RuntimeError("Not enough completed 1m candles")
    c=[x["c"] for x in d]; last=d[-1]; prev=d[-2]
    e9=ema(c[-40:],9); e21=ema(c[-60:],21); rr=rsi(c)
    score=0; reasons=[]
    if e9>e21: score+=1; reasons.append("EMA9 above EMA21")
    else: score-=1; reasons.append("EMA9 below EMA21")
    if last["c"]>last["o"]: score+=1; reasons.append("last candle bullish")
    elif last["c"]<last["o"]: score-=1; reasons.append("last candle bearish")
    if last["c"]>prev["c"]: score+=1; reasons.append("close rising")
    elif last["c"]<prev["c"]: score-=1; reasons.append("close falling")
    if rr>=55: score+=1; reasons.append(f"RSI {rr:.1f} bullish momentum")
    elif rr<=45: score-=1; reasons.append(f"RSI {rr:.1f} bearish momentum")
    else: reasons.append(f"RSI {rr:.1f} neutral")
    # Require at least 3 of 4 aligned votes; otherwise abstain.
    if score>=3: side="🟢 GREEN / bullish bias"; strength="Moderate directional score"
    elif score<=-3: side="🔴 RED / bearish bias"; strength="Moderate directional score"
    else: side="⚪ NO CLEAR SIGNAL"; strength="Mixed indicators — skip"
    nxt=datetime.fromtimestamp(last["t"]/1000,timezone.utc)
    msg=(f"⏱ 1-MIN CANDLE ESTIMATE — {INST}\n"
         f"Last completed candle (UTC): {nxt:%Y-%m-%d %H:%M}\n"
         f"Next candle direction estimate: {side}\n"
         f"Score: {score}/4 | {strength}\n"
         f"Last close: {last['c']}\n"
         f"RSI(14): {rr:.1f}\n"
         f"Basis: {', '.join(reasons)}\n\n"
         "⚠️ Estimate only, NOT guaranteed and not a true probability. 1m candles are noisy. No financial advice.")
    print(msg)
    if TOKEN and CHAT:
        body=urllib.parse.urlencode({"chat_id":CHAT,"text":msg,"disable_web_page_preview":"true"}).encode()
        req=urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data=body)
        with urllib.request.urlopen(req,timeout=20) as r:
            result=json.loads(r.read().decode())
            if not result.get("ok"): raise RuntimeError("Telegram send failed")
    else: print("Telegram secrets not set; prediction printed to Actions log.")
if __name__=="__main__": predict()
