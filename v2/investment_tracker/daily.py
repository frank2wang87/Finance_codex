"""Trading-day contribution based on prior close, today's trades and current quote."""
from datetime import datetime
from decimal import Decimal
from .ledger import calculate, dec, as_number

def daily_profit(assets, transactions, quotes, now):
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    rows=[]
    for a in assets:
        if a["kind"]!="security": continue
        prior=Decimal(0); today=[]
        for t in transactions:
            if t["asset_id"]!=a["id"] or t["type"] not in ("buy","sell"): continue
            at=datetime.fromisoformat(t["time"])
            if at<start: prior += dec(t["quantity"])*(1 if t["type"]=="buy" else -1)
            elif at<=now: today.append(t)
        if prior==0 and not today: continue
        q=quotes.get(a["id"]); reason=None; value=None
        try: qt=datetime.fromisoformat(q["time"]) if q else None
        except (TypeError,ValueError): qt=None
        if not q or not qt or qt.date()!=now.date() or qt>now:
            reason="缺少当日有效报价"
        elif any(datetime.fromisoformat(t["time"])>qt for t in today):
            reason="报价早于当日交易"
        elif prior and not q.get("prev_close"):
            reason="缺少昨收价"
        else:
            price=dec(q["price"])
            change=prior*(price-dec(q["prev_close"])) if prior else Decimal(0)
            for t in today:
                gross=dec(t["price"])*dec(t["quantity"])
                # amount captures actual cash flow and fee rounding.
                change += price*dec(t["quantity"])-dec(t["amount"]) if t["type"]=="buy" else dec(t["amount"])-price*dec(t["quantity"])
            value=as_number(change)
        rows.append({"id":a["id"],"name":a["name"],"code":a["code"],"profit":value,"reason":reason,
                     "quote_time":q.get("time") if q else None,"prev_close":q.get("prev_close") if q else None})
    previous=[t for t in transactions if datetime.fromisoformat(t["time"])<start]
    current=[t for t in transactions if datetime.fromisoformat(t["time"])<=now]
    interest=as_number(dec(calculate(assets,current,{},now)["interest"])-dec(calculate(assets,previous,{},start)["interest"]))
    missing=sum(1 for r in rows if r["profit"] is None)
    known=as_number(sum((dec(r["profit"]) for r in rows if r["profit"] is not None),Decimal(0))+dec(interest))
    return {"date":now.date().isoformat(),"items":rows,"cash_interest":interest,"known_total":known,
            "total":known if not missing else None,"missing":missing}
