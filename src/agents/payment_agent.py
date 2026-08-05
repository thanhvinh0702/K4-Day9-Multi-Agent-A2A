from __future__ import annotations

from decimal import Decimal

from src.datastore import OlistDataStore
from src.utils import money, unique


class PaymentAgent:
    name = "payment_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def reconcile(self, order_id: str, order_facts: dict) -> dict:
        payments = self.store.payments_by_order.get(order_id, [])
        payment_total = sum(
            (Decimal(row["payment_value"]) for row in payments), Decimal("0")
        )
        has_items = bool(order_facts["items"])
        if has_items:
            expected = order_facts["item_total"] + order_facts["freight_total"]
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
            "expected_total_brl": expected_out,
            "difference_brl": difference_out,
            "reconciled": reconciled,
            "payment_types": unique(row["payment_type"] for row in payments),
            "split_payment": len(payments) >= 2,
        }

