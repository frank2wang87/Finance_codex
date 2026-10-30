"""
Data fetcher module for A-share market data via East Money API.
"""

import time
import random
import logging
from typing import List, Optional, Tuple, Dict

import httpx
import pandas as pd

from .config import config, FIELD_MAP, get_market

logger = logging.getLogger(__name__)

REALTIME_NUMERIC_COLUMNS = [
    "最新价", "涨跌幅", "涨跌额", "成交量(手)", "成交额", "振幅",
    "换手率", "市盈率(动态)", "量比", "最高价", "最低价", "开盘价",
    "昨收价", "总市值", "流通市值",
]


def normalize_realtime_data(df: pd.DataFrame) -> pd.DataFrame:
    """统一不同实时行情源的字段类型。"""
    normalized = df.copy()
    for column in REALTIME_NUMERIC_COLUMNS:
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "股票代码" in normalized.columns:
        normalized["股票代码"] = normalized["股票代码"].astype(str).str.zfill(6)
        normalized = normalized.drop_duplicates("股票代码", keep="last")
        normalized = normalized.reset_index(drop=True)
    return normalized


class EastMoneyFetcher:
    """A 股行情获取器，东方财富不可用时自动切换腾讯行情。"""

    def __init__(self):
        self.session = httpx.Client(
            headers=config.api.eastmoney_headers,
            timeout=15,
            trust_env=False,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self.realtime_urls = tuple(dict.fromkeys([
            config.api.realtime_url,
            *config.api.realtime_fallback_urls,
        ]))
        self._realtime_url_index = 0
        self.last_source = None

    def _fetch_realtime_page(self, params: dict) -> dict:
        """从可用行情节点获取一页数据，并记住成功的节点。"""
        last_error = None
        for offset in range(len(self.realtime_urls)):
            index = (self._realtime_url_index + offset) % len(self.realtime_urls)
            url = self.realtime_urls[index]
            try:
                resp = self.session.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data.get("data") is None:
                    raise ValueError(f"行情节点返回空数据: {url}")
                self._realtime_url_index = index
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning("行情节点不可用 %s: %s", url, exc)

        raise RuntimeError("所有东方财富行情节点均不可用") from last_error

    def _fetch_realtime_eastmoney(self, max_pages: int = 60) -> pd.DataFrame:
        """通过东方财富获取 A 股实时行情全量数据。"""
        base_params = {
            "pn": 1, "pz": 100, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
            "fields": ",".join(FIELD_MAP.keys()),
        }
        logger.info("正在获取全A股实时行情数据...")
        all_dfs = []
        for page in range(1, max_pages + 1):
            params = base_params.copy()
            params["pn"] = page
            data = self._fetch_realtime_page(params)
            diff = data.get("data", {}).get("diff", [])
            total = data.get("data", {}).get("total", 0)
            if not diff:
                break
            page_df = pd.DataFrame(diff)
            all_dfs.append(page_df)
            if page * 100 >= total:
                break
            time.sleep(random.uniform(0.3, 0.6))
            logger.info(f"已获取第 {page} 页, 累计 {page*100}/{total}")
        if not all_dfs:
            logger.warning("未获取到数据")
            return pd.DataFrame()
        df = pd.concat(all_dfs, ignore_index=True)
        df.rename(columns=FIELD_MAP, inplace=True)
        logger.info(f"成功获取 {len(df)} 只股票")
        return df

    @staticmethod
    def _number(value, multiplier: float = 1.0):
        try:
            return float(value) * multiplier
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _tencent_symbol(code: str) -> str:
        if code.startswith(("4", "8", "92")):
            return f"bj{code}"
        if code.startswith(("5", "6", "9")):
            return f"sh{code}"
        return f"sz{code}"

    def _fetch_realtime_tencent(self, batch_size: int = 80) -> pd.DataFrame:
        """用交易所股票清单和腾讯批量接口构造实时行情。"""
        import akshare as ak

        code_df = ak.stock_info_a_code_name()
        codes = code_df["code"].astype(str).str.zfill(6).tolist()
        rows = []

        for start in range(0, len(codes), batch_size):
            batch = codes[start:start + batch_size]
            symbols = ",".join(self._tencent_symbol(code) for code in batch)
            url = f"https://qt.gtimg.cn/q={symbols}"
            resp = self.session.get(
                url,
                headers={
                    "User-Agent": config.api.eastmoney_headers["User-Agent"],
                    "Referer": "https://gu.qq.com/",
                },
            )
            resp.raise_for_status()
            resp.encoding = "gbk"

            for line in resp.text.splitlines():
                payload = line.partition("=")[2]
                first_quote = payload.find('"')
                last_quote = payload.rfind('"')
                if first_quote < 0 or last_quote <= first_quote:
                    continue
                fields = payload[first_quote + 1:last_quote].split("~")
                if len(fields) < 50 or not fields[2]:
                    continue
                rows.append({
                    "股票代码": fields[2],
                    "股票名称": fields[1],
                    "最新价": self._number(fields[3]),
                    "涨跌幅": self._number(fields[32]),
                    "涨跌额": self._number(fields[31]),
                    "成交量(手)": self._number(fields[36]),
                    "成交额": self._number(fields[37], 1e4),
                    "振幅": self._number(fields[43]),
                    "换手率": self._number(fields[38]),
                    "市盈率(动态)": self._number(fields[39]),
                    "量比": self._number(fields[49]),
                    "最高价": self._number(fields[33]),
                    "最低价": self._number(fields[34]),
                    "开盘价": self._number(fields[5]),
                    "昨收价": self._number(fields[4]),
                    "总市值": self._number(fields[45], 1e8),
                    "流通市值": self._number(fields[44], 1e8),
                })

            if start + batch_size < len(codes):
                time.sleep(0.05)

        if not rows:
            raise RuntimeError("腾讯行情接口未返回 A 股数据")

        df = pd.DataFrame(rows)
        logger.info("腾讯行情成功获取 %s 只股票", len(df))
        return df

    def fetch_realtime(self, max_pages: int = 60) -> pd.DataFrame:
        """获取实时行情；东方财富列表受限时自动使用腾讯行情。"""
        try:
            df = self._fetch_realtime_eastmoney(max_pages=max_pages)
            self.last_source = "东方财富在线接口"
            return normalize_realtime_data(df)
        except Exception as exc:
            logger.warning("东方财富实时列表不可用，切换腾讯行情: %s", exc)
            df = self._fetch_realtime_tencent()
            self.last_source = "交易所清单 + 腾讯实时行情"
            return normalize_realtime_data(df)

    def fetch_kline(
        self, code: str, days: int = 30, retries: int = 2
    ) -> Optional[pd.DataFrame]:
        """
        获取个股K线数据
        :param code: 股票代码 (如 "000001", "600000")
        :param days: 获取最近多少天的数据
        :returns: DataFrame with columns [日期, 开盘, 收盘, 最高, 最低, 成交量, ...]
        """
        try:
            return self._fetch_kline_tencent(code, days)
        except Exception as exc:
            logger.warning("腾讯 K 线不可用，切换东方财富: %s", exc)

        market = get_market(code)
        secid = f"{market}.{code}"

        params = {
            "secid": secid,
            "ut": "fa5fd1943c7b386f172d6893dbfd32bb",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "end": "20500101",
            "lmt": str(max(days * 2, 60)),
        }

        last_err = None
        for attempt in range(retries):
            try:
                resp = self.session.get(
                    config.api.kline_url, params=params, timeout=15
                )
                resp.raise_for_status()
                result = resp.json()

                klines = result.get("data", {}).get("klines", [])
                if not klines:
                    return None

                rows = [k.split(",") for k in klines]
                # K线字段: f51~f61
                col_names = ["日期", "开盘", "收盘", "最高", "最低",
                             "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
                df = pd.DataFrame(rows, columns=col_names)

                for col in col_names[1:]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df["日期"] = pd.to_datetime(df["日期"])
                df = df.sort_values("日期").reset_index(drop=True)

                return df.tail(days)

            except Exception as e:
                last_err = e
                time.sleep(random.uniform(0.5, 1.5) + 0.1 * attempt)

        logger.warning(f"获取 {code} K线失败: {last_err}")
        return None

    def _fetch_kline_tencent(self, code: str, days: int) -> pd.DataFrame:
        symbol = self._tencent_symbol(str(code).zfill(6))
        params = {"param": f"{symbol},day,,,{max(days * 2, 60)},qfq"}
        resp = self.session.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params=params,
            headers={
                "User-Agent": config.api.eastmoney_headers["User-Agent"],
                "Referer": "https://gu.qq.com/",
            },
        )
        resp.raise_for_status()
        stock_data = resp.json().get("data", {}).get(symbol, {})
        rows = stock_data.get("qfqday") or stock_data.get("day") or []
        if not rows:
            raise ValueError(f"腾讯未返回 {code} 的 K 线数据")

        df = pd.DataFrame(
            [row[:6] for row in rows],
            columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"],
        )
        for col in ["开盘", "收盘", "最高", "最低", "成交量"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["日期"] = pd.to_datetime(df["日期"])
        previous_close = df["收盘"].shift(1)
        df["成交额"] = None
        df["振幅"] = (df["最高"] - df["最低"]) / previous_close * 100
        df["涨跌幅"] = (df["收盘"] / previous_close - 1) * 100
        df["涨跌额"] = df["收盘"] - previous_close
        df["换手率"] = None
        df = df.sort_values("日期").reset_index(drop=True)
        return df.tail(days)

    def check_volume_trend(
        self, kline_df: pd.DataFrame
    ) -> Tuple[bool, List[float]]:
        """
        检查成交量是否连续3日递增
        :returns: (是否满足, 近3日成交量列表)
        """
        if kline_df is None or len(kline_df) < 3:
            return False, []

        volumes = kline_df["成交量"].tail(3).tolist()
        if len(volumes) < 3:
            return False, volumes

        # 成交量连续递增：v1 < v2 < v3
        is_increasing = volumes[0] < volumes[1] < volumes[2]
        return is_increasing, volumes

    @staticmethod
    def check_macd_golden_cross(kline_df: pd.DataFrame) -> bool:
        """检查最新交易日 DIF 是否由下向上穿越 DEA。"""
        if kline_df is None or "收盘" not in kline_df.columns:
            return False

        closes = pd.to_numeric(kline_df["收盘"], errors="coerce").dropna()
        if len(closes) < 35:
            return False

        ema_fast = closes.ewm(span=12, adjust=False).mean()
        ema_slow = closes.ewm(span=26, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=9, adjust=False).mean()

        return bool(dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1])

    def count_limit_up_days(
        self, kline_df: pd.DataFrame, threshold: float = 9.8
    ) -> int:
        """
        统计最近一个月内涨停天数
        涨停判定：当日涨跌幅 >= threshold%
        """
        if kline_df is None or kline_df.empty:
            return 0

        limit_ups = kline_df[kline_df["涨跌幅"] >= threshold]
        return len(limit_ups)

    def batch_check_history(
        self, codes: List[str], days: int = 30
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """批量获取多只股票的K线数据（带间隔，避免请求过快）"""
        results = {}
        total = len(codes)
        for i, code in enumerate(codes):
            kdf = self.fetch_kline(code, days=days)
            results[code] = kdf
            if i < total - 1:
                time.sleep(random.uniform(0.05, 0.15))
        return results
