import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from core.analyzer import ANALYSIS_PROMPT, StockAnalyzer


class FakeCompletions:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        content = """```json
        {
            "score": 82,
            "reason": "量价配合良好",
            "risk": "次日可能高开低走",
            "target_price": 12.5,
            "stop_loss": 9.2
        }
        ```"""
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class BlockedCompletions:
    def create(self, **kwargs):
        raise RuntimeError(
            "<!DOCTYPE html><html><title>Error - Request Blocked</title></html>"
        )


class AnalyzerTests(unittest.TestCase):
    def test_normalizes_deepseek_website_to_api(self):
        website = StockAnalyzer(
            api_key="test-key",
            base_url="https://www.deepseek.com/",
            model="deepseek-chat",
        )
        api_root = StockAnalyzer(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )

        self.assertEqual(website.base_url, "https://api.deepseek.com")
        self.assertEqual(api_root.base_url, "https://api.deepseek.com")

    def test_normalizes_deepseek_display_model_to_api_id(self):
        analyzer = StockAnalyzer(
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="DeepSeek V4 Pro",
        )

        self.assertEqual(analyzer.model, "deepseek-v4-pro")

    def test_prompt_format_preserves_json_object(self):
        prompt = ANALYSIS_PROMPT.format(
            code="000001",
            name="平安银行",
            price=10.0,
            pct_change=3.0,
            volume_ratio=1.5,
            turnover=6.0,
            market_cap=100.0,
            pe=8.0,
            limit_up_days=2,
        )

        self.assertIn('"score": <0-100的整数评分>', prompt)
        self.assertIn("股票代码：000001", prompt)

    def test_analyze_parses_fenced_json(self):
        completions = FakeCompletions()
        analyzer = StockAnalyzer(api_key="test-key", model="DeepSeek V4 Pro")
        analyzer._client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )

        result = analyzer.analyze({
            "code": "000001",
            "name": "平安银行",
            "price": 10.0,
        })

        self.assertEqual(result.score, 82)
        self.assertEqual(result.reason, "量价配合良好")
        self.assertEqual(result.current_price, 10.0)
        self.assertEqual(result.target_price, 12.5)
        self.assertAlmostEqual(result.target_gain_pct, 25.0)
        self.assertAlmostEqual(result.stop_loss_pct, 8.0)
        self.assertEqual(completions.last_kwargs["model"], "deepseek-v4-pro")

    def test_analyze_hides_blocked_html_response(self):
        analyzer = StockAnalyzer(
            api_key="test-key",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        analyzer._client = SimpleNamespace(
            chat=SimpleNamespace(completions=BlockedCompletions())
        )

        result = analyzer.analyze({"code": "002793", "name": "罗欣药业"})

        self.assertEqual(result.score, 0)
        self.assertIn("DeepSeek 安全网关", result.reason)
        self.assertNotIn("<!DOCTYPE html>", result.reason)

    @patch("core.analyzer.time.sleep", return_value=None)
    def test_analyze_batch_accepts_screening_results(self, _sleep):
        analyzer = StockAnalyzer(api_key="test-key")
        analyzer._client = SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
        screening_results = pd.DataFrame([
            {
                "股票代码": "000001",
                "股票名称": "平安银行",
                "最新价": 10.0,
                "涨跌幅": 3.0,
                "量比": 1.5,
                "换手率": 6.0,
                "总市值": 100e8,
            }
        ])

        results = analyzer.analyze_batch(screening_results)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].code, "000001")
        self.assertEqual(results[0].score, 82)
        self.assertEqual(results[0].current_price, 10.0)


if __name__ == "__main__":
    unittest.main()
