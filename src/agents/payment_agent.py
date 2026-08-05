from __future__ import annotations

from decimal import Decimal

from src.datastore import OlistDataStore
from src.utils import money, unique


class PaymentAgent:
    name = "payment_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def analyze(self, order_id: str) -> dict:
        items = self.store.items_by_order.get(order_id, [])
        payments = self.store.payments_by_order.get(order_id, [])
        item_total = sum(
            (Decimal(row["price"]) for row in items), Decimal("0")
        )
        freight_total = sum(
            (Decimal(row["freight_value"]) for row in items), Decimal("0")
        )
        payment_total = sum(
            (Decimal(row["payment_value"]) for row in payments), Decimal("0")
        )
        has_items = bool(items)
        if has_items:
            expected = item_total + freight_total
            difference = payment_total - expected
            reconciled: bool | None = abs(difference) <= Decimal("0.10")
            expected_out: float | None = money(expected)
            difference_out: float | None = money(difference)
        else:
            expected_out = None
            difference_out = None
            reconciled = None
        return {
            "rows": payments,
            "payment_ids": [
                f"{order_id}:{row['payment_sequential']}" for row in payments
            ],
            "payment_total": payment_total,
            "payment_total_brl": money(payment_total),
            "item_total_brl": money(item_total),
            "freight_total_brl": money(freight_total),
            "expected_total_brl": expected_out,
            "difference_brl": difference_out,
            "reconciled": reconciled,
            "payment_types": unique(row["payment_type"] for row in payments),
            "split_payment": len(payments) >= 2,
        }
