"""
Stock screener module with multi-condition filtering.
"""

import logging
from typing import Dict, List, Tuple, Callable, Any
from dataclasses import dataclass, field

import pandas as pd

from .config import config
from .data_fetcher import EastMoneyFetcher, normalize_realtime_data

logger = logging.getLogger(__name__)


CUSTOM_CONDITION_FIELDS = {
    "最新价 (元)": {"column": "最新价", "scale": 1.0},
    "涨跌幅 (%)": {"column": "涨跌幅", "scale": 1.0},
    "涨跌额 (元)": {"column": "涨跌额", "scale": 1.0},
    "成交量 (手)": {"column": "成交量(手)", "scale": 1.0},
    "成交额 (亿元)": {"column": "成交额", "scale": 1e8},
    "振幅 (%)": {"column": "振幅", "scale": 1.0},
    "换手率 (%)": {"column": "换手率", "scale": 1.0},
    "市盈率 (动态)": {"column": "市盈率(动态)", "scale": 1.0},
    "量比": {"column": "量比", "scale": 1.0},
    "最高价 (元)": {"column": "最高价", "scale": 1.0},
    "最低价 (元)": {"column": "最低价", "scale": 1.0},
    "开盘价 (元)": {"column": "开盘价", "scale": 1.0},
    "昨收价 (元)": {"column": "昨收价", "scale": 1.0},
    "总市值 (亿元)": {"column": "总市值", "scale": 1e8},
    "流通市值 (亿元)": {"column": "流通市值", "scale": 1e8},
}

SCREENABLE_COLUMNS = {
    definition["column"] for definition in CUSTOM_CONDITION_FIELDS.values()
}


@dataclass
class ScreenResult:
    """单只股票的筛选结果"""
    code: str
    name: str
    price: float
    pct_change: float
    volume_ratio: float
    turnover: float
    market_cap: float
    vol_trend_ok: bool = False
    limit_up_days: int = 0
    all_passed: bool = False


@dataclass
class ConditionDef:
    """条件定义"""
    name: str                  # 条件名称
    key: str                   # 条件key，用于启用/禁用
    enabled: bool = True       # 默认启用


# 预定义10个条件槽位
DEFAULT_CONDITIONS = [
    ConditionDef("涨幅 2%~5%", "pct_change"),
    ConditionDef("量比 1~5", "volume_ratio"),
    ConditionDef("换手率 5%~10%", "turnover"),
    ConditionDef("股价 5~80元", "price"),
    ConditionDef("市值 30~300亿", "market_cap"),
    ConditionDef("成交量3日递增", "volume_trend"),
    ConditionDef("近一月涨停次数>1", "limit_up"),
    ConditionDef("条件8(预留)", "cond_8", enabled=False),
    ConditionDef("条件9(预留)", "cond_9", enabled=False),
    ConditionDef("条件10(预留)", "cond_10", enabled=False),
]


