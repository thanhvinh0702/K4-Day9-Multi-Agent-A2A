from __future__ import annotations

import unittest
from decimal import Decimal

from src.policy import PolicyAgent
from src.utils import hours_between, is_after, money, unique


class UtilityTests(unittest.TestCase):
    def test_unique_is_stable(self) -> None:
        self.assertEqual(unique(["b", "a", "b", "c"]), ["b", "a", "c"])

    def test_money_rounds_half_up(self) -> None:
        self.assertEqual(money(Decimal("1.005")), 1.01)

    def test_hour_variance(self) -> None:
        self.assertEqual(
            hours_between("2018-03-31 15:23:33", "2018-03-28 00:00:00"),
            87.39,
        )

    def test_classification_uses_raw_timestamp(self) -> None:
        self.assertTrue(
            is_after("2018-01-01 00:00:01", "2018-01-01 00:00:00")
        )


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = PolicyAgent()
        self.customer = {"repeat_customer": False}
        self.order_facts = {
            "multi_item_order": False,
            "multi_seller_order": False,
            "multiple_categories": False,
            "freight_total_brl": 10.0,
        }
        self.payment = {
            "payment_total": Decimal("100"),
            "payment_total_brl": 100.0,
            "split_payment": False,
            "reconciled": True,
        }
        self.delivery = {
            "delivered_late": False,
            "late_handoff_seller_ids": [],
        }

    def decide(self, status: str = "delivered") -> dict:
        return self.agent.decide(
            {"order_id": "order-1", "order_status": status},
            self.customer,
            self.order_facts,
            self.payment,
            self.delivery,
        )

    def test_canceled_has_priority_and_full_refund(self) -> None:
        self.delivery["delivered_late"] = True
        result = self.decide("canceled")
        self.assertEqual(result["primary_issue"], "canceled_order_paid")
        self.assertEqual(result["recommended_refund_brl"], 100.0)

    def test_seller_delay(self) -> None:
        self.delivery.update(
            {"delivered_late": True, "late_handoff_seller_ids": ["seller-1"]}
        )
        result = self.decide()
        self.assertEqual(result["primary_issue"], "late_delivery_seller")
        self.assertEqual(result["responsible_parties"][0]["party_id"], "seller-1")

    def test_valid_split_payment(self) -> None:
        self.payment["split_payment"] = True
        result = self.decide()
        self.assertEqual(result["primary_issue"], "valid_split_payment")
        self.assertNotIn("verify_payment_allocation", result["actions"])


if __name__ == "__main__":
    unittest.main()
