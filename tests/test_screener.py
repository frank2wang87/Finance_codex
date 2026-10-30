import unittest

import pandas as pd

from core.data_fetcher import EastMoneyFetcher
from core.screener import StockScreener


class ScreenerTests(unittest.TestCase):
    @staticmethod
    def _base_conditions():
        return {
            "pct_min": 2.0,
            "pct_max": 5.0,
            "vr_min": 1.0,
            "vr_max": 5.0,
            "tr_min": 5.0,
            "tr_max": 10.0,
            "price_min": 5.0,
            "price_max": 80.0,
            "mcap_min": 30e8,
            "mcap_max": 300e8,
            "check_vol_trend": False,
            "check_limit_up": False,
        }

    def test_screen_stream_converts_string_numbers(self):
        source = pd.DataFrame([
            {
                "股票代码": "1",
                "股票名称": "测试股票",
                "最新价": "10.50",
                "涨跌幅": "3.20",
                "量比": "1.80",
                "换手率": "6.50",
                "总市值": "10000000000",
            },
            {
                "股票代码": "2",
                "股票名称": "无效数据",
                "最新价": "-",
                "涨跌幅": "-",
                "量比": "-",
                "换手率": "-",
                "总市值": "-",
            },
            {
                "股票代码": "1",
                "股票名称": "测试股票",
                "最新价": "10.60",
                "涨跌幅": "3.30",
                "量比": "1.90",
                "换手率": "6.60",
                "总市值": "10100000000",
            },
        ])
        conditions = self._base_conditions()

        screener = StockScreener()
        try:
            result = screener.screen_stream(source, conditions)
        finally:
            screener.fetcher.session.close()

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["股票代码"], "000001")
        self.assertEqual(result.iloc[0]["最新价"], 10.6)

    def test_screen_stream_applies_custom_range_conditions(self):
        source = pd.DataFrame([
            {
                "股票代码": "1",
                "股票名称": "符合自定义条件",
                "最新价": 10.5,
                "涨跌幅": 3.2,
                "量比": 1.8,
                "换手率": 6.5,
                "总市值": 100e8,
            },
            {
                "股票代码": "2",
                "股票名称": "不符合自定义条件",
                "最新价": 20.0,
                "涨跌幅": 3.0,
                "量比": 2.0,
                "换手率": 7.0,
                "总市值": 120e8,
            },
        ])
        conditions = self._base_conditions()
        conditions["custom_conditions"] = [{
            "label": "最新价 (元)",
            "column": "最新价",
            "min": 10.0,
            "max": 11.0,
        }]

        screener = StockScreener()
        try:
            result = screener.screen_stream(source, conditions)
        finally:
            screener.fetcher.session.close()

        self.assertEqual(result["股票代码"].tolist(), ["000001"])

    def test_screen_stream_rejects_incomplete_custom_condition(self):
        source = pd.DataFrame([{
            "股票代码": "1",
            "股票名称": "测试股票",
            "最新价": 10.5,
            "涨跌幅": 3.2,
            "量比": 1.8,
            "换手率": 6.5,
            "总市值": 100e8,
        }])
        conditions = self._base_conditions()
        conditions["custom_conditions"] = [{
            "label": "最新价 (元)",
            "column": "最新价",
            "min": None,
            "max": 11.0,
        }]

        screener = StockScreener()
        try:
            with self.assertRaisesRegex(ValueError, "需要同时填写"):
                screener.screen_stream(source, conditions)
        finally:
            screener.fetcher.session.close()

    def test_board_inclusion_switches_exclude_chinext_and_star_market(self):
        source = pd.DataFrame([
            {
                "股票代码": "300001",
                "股票名称": "创业板股票",
                "最新价": 10.0,
                "涨跌幅": 3.0,
                "量比": 2.0,
                "换手率": 6.0,
                "总市值": 100e8,
            },
            {
                "股票代码": "688001",
                "股票名称": "科创板股票",
                "最新价": 20.0,
                "涨跌幅": 3.0,
                "量比": 2.0,
                "换手率": 6.0,
                "总市值": 100e8,
            },
            {
                "股票代码": "000001",
                "股票名称": "主板股票",
                "最新价": 15.0,
                "涨跌幅": 3.0,
                "量比": 2.0,
                "换手率": 6.0,
                "总市值": 100e8,
            },
        ])
        conditions = self._base_conditions()
        conditions["include_chinext"] = False
        conditions["include_star_market"] = False

        screener = StockScreener()
        try:
            result = screener.screen_stream(source, conditions)
        finally:
            screener.fetcher.session.close()

        self.assertEqual(result["股票代码"].tolist(), ["000001"])

    def test_macd_golden_cross_detects_latest_cross(self):
        kline = pd.DataFrame({"收盘": [10.0] * 58 + [9.0, 11.0]})

        self.assertTrue(EastMoneyFetcher.check_macd_golden_cross(kline))

    def test_screen_stream_applies_macd_condition_with_60_day_history(self):
        source = pd.DataFrame([{
            "股票代码": "000001",
            "股票名称": "MACD金叉股票",
            "最新价": 10.5,
            "涨跌幅": 3.2,
            "量比": 1.8,
            "换手率": 6.5,
            "总市值": 100e8,
        }])
        kline = pd.DataFrame({"收盘": [10.0] * 58 + [9.0, 11.0]})
        requested_days = []

        conditions = self._base_conditions()
        conditions["check_macd"] = True

        screener = StockScreener()
        screener.fetcher.batch_check_history = lambda codes, days: (
            requested_days.append(days) or {"000001": kline}
        )
        try:
            result = screener.screen_stream(source, conditions)
        finally:
            screener.fetcher.session.close()

        self.assertEqual(requested_days, [60])
        self.assertEqual(result["股票代码"].tolist(), ["000001"])
        self.assertEqual(result.iloc[0]["MACD金叉"], "是")


if __name__ == "__main__":
    unittest.main()