class StockScreener:
    """选股器"""

    def __init__(self):
        self.fetcher = EastMoneyFetcher()
        self.conditions = DEFAULT_CONDITIONS

    @staticmethod
    def _validate_range(label: str, minimum: Any, maximum: Any) -> Tuple[float, float]:
        if minimum is None or maximum is None:
            raise ValueError(f"条件“{label}”需要同时填写最小值和最大值")
        try:
            minimum = float(minimum)
            maximum = float(maximum)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"条件“{label}”的最小值和最大值必须是数字") from exc
        if minimum > maximum:
            raise ValueError(f"条件“{label}”的最小值不能大于最大值")
        return minimum, maximum

    def _build_realtime_mask(
        self, df: pd.DataFrame, cond_values: Dict[str, Any]
    ) -> pd.Series:
        cfg = config.conditions
        ranges = [
            ("涨幅", "涨跌幅", cond_values.get("pct_min", cfg.pct_change_min), cond_values.get("pct_max", cfg.pct_change_max)),
            ("量比", "量比", cond_values.get("vr_min", cfg.volume_ratio_min), cond_values.get("vr_max", cfg.volume_ratio_max)),
            ("换手率", "换手率", cond_values.get("tr_min", cfg.turnover_min), cond_values.get("tr_max", cfg.turnover_max)),
            ("股价", "最新价", cond_values.get("price_min", cfg.price_min), cond_values.get("price_max", cfg.price_max)),
            ("市值", "总市值", cond_values.get("mcap_min", cfg.market_cap_min * 1e8), cond_values.get("mcap_max", cfg.market_cap_max * 1e8)),
        ]

        mask = pd.Series(True, index=df.index)
        for label, column, minimum, maximum in ranges:
            minimum, maximum = self._validate_range(label, minimum, maximum)
            mask &= df[column].between(minimum, maximum, inclusive="both")

        codes = df["股票代码"].astype(str).str.zfill(6)
        if not cond_values.get("include_chinext", True):
            mask &= ~codes.str.startswith(("300", "301"))
        if not cond_values.get("include_star_market", True):
            mask &= ~codes.str.startswith(("688", "689"))

        for custom in cond_values.get("custom_conditions", []):
            label = str(custom.get("label") or custom.get("column") or "自定义条件")
            column = custom.get("column")
            if column not in SCREENABLE_COLUMNS:
                raise ValueError(f"自定义条件“{label}”不是可筛选的行情字段")
            if column not in df.columns:
                raise ValueError(f"当前行情数据缺少字段“{column}”")
            minimum, maximum = self._validate_range(
                label, custom.get("min"), custom.get("max")
            )
            mask &= df[column].between(minimum, maximum, inclusive="both")

        return mask

    @staticmethod
    def _limit_up_matches(count: int, cond_values: Dict[str, Any]) -> bool:
        cfg = config.conditions
        minimum = cond_values.get("limit_up_min", cfg.limit_up_days_min)
        maximum = cond_values.get("limit_up_max", cfg.limit_up_days_max)
        minimum, maximum = StockScreener._validate_range(
            "最近一个月涨停次数", minimum, maximum
        )
        return minimum <= count <= maximum

    def screen(self, cond_values: Dict[str, Any] = None) -> pd.DataFrame:
        """
        执行完整选股流程
        :param cond_values: 可覆盖的条件值字典
        :returns: 筛选结果的DataFrame
        """
        cond_values = cond_values or {}

        # 1. 获取全量实时数据
        df = self.fetcher.fetch_realtime()
        if df.empty:
            return df

        logger.info(f"初始数据: {len(df)} 只股票")

        # 2. 实时行情条件过滤（固定条件 + 用户自定义条件）
        df = normalize_realtime_data(df)
        base_mask = self._build_realtime_mask(df, cond_values)
        candidates = df[base_mask].copy()

        logger.info(f"基础条件筛选后: {len(candidates)} 只股票")

        if candidates.empty:
            return candidates

        # 3. 需要 K 线数据的条件
        check_vol = cond_values.get("check_vol_trend", True)
        check_limit = cond_values.get("check_limit_up", True)
        check_macd = cond_values.get("check_macd", False)
        if not (check_vol or check_limit or check_macd):
            return candidates

        codes = candidates["股票代码"].tolist()
        names = candidates["股票名称"].tolist()

        # 批量获取K线数据
        history_days = 60 if check_macd else 30
        kline_map = self.fetcher.batch_check_history(codes, days=history_days)

        results = []
        for code, name in zip(codes, names):
            kdf = kline_map.get(code)
            row = candidates[candidates["股票代码"] == code].iloc[0]

            # 条件f: 成交量3日递增
            vol_ok = True
            if check_vol and kdf is not None:
                vol_ok, volumes = self.fetcher.check_volume_trend(kdf)
            elif check_vol:
                vol_ok = False

            # 条件g: 最近一月涨停次数
            limit_up_cnt = 0
            if check_limit and kdf is not None:
                limit_up_cnt = self.fetcher.count_limit_up_days(kdf)
            limit_ok = (
                self._limit_up_matches(limit_up_cnt, cond_values)
                if check_limit else True
            )

            macd_ok = True
            if check_macd:
                macd_ok = self.fetcher.check_macd_golden_cross(kdf)

            # 最终判定
            all_pass = vol_ok and limit_ok and macd_ok

            results.append({
                "股票代码": code,
                "股票名称": name,
                "最新价": row["最新价"],
                "涨跌幅": row["涨跌幅"],
                "量比": row["量比"],
                "换手率": row["换手率"],
                "总市值": row["总市值"],
                "成交量3日递增": "是" if vol_ok else "否",
                "近一月涨停次数": limit_up_cnt,
                "MACD金叉": "是" if macd_ok else "否",
                "通过筛选": "是" if all_pass else "否",
            })

        return pd.DataFrame(results)

    def screen_stream(self, df: pd.DataFrame, cond_values: Dict[str, Any] = None) -> pd.DataFrame:
        """
        对已获取的实时数据执行筛选（用于UI中复用数据）
        """
        cond_values = cond_values or {}

        if df.empty:
            return df

        df = normalize_realtime_data(df)

        mask = self._build_realtime_mask(df, cond_values)

        candidates = df[mask].copy()

        # 检查是否需要历史数据分析
        check_vol = cond_values.get("check_vol_trend", True)
        check_limit = cond_values.get("check_limit_up", True)
        check_macd = cond_values.get("check_macd", False)

        if not (check_vol or check_limit or check_macd):
            return candidates

        if candidates.empty:
            return candidates

        codes = candidates["股票代码"].tolist()
        history_days = 60 if check_macd else 30
        kline_map = self.fetcher.batch_check_history(codes, days=history_days)

        keep_indices = []
        for idx, code in enumerate(codes):
            kdf = kline_map.get(code)
            if kdf is None or kdf.empty:
                continue

            candidate_index = candidates.index[idx]

            if check_vol:
                vol_ok, _ = self.fetcher.check_volume_trend(kdf)
                if not vol_ok:
                    continue
                candidates.at[candidate_index, "成交量3日递增"] = "是"

            if check_limit:
                cnt = self.fetcher.count_limit_up_days(kdf)
                if not self._limit_up_matches(cnt, cond_values):
                    continue
                candidates.at[candidate_index, "近一月涨停次数"] = cnt

            if check_macd:
                if not self.fetcher.check_macd_golden_cross(kdf):
                    continue
                candidates.at[candidate_index, "MACD金叉"] = "是"

            keep_indices.append(candidate_index)

        return candidates.loc[keep_indices]
