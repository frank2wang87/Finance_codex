"""
Chrome bridge fallback - uses cached data when direct network is blocked.
"""
import os
import json
import pandas as pd
from .config import FIELD_MAP


def load_cached_data(filepath: str = "stock_data.json") -> pd.DataFrame:
    """从 Chrome bridge 保存的 JSON 文件加载数据"""
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    diff = data.get("data", {}).get("diff", [])
    if not diff:
        return None
    df = pd.DataFrame(diff)
    df.rename(columns=FIELD_MAP, inplace=True)
    numeric_cols = ["最新价", "涨跌幅", "涨跌额", "成交量(手)", "成交额",
                    "振幅", "换手率", "市盈率(动态)", "量比",
                    "最高价", "最低价", "开盘价", "昨收价",
                    "总市值", "流通市值"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def apply_patch():
    """猴子补丁：给 EastMoneyFetcher.fetch_realtime 加上缓存后备"""
    from .data_fetcher import EastMoneyFetcher

    _original = EastMoneyFetcher.fetch_realtime

    def patched_fetch(self, *args, **kwargs):
        try:
            return _original(self, *args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            is_network_error = any(x in err_str for x in [
                "proxyerror", "connectionerror", "max retries",
                "10013", "remote disconnected", "unable to connect"
            ])
            if is_network_error:
                cached = load_cached_data()
                if cached is not None:
                    return cached
            raise

    EastMoneyFetcher.fetch_realtime = patched_fetch
    return True
