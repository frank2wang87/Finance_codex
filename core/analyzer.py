"""
AI-powered stock analysis module.
Uses LLM API to analyze stocks for T+1 trading strategy.
"""
import logging
import json
import time
from urllib.parse import urlparse
from typing import List, Dict, Optional
from dataclasses import dataclass
import httpx
from openai import OpenAI
import pandas as pd
from .config import config
logger = logging.getLogger(__name__)
@dataclass
class AnalysisResult:
    code: str = ""
    name: str = ""
    score: float = 0.0
    reason: str = ""
    risk: str = ""
    current_price: float = 0.0
    target_price: float = 0.0
    stop_loss: float = 0.0

    @property
    def target_gain_pct(self) -> Optional[float]:
        if self.current_price <= 0 or self.target_price <= 0:
            return None
        return (self.target_price / self.current_price - 1) * 100

    @property
    def stop_loss_pct(self) -> Optional[float]:
        if self.current_price <= 0 or self.stop_loss <= 0:
            return None
        return (self.current_price - self.stop_loss) / self.current_price * 100
ANALYSIS_PROMPT = """你是一位资深A股短线交易分析师，专注于 T+1 交易策略（今日买入，次日卖出）。
请对以下股票进行专业分析，判断今日买入、次日卖出的可行性。
股票代码：{code}
股票名称：{name}
当前价格：{price}元
今日涨幅：{pct_change}%
量比：{volume_ratio}
换手率：{turnover}%
总市值：{market_cap}亿元
市盈率(动态)：{pe}
涨停次数(近一月)：{limit_up_days}
请从以下维度分析：
1. 技术面（K线形态、量价配合、短线趋势）
2. 资金面（量比、换手率、主力资金动向）
3. 情绪面（市场热度、涨停基因）
4. 风险因素（追高风险、次日抛压）
请返回严格的 JSON 格式（不要有其他文字）:
{{
    "score": <0-100的整数评分>,
    "reason": "<简要分析理由>",
    "risk": "<风险提示>",
    "target_price": <目标价, 浮点数>,
    "stop_loss": <止损价, 浮点数>
}}
评分标准：
- 90-100: 非常推荐买入
- 70-89: 推荐买入
- 50-69: 谨慎买入
- 0-49: 不推荐买入
"""
class StockAnalyzer:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or config.llm.api_key
        self.base_url = self._normalize_base_url(base_url or config.llm.base_url)
        self.model = self._normalize_model(model or config.llm.model)
        self._client = None

    @staticmethod
    def _normalize_base_url(base_url):
        value = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower()

        if hostname in {"deepseek.com", "www.deepseek.com", "chat.deepseek.com"}:
            return "https://api.deepseek.com"
        return value

    @staticmethod
    def _normalize_model(model):
        value = str(model or "").strip()
        aliases = {
            "deepseek v4 pro": "deepseek-v4-pro",
            "deepseek-v4-pro": "deepseek-v4-pro",
            "deepseek v4 flash": "deepseek-v4-flash",
            "deepseek-v4-flash": "deepseek-v4-flash",
        }
        return aliases.get(value.lower(), value)

    def _friendly_error(self, exc):
        message = str(exc).strip()
        lowered = message.lower()
        if "<!doctype html" in lowered or "request blocked" in lowered:
            if "deepseek" in self.base_url.lower():
                return (
                    "DeepSeek 安全网关拦截了请求。请确认 API 地址为 "
                    "https://api.deepseek.com/v1，模型名称为 deepseek-chat；"
                    "若配置正确，请稍后重试。"
                )
            return "模型 API 安全网关拦截了请求，请检查 API 地址后重试。"
        if "authentication" in lowered or "api key" in lowered or "401" in lowered:
            return "API Key 无效或未获授权，请检查密钥。"
        if "supported api model names" in lowered or "model_not_found" in lowered:
            return "模型配置错误。当前应使用 DeepSeek V4 Pro（API 标识 deepseek-v4-pro）。"
        if len(message) > 300:
            message = message[:300] + "..."
        return message or exc.__class__.__name__

    @property
    def client(self):
        if not self.api_key:
            return None
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=config.llm.timeout,
                http_client=httpx.Client(
                    trust_env=False,
                    timeout=config.llm.timeout,
                    follow_redirects=True,
                ),
            )
        return self._client
    def is_ready(self):
        return bool(self.api_key)
    def analyze(self, stock_info):
        if not self.is_ready():
            return None
        try:
            prompt = ANALYSIS_PROMPT.format(
                code=stock_info.get("code", ""),
                name=stock_info.get("name", ""),
                price=stock_info.get("price", 0),
                pct_change=stock_info.get("pct_change", 0),
                volume_ratio=stock_info.get("volume_ratio", 0),
                turnover=stock_info.get("turnover", 0),
                market_cap=stock_info.get("market_cap", 0),
                pe=stock_info.get("pe", "N/A"),
                limit_up_days=stock_info.get("limit_up_days", 0),
            )
            resp=self.client.chat.completions.create(
                model=self.model,
                messages=[{"role":"user","content":prompt}],
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens)
            content=resp.choices[0].message.content.strip()
            if "```json" in content:
                content=content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content=content.split("```")[1].split("```")[0].strip()
            data=json.loads(content)
            return AnalysisResult(
                code=stock_info.get("code",""),
                name=stock_info.get("name",""),
                score=float(data.get("score",0)),
                reason=data.get("reason",""),
                risk=data.get("risk",""),
                current_price=float(stock_info.get("price",0)),
                target_price=float(data.get("target_price",0)),
                stop_loss=float(data.get("stop_loss",0)))
        except Exception as e:
            logger.error(f"分析 {stock_info.get('code')} 失败: {e}")
            return AnalysisResult(
                code=stock_info.get("code",""),
                name=stock_info.get("name",""),
                score=0,
                reason=f"分析失败：{self._friendly_error(e)}",
                risk="未生成风险分析",
                current_price=float(stock_info.get("price",0)),
            )
    def analyze_batch(self, df):
        if not self.is_ready():
            logger.warning("未配置API密钥,跳过AI分析")
            return []
        results=[]
        for _,row in df.iterrows():
            mcap=float(row.get("总市值",0))/1e8 if row.get("总市值") else 0
            stock_info={
                "code":row.get("股票代码",""),
                "name":row.get("股票名称",""),
                "price":float(row.get("最新价",0)),
                "pct_change":float(row.get("涨跌幅",0)),
                "volume_ratio":float(row.get("量比",0)),
                "turnover":float(row.get("换手率",0)),
                "market_cap":round(mcap,2),
                "pe":float(row.get("市盈率(动态)",0)) if row.get("市盈率(动态)") else "N/A",
                "limit_up_days":int(row.get("近一月涨停次数",0))}
            result=self.analyze(stock_info)
            if result:
                results.append(result)
            time.sleep(0.5)
        results.sort(key=lambda r:r.score,reverse=True)
        return results
