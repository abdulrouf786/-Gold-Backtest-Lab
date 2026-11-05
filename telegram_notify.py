import csv
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATUS = os.getenv("BACKTEST_STATUS", "success").lower()

def send(text):
    if not TOKEN or not CHAT_ID:
        print("Telegram secrets missing; skipping notification.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=payload)
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode())
    if not result.get("ok"):
        raise RuntimeError("Telegram API returned ok=false")
    print("Telegram notification sent.")

def main():
    if STATUS != "success":
        send("⚠️ Gold Backtest Lab\nBacktest workflow FAILED. GitHub Actions logs check karein.")
        return

    report = Path("reports/strategy_comparison.csv")
    if not report.exists():
        send("⚠️ Gold Backtest Lab\nWorkflow successful, lekin strategy_comparison.csv report nahi mili.")
        return

    with report.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        send("📊 Gold Backtest Lab\nBacktest complete, lekin report empty hai.")
        return

    rows.sort(key=lambda r: float(r.get("net_R", 0) or 0), reverse=True)
    lines = ["📊 GOLD BACKTEST LAB — RESULTS", "Market: Yahoo Finance GC=F (Gold futures)", "Note: Historical test; not a live signal."]
    for i, r in enumerate(rows[:5], 1):
        pf = r.get("profit_factor", "0")
        lines.append(
            f"{i}. {r.get('strategy','?')}\n"
            f"Trades: {r.get('trades','?')} | Win rate: {r.get('win_rate_pct','?')}%\n"
            f"Net R: {r.get('net_R','?')} | PF: {pf} | Max DD: {r.get('max_drawdown_R','?')} R"
        )
    lines.append("\nWorkflow: https://github.com/abdulrouf786/-Gold-Backtest-Lab/actions")
    send("\n\n".join(lines))

if __name__ == "__main__":
    main()
