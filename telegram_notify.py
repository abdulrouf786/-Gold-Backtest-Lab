import csv, json, os, urllib.parse, urllib.request
from pathlib import Path
TOKEN=os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN","")
CHAT=os.getenv("TELEGRAM_CHAT_ID","")
STATUS=os.getenv("BACKTEST_STATUS","success").lower()
def send(msg):
    if not TOKEN or not CHAT:
        print("Telegram secrets missing. Set BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return
    url=f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data=urllib.parse.urlencode({"chat_id":CHAT,"text":msg,"disable_web_page_preview":"true"}).encode()
    req=urllib.request.Request(url,data=data)
    with urllib.request.urlopen(req,timeout=25) as r: result=json.loads(r.read().decode())
    if not result.get("ok"): raise RuntimeError("Telegram API sendMessage failed")
def main():
    if STATUS!="success":
        send("⚠️ GOLD BACKTEST LAB\nGitHub Actions backtest failed. Check workflow logs.")
        return
    p=Path("reports/strategy_comparison.csv")
    if not p.exists():
        send("⚠️ GOLD BACKTEST LAB\nBacktest finished but report CSV is missing.")
        return
    with p.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
    rows.sort(key=lambda x:float(x.get("net_R") or 0),reverse=True)
    msg=["📊 GOLD BACKTEST LAB — RESULTS","Market: Binance PAXGUSDT (gold-backed token, not spot XAUUSD)","Historical simulation only; not a guaranteed signal."]
    for i,r in enumerate(rows[:5],1):
        msg.append(f"{i}. {r['strategy']}\nTrades: {r['trades']} | Win: {r['win_rate_pct']}%\nNet R: {r['net_R']} | PF: {r['profit_factor']} | Max DD: {r['max_drawdown_R']}R")
    msg.append("\nGitHub Actions: https://github.com/abdulrouf786/-Gold-Backtest-Lab/actions")
    send("\n\n".join(msg))
if __name__=="__main__": main()
