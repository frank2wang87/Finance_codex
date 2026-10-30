"""
Configuration for the stock screening and analysis tool.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class APIConfig:
    """API 配置"""
    eastmoney_headers: Dict[str, str] = field(default_factory=lambda: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
    })
    realtime_url: str = "https://push2.eastmoney.com/api/qt/clist/get"
    realtime_fallback_urls: List[str] = field(default_factory=lambda: [
        "https://1.push2.eastmoney.com/api/qt/clist/get",
        "https://17.push2.eastmoney.com/api/qt/clist/get",
        "https://79.push2.eastmoney.com/api/qt/clist/get",
    ])
    kline_url: str = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


@dataclass
class LLMConfig:
    """大模型 API 配置"""
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    model_display_name: str = "DeepSeek V4 Pro"
    temperature: float = 0.3
    max_tokens: int = 2000
    timeout: int = 60


@dataclass
class ConditionConfig:
    """选股条件默认值"""
    pct_change_min: float = 2.0    # 涨幅下限%
    pct_change_max: float = 5.0    # 涨幅上限%
    volume_ratio_min: float = 1.0  # 量比下限
    volume_ratio_max: float = 5.0  # 量比上限
    turnover_min: float = 5.0      # 换手率下限%
    turnover_max: float = 10.0     # 换手率上限%
    price_min: float = 5.0         # 股价下限(元)
    price_max: float = 80.0        # 股价上限(元)
    market_cap_min: float = 30.0   # 市值下限(亿)
    market_cap_max: float = 300.0  # 市值上限(亿)
    limit_up_days_min: int = 2     # 最近一月涨停次数下限（对应大于 1 次）
    limit_up_days_max: int = 31    # 最近一月涨停次数上限


@dataclass
class Config:
    """总配置"""
    api: APIConfig = field(default_factory=APIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    conditions: ConditionConfig = field(default_factory=ConditionConfig)


config = Config()


# 实时行情字段说明
FIELD_MAP = {
    "f2": "最新价",
    "f3": "涨跌幅",
    "f4": "涨跌额",
    "f5": "成交量(手)",
    "f6": "成交额",
    "f7": "振幅",
    "f8": "换手率",
    "f9": "市盈率(动态)",
    "f10": "量比",
    "f12": "股票代码",
    "f14": "股票名称",
    "f15": "最高价",
    "f16": "最低价",
    "f17": "开盘价",
    "f18": "昨收价",
    "f20": "总市值",
    "f21": "流通市值",
}

# K线字段
KLN_FIELD_MAP = {
    "f51": "日期",
    "f52": "开盘",
    "f53": "收盘",
    "f54": "最高",
    "f55": "最低",
    "f56": "成交量",
    "f57": "成交额",
    "f58": "振幅",
    "f59": "涨跌幅",
    "f60": "涨跌额",
    "f61": "换手率",
}


def get_market(code: str) -> int:
    """根据股票代码判断市场：1=沪市，0=深市"""
    code = str(code).strip()
    if code.startswith("6") or code.startswith("9"):
        return 1
    return 0
