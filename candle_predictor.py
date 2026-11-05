import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone

# Strict 1-minute directional filter. It is NOT a calibrated probability or guaranteed prediction.
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
    return [{"t":int(x[0]),"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4]),"v":float(x[5]),"confirm":x[8]} for x in rows]

def ema(vals,n):
    alpha=2/(n+1); result=vals[0]
    for value in vals[1:]: result=alpha*value+(1-alpha)*result
    return result

def rsi(vals,n=14):
    diff=[vals[i]-vals[i-1] for i in range(1,len(vals))]
    ups=sum(max(x,0) for x in diff[-n:])/n
    downs=sum(max(-x,0) for x in diff[-n:])/n
    return 100 if downs==0 else 100-100/(1+ups/downs)

def predict():
    data=[x for x in candles() if x["confirm"]=="1"]
    if len(data)<60: raise RuntimeError("Not enough completed 1m candles")
    closes=[x["c"] for x in data]
    last,prev=data[-1],data[-2]
    ema9=ema(closes[-40:],9); ema21=ema(closes[-60:],21); value_rsi=rsi(closes)
    score=0; checks=[]
    # Full-confirmation directional votes (4/4 required).
    checks.append(("EMA9/EMA21 trend",ema9>ema21 if ema9!=ema21 else None))
    checks.append(("Last candle body",last["c"]>last["o"] if last["c"]!=last["o"] else None))
    checks.append(("Close momentum",last["c"]>prev["c"] if last["c"]!=prev["c"] else None))
    checks.append(("RSI momentum",value_rsi>=55 if value_rsi>=55 else (False if value_rsi<=45 else None)))
    for _,vote in checks:
        if vote is True: score+=1
        elif vote is False: score-=1
    # Strict filter: all four checks must align; RSI must be directional.
    if score==4 and all(v is True for _,v in checks):
        signal="🟢 GREEN bias — FULL CONFIRMATION"
    elif score==-4 and all(v is False for _,v in checks):
        signal="🔴 RED bias — FULL CONFIRMATION"
    else:
        signal="⚪ NO SIGNAL — confirmation incomplete"
    stamp=datetime.fromtimestamp(last["t"]/1000,timezone.utc)
    detail="\n".join(f"{'✓' if v is True else ('✗' if v is False else '—')} {name}" for name,v in checks)
    message=(f"⏱ 1-MIN CANDLE ESTIMATE | {INST}\n"
      f"Last completed candle UTC: {stamp:%Y-%m-%d %H:%M}\n"
      f"Next candle: {signal}\nConfirmation: {score:+d}/4\n"
      f"RSI(14): {value_rsi:.1f}\nLast close: {last['c']}\n\n{detail}\n\n"
      "⚠️ This is a directional estimate, not a reliable probability or guarantee. 1-minute candles are noisy. "
      "Full indicator alignment does NOT mean the next candle is certain.")
    print(message)
    if TOKEN and CHAT:
        body=urllib.parse.urlencode({"chat_id":CHAT,"text":message,"disable_web_page_preview":"true"}).encode()
        req=urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage",data=body)
        with urllib.request.urlopen(req,timeout=20) as r:
            response=json.loads(r.read().decode())
            if not response.get("ok"): raise RuntimeError("Telegram send failed")
    else: print("Telegram secrets missing; result shown in GitHub Actions log.")

if __name__=="__main__": predict()
