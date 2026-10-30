"""Portfolio accounting. All values use CNY and average cost accounting."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")
ZERO = Decimal("0")


def dec(value: object) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_number(value: Decimal) -> float:
    return float(money(value))


def accrue(balance: Decimal, start: datetime, end: datetime, annual_rate: Decimal) -> Decimal:
    """Simple daily interest; no interest is earned on negative or zero cash."""
    seconds = max((end - start).total_seconds(), 0)
    if balance <= ZERO or seconds <= 0:
        return ZERO
    return balance * annual_rate * dec(seconds) / dec(365 * 24 * 3600)


def calculate(assets: list[dict], transactions: list[dict], quotes: dict, now: datetime) -> dict:
    positions = {a["id"]: {"quantity": ZERO, "basis": ZERO, "realized": ZERO,
                             "bought": ZERO, "sold": ZERO} for a in assets if a["kind"] == "security"}
    annual_rate = dec(next((a["annual_rate"] for a in assets if a["kind"] == "cash"), 0.01))
    cash = ZERO
    interest = ZERO
    contributions = ZERO
    timeline = []
    last_time = None
    last_prices = {}

    def snapshot(at: datetime, label: str, tx_id: int | None = None) -> None:
        values = {}
        asset_states = {}
        for asset in assets:
            if asset["kind"] == "security":
                p = positions[asset["id"]]
                price = last_prices.get(asset["id"], ZERO)
                value = p["quantity"] * price
                unrealized = value - p["basis"]
                total_profit = p["realized"] + unrealized
                values[str(asset["id"])] = as_number(value)
                asset_states[str(asset["id"])] = {
                    "quantity": float(p["quantity"]), "value": as_number(value),
                    "realized": as_number(p["realized"]), "unrealized": as_number(unrealized),
                    "profit": as_number(total_profit),
                    "return_rate": float(total_profit / p["bought"] * 100) if p["bought"] else 0,
                }
        equity = cash + sum((dec(v) for v in values.values()), ZERO)
        timeline.append({"time": at.isoformat(timespec="minutes"), "label": label,
                         "tx_id": tx_id,
                         "equity": as_number(equity), "profit": as_number(equity - contributions),
                         "return_rate": float((equity - contributions) / contributions * 100) if contributions > 0 else 0,
                         "cash": as_number(cash), "contributions": as_number(contributions),
                         "assets": values, "asset_states": asset_states})

    for tx in sorted(transactions, key=lambda t: (t["time"], t["id"])):
        at = datetime.fromisoformat(tx["time"])
        if last_time is not None:
            gain = accrue(cash, last_time, at, annual_rate)
            cash += gain
            interest += gain
        kind = tx["type"]
        amount = dec(tx["amount"])
        if kind == "deposit":
            cash += amount
            contributions += amount
        elif kind == "withdraw":
            cash -= amount
            contributions -= amount
        else:
            p = positions[tx["asset_id"]]
            quantity = dec(tx["quantity"])
            price = dec(tx["price"])
            fee = dec(tx["fee"])
            if kind == "buy":
                cash -= amount
                p["quantity"] += quantity
                p["basis"] += amount
                p["bought"] += amount
            elif kind == "sell":
                previous_qty = p["quantity"]
                released_basis = p["basis"] * quantity / previous_qty if previous_qty else ZERO
                p["quantity"] -= quantity
                p["basis"] -= released_basis
                p["realized"] += amount - released_basis
                p["sold"] += amount
                cash += amount
            last_prices[tx["asset_id"]] = price
        last_time = at
        snapshot(at, kind, tx["id"])

    if last_time is not None:
        gain = accrue(cash, last_time, now, annual_rate)
        cash += gain
        interest += gain

    rows = []
    value_sum = ZERO
    for asset in assets:
        if asset["kind"] != "security":
            continue
        p = positions[asset["id"]]
        quote = quotes.get(asset["id"])
        live_price = dec(quote["price"]) if quote and quote.get("price") is not None else None
        price = live_price if live_price is not None else last_prices.get(asset["id"])
        market_value = p["quantity"] * price if price is not None else ZERO
        unrealized = market_value - p["basis"] if price is not None else ZERO
        total_profit = p["realized"] + unrealized
        value_sum += market_value
        rows.append({"id": asset["id"], "name": asset["name"], "code": asset["code"],
                     "secid": asset["secid"], "quantity": float(p["quantity"]),
                     "average_cost": float(p["basis"] / p["quantity"]) if p["quantity"] else 0,
                     "cost": as_number(p["basis"]), "price": float(price) if price is not None else None,
                     "market_value": as_number(market_value), "realized": as_number(p["realized"]),
                     "unrealized": as_number(unrealized), "profit": as_number(total_profit),
                     "return_rate": float(total_profit / p["bought"] * 100) if p["bought"] else 0,
                     "bought": as_number(p["bought"]), "sold": as_number(p["sold"]),
                     "quote_source": quote.get("source") if quote else ("最近成交价" if price else "无价格"),
                     "quote_time": quote.get("time") if quote else None})

    equity = cash + value_sum
    profit = equity - contributions
    if timeline:
        snapshot(now, "当前")
        timeline[-1]["assets"] = {str(r["id"]): r["market_value"] for r in rows}
        timeline[-1]["equity"] = as_number(equity)
        timeline[-1]["profit"] = as_number(profit)
        timeline[-1]["cash"] = as_number(cash)
        timeline[-1]["return_rate"] = float(profit / contributions * 100) if contributions > 0 else 0
        timeline[-1]["asset_states"] = {
            str(r["id"]): {"quantity": r["quantity"], "value": r["market_value"],
                            "realized": r["realized"], "unrealized": r["unrealized"],
                            "profit": r["profit"], "return_rate": r["return_rate"]} for r in rows
        }

    return {"cash": as_number(cash), "interest": as_number(interest),
            "contributions": as_number(contributions), "market_value": as_number(value_sum),
            "equity": as_number(equity), "profit": as_number(profit),
            "return_rate": float(profit / contributions * 100) if contributions > 0 else 0,
            "positions": rows, "timeline": timeline}
