import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("接口发生重定向，请使用最终地址")

def build_context(state, mode, now, asset_id=None):
    if mode not in ("daily","weekly","asset"): raise ValueError("分析类型无效")
    start=now.replace(hour=0,minute=0,second=0,microsecond=0)
    if mode=="weekly": start-=timedelta(days=start.weekday())
    if mode=="asset": start -= timedelta(days=90)
    names={a["id"]:{"name":a["name"],"code":a["code"]} for a in state["assets"]}
    tx=[{"time":t["time"],"type":t["type"],"asset":names.get(t["asset_id"]),"quantity":t["quantity"],"price":t["price"],"amount":t["amount"],"fee":t["fee"]} for t in state["transactions"] if t["type"] in ("buy","sell") and start<=datetime.fromisoformat(t["time"])<=now]
    positions=[{k:p.get(k) for k in ("name","code","quantity","average_cost","price","quote_time","quote_source","market_value","cost","realized","unrealized","profit","return_rate")} for p in state["portfolio"]["positions"] if p["quantity"]>0 or any(x["asset"] and x["asset"]["code"]==p["code"] for x in tx)]
    if mode=="asset":
        try: asset_id=int(asset_id)
        except (ValueError,TypeError): raise ValueError("请选择有效标的") from None
        selected=next((p for p in state["portfolio"]["positions"] if p["id"]==asset_id),None)
        if selected is None: raise ValueError("标的不存在")
        positions=[{k:selected.get(k) for k in ("name","code","quantity","average_cost","price","quote_time","quote_source","market_value","cost","realized","unrealized","profit","return_rate")}]
        tx=[t for t in tx if t["asset"] and t["asset"]["code"]==selected["code"]]
    portfolio={k:state["portfolio"][k] for k in ("equity","cash","contributions","profit","return_rate")}
    timeline=state["portfolio"].get("timeline",[])
    prior=[p for p in timeline if datetime.fromisoformat(p["time"]) < start]
    during=[p for p in timeline if start <= datetime.fromisoformat(p["time"]) <= now and p.get("tx_id") is not None]
    snapshots=([prior[-1]] if prior else [])+during
    history=[{k:p.get(k) for k in ("time","equity","profit","return_rate","cash","asset_states")} for p in snapshots]
    if mode=="asset":
        for p in history:
            states=p.get("asset_states") or {}
            p["asset_states"]={str(asset_id):states[str(asset_id)]} if str(asset_id) in states else {}
    return {"period_start":start.isoformat(timespec="minutes"),"as_of":now.isoformat(timespec="minutes"),"positions":positions,"portfolio":portfolio,"transactions":tx,"transaction_node_snapshots":history,"limitations":"历史点按最近成交价估值，不是每日市场行情；无连续历史价格、新闻、估值和市场预测；报价可能延迟"}

def parse_preferences(raw):
    if not isinstance(raw, dict): raise ValueError("投资偏好格式无效")
    result={}
    for key,upper in (("holding_months",1200),("max_drawdown_pct",100),("max_position_pct",100),("min_cash_pct",100)):
        value=raw.get(key)
        if value in (None,""): result[key]=None; continue
        try: number=float(value)
        except (TypeError,ValueError): raise ValueError("投资偏好数值无效") from None
        import math
        if not math.isfinite(number) or number<0 or number>upper or (key=="holding_months" and (number<1 or not number.is_integer())):
            raise ValueError("投资偏好超出范围")
        result[key]=number
    result["notes"]=str(raw.get("notes",""))[:600]
    return result

def analyze(state, body):
    base=str(body.get("base_url","")).strip().rstrip("/")
    model=str(body.get("model","")).strip()
    key=str(body.get("api_key","")).strip()
    mode=str(body.get("mode",""))
    parts=urlsplit(base)
    if parts.scheme!="https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.hostname in ("localhost",) or parts.hostname.endswith(".local"):
        raise ValueError("请填写公开服务商的 HTTPS 基础地址")
    if not model or len(model)>120 or not key or len(key)>1024 or "\n" in key or "\r" in key: raise ValueError("请填写有效的模型与 API Key")
    ctx=build_context(state,mode,datetime.now(),body.get("asset_id"))
    preferences=parse_preferences(body.get("preferences",{}))
    ctx["preferences"]=preferences
    ctx["daily_pnl"]=state.get("daily")
    if mode=="asset" and ctx["daily_pnl"]:
        ctx["daily_pnl"]={**ctx["daily_pnl"],"items":[x for x in ctx["daily_pnl"]["items"] if x["id"]==int(body["asset_id"])]}
    targets=state.get("targets",{})
    equity=ctx["portfolio"]["equity"]
    ctx["current_cash_pct"]=ctx["portfolio"]["cash"]/equity*100 if equity>0 else None
    for position in ctx["positions"]:
        position["portfolio_weight_pct"]=position["market_value"]/equity*100 if equity>0 else None
        asset=next((a for a in state["assets"] if a["code"]==position["code"]),None)
        position["target_weight_pct"]=targets.get(str(asset["id"])) if asset else None
        position["target_gap_pct"]=position["target_weight_pct"]-position["portfolio_weight_pct"] if position["target_weight_pct"] is not None and position["portfolio_weight_pct"] is not None else None
    if not ctx["positions"]: raise ValueError("暂无持仓或本期买卖记录")
    system="你是谨慎的投资记录分析助手，只依据提供的数据。不得编造新闻、历史行情、未来价格或用户风险偏好。按标的结合投资偏好和当前仓位比例给出买入、卖出或不动的条件性分析、依据、风险、是否超出设置上限和缺失数据；用户的回撤阈值不是实测最大回撤，没有连续行情时不得声称计算了最大回撤；数据不足或报价过旧优先不动。不要承诺收益或发出确定性交易指令。用户自行决策。"
    system += " 输出 JSON 对象，字段 summary 和 assets；assets 数组每个元素包含 name、code、decision、trend、levels、reason、risk，均为中文字符串。trend 为未来可能的多种情景和适用期限，不得保证方向；levels 给出条件性观察或买卖节点，数据不足时明确写无法可靠确定，不编造具体价位。每个标的独立一项。"
    task=("分析所选标的最近90天的持仓和买卖" if mode=="asset" else "分析当天持仓和买卖" if mode=="daily" else "复盘本周持仓和交易，提出下周每个标的的条件性建议和组合风险")
    payload={"model":model,"messages":[{"role":"system","content":system},{"role":"user","content":task+"；账本数据和投资偏好："+json.dumps(ctx,ensure_ascii=False)}],"stream":False}
    req=Request(base+"/chat/completions",data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        with build_opener(NoRedirect()).open(req,timeout=90) as response: result=json.loads(response.read(2000000))
    except HTTPError as exc: raise ValueError("模型接口返回 HTTP "+str(exc.code)+"，请检查地址、模型、Key 和额度") from None
    except (URLError,TimeoutError,OSError): raise ValueError("无法连接模型接口，请检查网络和地址") from None
    try:
        choice=result["choices"][0]
        content=choice["message"]["content"]
        if not isinstance(content,str) or not content.strip(): raise ValueError("模型返回空内容")
        if choice.get("finish_reason")=="length": content+="\n[内容被截断]"
    except (KeyError,IndexError,TypeError): raise ValueError("模型返回格式无法识别") from None
    return {"content":content,"as_of":ctx["as_of"],"period_start":ctx["period_start"],"model":model}
