import tempfile
import unittest
import json
from io import BytesIO
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from openpyxl import load_workbook

from investment_tracker import server
from investment_tracker.ledger import calculate


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.assets = [
            {"id": 1, "name": "余额宝", "code": "CASH", "kind": "cash", "annual_rate": 0.01},
            {"id": 2, "name": "测试 ETF", "code": "510300", "secid": "1.510300", "kind": "security", "annual_rate": 0},
        ]

    def test_buy_sell_fees_interest_and_net_contribution(self):
        tx = [
            {"id": 1, "time": "2026-01-01T00:00", "type": "deposit", "asset_id": None, "amount": 10000, "quantity": 0, "price": 0, "fee": 0},
            {"id": 2, "time": "2026-01-01T00:00", "type": "buy", "asset_id": 2, "amount": 1001, "quantity": 100, "price": 10, "fee": 1},
            {"id": 3, "time": "2026-01-01T00:00", "type": "sell", "asset_id": 2, "amount": 598, "quantity": 50, "price": 12, "fee": 2},
        ]
        result = calculate(self.assets, tx, {2: {"price": 12, "source": "test", "time": "2026-01-01T00:00"}}, datetime(2026, 1, 1))
        position = result["positions"][0]
        self.assertEqual(result["cash"], 9597)
        self.assertEqual(result["equity"], 10197)
        self.assertEqual(result["profit"], 197)
        self.assertEqual(position["cost"], 500.5)
        self.assertEqual(position["realized"], 97.5)
        self.assertEqual(position["unrealized"], 99.5)
        self.assertEqual(position["quantity"], 50)
        after_sell = next(point for point in result["timeline"] if point["tx_id"] == 3)
        self.assertEqual(after_sell["asset_states"]["2"]["realized"], 97.5)
        self.assertEqual(after_sell["asset_states"]["2"]["unrealized"], 99.5)
        self.assertEqual(result["timeline"][-1]["asset_states"]["2"]["profit"], 197)

    def test_cash_interest_and_withdrawal(self):
        tx = [{"id": 1, "time": "2025-01-01T00:00", "type": "deposit", "asset_id": None, "amount": 36500, "quantity": 0, "price": 0, "fee": 0},
              {"id": 2, "time": "2026-01-01T00:00", "type": "withdraw", "asset_id": None, "amount": 500, "quantity": 0, "price": 0, "fee": 0}]
        result = calculate(self.assets, tx, {}, datetime(2026, 1, 1))
        self.assertEqual(result["interest"], 365)
        self.assertEqual(result["cash"], 36365)
        self.assertEqual(result["contributions"], 36000)
        self.assertEqual(result["profit"], 365)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.patch = patch.object(server, "DB_PATH", Path(self.temp.name) / "test.db")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_amount_mode_and_overdraw_rollback(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 1000})
            asset = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            server.add_transaction(db, {"type": "buy", "asset_id": asset, "time": "2026-01-02T00:00",
                                        "price": 4, "fee": 1, "amount": 401, "input_mode": "amount"})
            tx = db.execute("SELECT quantity,amount FROM transactions WHERE type='buy'").fetchone()
            self.assertEqual(tx["quantity"], 100)
            self.assertEqual(tx["amount"], 401)
            with self.assertRaisesRegex(ValueError, "现金余额为负"):
                server.add_transaction(db, {"type": "buy", "asset_id": asset, "time": "2026-01-02T01:00",
                                            "price": 10, "fee": 0, "quantity": 1000})
            self.assertEqual(db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 2)

    def test_oversell_rejected(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 1000})
            asset = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            with self.assertRaisesRegex(ValueError, "卖出数量超过"):
                server.add_transaction(db, {"type": "sell", "asset_id": asset, "time": "2026-01-02T00:00",
                                            "price": 10, "fee": 0, "quantity": 10})

    def test_edit_transaction_recalculates_and_invalid_edit_rolls_back(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 1000})
            asset = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            tx_id = server.add_transaction(db, {"type": "buy", "asset_id": asset,
                "time": "2026-01-02T00:00", "price": 4, "quantity": 100, "fee": 1})
            updated = server.update_transaction(db, {"id": tx_id, "type": "buy", "asset_id": asset,
                "time": "2026-01-02T00:00", "price": 4, "quantity": 125, "fee": 2, "note": "修正数量"})
            self.assertEqual(next(p for p in updated["portfolio"]["positions"] if p["id"] == asset)["quantity"], 125)
            self.assertEqual(db.execute("SELECT amount,note FROM transactions WHERE id=?", (tx_id,)).fetchone()["amount"], 502)
            with self.assertRaisesRegex(ValueError, "现金余额为负"):
                server.update_transaction(db, {"id": tx_id, "type": "buy", "asset_id": asset,
                    "time": "2026-01-02T00:00", "price": 4, "quantity": 1000, "fee": 2})
            saved = db.execute("SELECT quantity,amount,note FROM transactions WHERE id=?", (tx_id,)).fetchone()
            self.assertEqual((saved["quantity"], saved["amount"], saved["note"]), (125, 502, "修正数量"))

    def test_edit_preserves_sell_order_and_initial_funding(self):
        with server.database() as db:
            funding = server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 1000})
            asset = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            buy = server.add_transaction(db, {"type": "buy", "asset_id": asset,
                "time": "2026-01-02T00:00", "price": 4, "quantity": 100, "fee": 0})
            server.add_transaction(db, {"type": "sell", "asset_id": asset,
                "time": "2026-01-03T00:00", "price": 5, "quantity": 50, "fee": 0})
            with self.assertRaisesRegex(ValueError, "卖出数量超过"):
                server.update_transaction(db, {"id": buy, "type": "buy", "asset_id": asset,
                    "time": "2026-01-02T00:00", "price": 4, "quantity": 40, "fee": 0})
            self.assertEqual(db.execute("SELECT quantity FROM transactions WHERE id=?", (buy,)).fetchone()[0], 100)
            updated = server.update_transaction(db, {"id": funding, "type": "deposit",
                "time": "2026-01-01T00:00", "amount": 1200, "note": "修正初始资金"})
            self.assertEqual(updated["portfolio"]["contributions"], 1200)
            self.assertEqual(len(updated["transactions"]), 3)

    def test_exports_include_post_trade_results(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 1000})
            asset = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            server.add_transaction(db, {"type": "buy", "asset_id": asset, "time": "2026-01-02T00:00",
                                        "price": 4, "fee": 1, "quantity": 100})
            csv_data, _, _ = server.export_file(db, "csv")
            xlsx_data, _, _ = server.export_file(db, "xlsx")
            self.assertIn("交易后账户总资产", csv_data.decode("utf-8-sig"))
            self.assertIn("沪深300 ETF", csv_data.decode("utf-8-sig"))
            self.assertTrue(xlsx_data.startswith(b"PK"))
            workbook = load_workbook(BytesIO(xlsx_data), read_only=True)
            self.assertEqual([cell.value for cell in workbook["标的曲线"][1]][5:9],
                             ["已实现收益", "浮动盈亏", "累计盈亏", "收益率%"])
            workbook.close()

    def test_market_code_is_derived_and_quote_loaded_on_add(self):
        self.assertEqual(server.derive_secid("159941"), "0.159941")
        self.assertEqual(server.derive_secid("510300"), "1.510300")
        with server.database() as db, patch.object(server, "fetch_quote", side_effect=lambda asset: {
            "asset_id": asset["id"], "price": 1.690, "time": "2026-10-29T16:14", "source": "腾讯行情"
        }):
            result = server.add_asset(db, {"name": "纳指ETF广发", "code": "159941"})
            asset = next(a for a in result["assets"] if a["code"] == "159941")
            self.assertEqual(asset["secid"], "0.159941")
            self.assertEqual(result["portfolio"]["positions"][-1]["price"], 1.690)

    def test_existing_wrong_etf_market_code_is_repaired(self):
        with server.database() as db:
            db.execute("INSERT INTO assets(name,code,secid,kind) VALUES('纳指ETF广发','159941','1.159941','security')")
            asset_id = db.execute("SELECT id FROM assets WHERE code='159941'").fetchone()[0]
            db.execute("INSERT INTO quotes(asset_id,price,time,source) VALUES(?,9.99,'2026-10-29T10:00','手动')", (asset_id,))
            db.commit()
        with server.database() as db:
            self.assertEqual(db.execute("SELECT secid FROM assets WHERE code='159941'").fetchone()[0], "0.159941")
            self.assertIsNone(db.execute("SELECT price FROM quotes WHERE asset_id=?", (asset_id,)).fetchone())

    def test_gold_quote_uses_sge_price_and_actual_quote_time(self):
        self.assertEqual(server.derive_secid("Au9999"), "118.AU9999")
        payload = {"heyue": "Au99.99", "delaystr": "2026年10月29日 15:45:00",
                   "times": ["15:28", "15:29", "15:30", "15:31"],
                   "data": ["864.44", "864.70", "864.70", "0.0"]}
        with patch.object(server, "urlopen", return_value=BytesIO(json.dumps(payload).encode())):
            quote = server.fetch_quote_sge({"id": 5, "code": "Au9999"})
        self.assertEqual(quote["price"], 864.7)
        self.assertEqual(quote["time"], "2026-10-29T15:30")
        self.assertEqual(quote["source"], "上金所延时行情")
        payload["delaystr"] = "2099年10月29日 15:45:00"
        with patch.object(server, "urlopen", return_value=BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(ValueError, "暂无有效价格"):
                server.fetch_quote_sge({"id": 5, "code": "Au9999"})

    def test_asset_removal_preserves_trade_history_and_cash(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 300000})
            unused = db.execute("SELECT id FROM assets WHERE code='513100'").fetchone()[0]
            server.delete_asset(db, unused)
            self.assertIsNone(db.execute("SELECT 1 FROM assets WHERE id=?", (unused,)).fetchone())
            held = db.execute("SELECT id FROM assets WHERE code='510300'").fetchone()[0]
            server.add_transaction(db, {"type": "buy", "asset_id": held, "time": "2026-01-02T00:00",
                                        "price": 4, "fee": 0, "quantity": 100})
            before = server.current_state(db)
            after = server.delete_asset(db, held)
            self.assertEqual(len(after["transactions"]), len(before["transactions"]))
            self.assertEqual(after["portfolio"]["equity"], before["portfolio"]["equity"])
            self.assertFalse(next(a for a in after["assets"] if a["id"] == held)["is_active"])
            self.assertEqual(next(p for p in after["portfolio"]["positions"] if p["id"] == held)["quantity"], 100)
            server.restore_asset(db, held)
            self.assertTrue(db.execute("SELECT is_active FROM assets WHERE id=?", (held,)).fetchone()[0])

    def test_adding_capital_increases_cash_and_net_investment(self):
        with server.database() as db:
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-01T00:00", "amount": 300000})
            before = server.current_state(db)["portfolio"]
            server.add_transaction(db, {"type": "deposit", "time": "2026-01-02T00:00", "amount": 10000})
            after = server.current_state(db)["portfolio"]
            self.assertEqual(after["contributions"] - before["contributions"], 10000)
            self.assertGreater(after["cash"] - before["cash"], 9999)

    def test_tencent_quote_time_and_price(self):
        fields = [""] * 32
        fields[2], fields[3], fields[30] = "159941", "1.690", "20261029161400"
        payload = ('v_sz159941="' + '~'.join(fields) + '";').encode("gbk")
        with patch.object(server, "urlopen", return_value=BytesIO(payload)):
            quote = server.fetch_quote_tencent({"id": 5, "secid": "0.159941"})
        self.assertEqual(quote["price"], 1.690)
        self.assertEqual(quote["time"], "2026-10-29T16:14")


if __name__ == "__main__":
    unittest.main()
