import sqlite3
from datetime import datetime

c = sqlite3.connect('trades.db')
c.row_factory = sqlite3.Row
rows = c.execute("""SELECT t.id, t.market_price, t.claude_score, t.edge, t.amount_usd, t.side, t.created_at,
                  t.end_date_iso, o.result, o.pnl, o.resolved_at
           FROM trades t LEFT JOIN outcomes o ON o.trade_id = t.id ORDER BY t.id DESC LIMIT 5""").fetchall()

for row in rows:
    r = dict(row)
    rid = r["id"]
    
    # Test Resolution Duration
    end_iso = r.get("end_date_iso")
    resolved_at = r.get("resolved_at")
    created_at = r.get("created_at")
    duration_source = end_iso or resolved_at
    dur = ""
    if duration_source and created_at:
        try:
            close_dt = datetime.fromisoformat(duration_source.replace("Z", "+00:00"))
            create_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            delta = close_dt - create_dt
            total_secs = int(delta.total_seconds())
            if total_secs > 0:
                if total_secs < 60:
                    dur = f"{total_secs}s"
                elif total_secs < 3600:
                    dur = f"{total_secs // 60}m"
                else:
                    dur = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
        except Exception as e:
            dur = f"err:{e}"

    # Test Expected Profit
    price = r.get("market_price", 0.5)
    score = r.get("claude_score", 0.5)
    amount = r.get("amount_usd", 1.0)
    side = r.get("side", "YES")
    edge = r.get("edge", 0.0) or 0.0
    ep = 0.0
    if amount:
        entry_price = None
        if price and price > 0.01 and price < 0.99:
            entry_price = price
        elif edge and score:
            entry_price = max(0.01, min(0.99, score - edge))
        if entry_price and entry_price > 0.01 and entry_price < 0.99:
            if side == "YES":
                pp = amount * (1.0 / entry_price - 1.0)
            else:
                pp = amount * (1.0 / (1.0 - entry_price) - 1.0)
            ep = round(score * pp - (1.0 - score) * amount, 2)
        elif edge:
            ep = round(edge * amount, 2)

    print(f"#{rid}: res_dur={dur!r} exp_profit=${ep} (price={price}, score={score}, edge={edge}, side={side}, result={r.get('result')})")
c.close()