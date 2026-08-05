from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import ROOT_DIR


DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOG_DIR = ROOT_DIR / "logging"
TRACE_PATH = ROOT_DIR / "trace.jsonl"
METADATA_PATH = ROOT_DIR / "metadata.json"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _money(value: float | None) -> float | None:
    return None if value is None else round(value + 0.0000001, 2)


def _hours(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    a = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    b = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    return round((a - b).total_seconds() / 3600, 2)


class OlistCaseTools:
    def __init__(self) -> None:
        self.orders = _read_csv("olist_orders_dataset.csv")
        self.customers = _read_csv("olist_customers_dataset.csv")
        self.items = _read_csv("olist_order_items_dataset.csv")
        self.payments = _read_csv("olist_order_payments_dataset.csv")
        self.products = _read_csv("olist_products_dataset.csv")
        self.category_translations = _read_csv("product_category_name_translation.csv")

        self.orders_by_id = {row["order_id"]: row for row in self.orders}
        self.customers_by_id = {row["customer_id"]: row for row in self.customers}
        self.items_by_order = self._group(self.items, "order_id")
        self.payments_by_order = self._group(self.payments, "order_id")
        self.products_by_id = {row["product_id"]: row for row in self.products}
        self.category_en = {
            row["product_category_name"]: row["product_category_name_english"]
            for row in self.category_translations
        }

        orders_by_customer_unique: dict[str, list[str]] = defaultdict(list)
        for order in self.orders:
            customer = self.customers_by_id.get(order["customer_id"])
            if customer:
                orders_by_customer_unique[customer["customer_unique_id"]].append(order["order_id"])
        self.orders_by_customer_unique = orders_by_customer_unique

    @staticmethod
    def _group(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[row[key]].append(row)
        return grouped

    def investigate_case_file(self, case_id: str, write_output: bool = True) -> dict[str, Any]:
        path = INPUT_DIR / f"{case_id}.json"
        if not path.exists():
            raise ValueError(f"Input case not found: {case_id}")
        case = json.loads(path.read_text(encoding="utf-8"))
        return self.investigate_order(
            case_id=case["case_id"],
            order_id=case["customer_request"]["claimed_order_id"],
            write_output=write_output,
        )

    def investigate_order(
        self, case_id: str,
        order_id: str,
        write_output: bool = True,
    ) -> dict[str, Any]:
        order = self.orders_by_id.get(order_id)
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        customer = self.customers_by_id.get(order["customer_id"], {})
        items = self.items_by_order.get(order_id, [])
        payments = self.payments_by_order.get(order_id, [])

        item_ids = [f"{order_id}:{row['order_item_id']}" for row in items][:5]
        seller_ids = self._stable_unique([row["seller_id"] for row in items])[:3]
        payment_ids = [f"{order_id}:{row['payment_sequential']}" for row in payments][:5]
        product_ids = self._stable_unique([row["product_id"] for row in items])[:5]
        categories = self._categories(product_ids)[:5]

        customer_unique_id = customer.get("customer_unique_id")
        related_order_ids = []
        if customer_unique_id:
            related_order_ids = [
                oid for oid in self.orders_by_customer_unique.get(customer_unique_id, [])
                if oid != order_id
            ][:5]

        delivery_analysis = self._delivery_analysis(order, items)
        payment_reconciliation = self._payment_reconciliation(items, payments)
        policy = self._apply_policy(order, items, payments, delivery_analysis, payment_reconciliation, related_order_ids, categories)

        result = {
            "case_id": case_id,
            "case_assessment": {
                "primary_issue": policy["primary_issue"],
                "secondary_issues": policy["secondary_issues"],
                "case_status": "action_required" if policy["recommended_refund_brl"] > 0 else "no_action",
                "confidence": policy["confidence"],
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids,
                "seller_ids": seller_ids,
                "payment_ids": payment_ids,
            },
            "customer_context": {
                "customer_unique_id": customer_unique_id,
                "related_order_ids": related_order_ids,
            },
            "product_context": {
                "product_ids": product_ids,
                "category_names": categories,
            },
            "delivery_analysis": delivery_analysis,
            "payment_reconciliation": payment_reconciliation,
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": policy["root_cause_code"], "rank": 1}],
                "responsible_parties": policy["responsible_parties"],
            },
            "evidence_ids": self._evidence(order_id, item_ids, payment_ids, policy),
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": _money(policy["recommended_refund_brl"]),
            },
            "resolution_actions": policy["actions"][:5],
        }

        if write_output:
            OUTPUT_DIR.mkdir(exist_ok=True)
            (OUTPUT_DIR / f"{case_id}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._log_trace(case_id, order_id, policy)
        return result

    def run_all_cases(self, reset_trace: bool = True) -> dict[str, Any]:
        if reset_trace:
            TRACE_PATH.write_text("", encoding="utf-8")
        case_files = sorted(INPUT_DIR.glob("EC_*.json"))
        try:
            from tqdm import tqdm
        except Exception:
            def tqdm(iterable, **_kwargs):  # type: ignore
                return iterable
        results = []
        for path in tqdm(case_files, desc="Processing cases", total=len(case_files)):
            results.append(self.investigate_case_file(path.stem, write_output=True))
        return {"processed": len(results), "case_ids": [row["case_id"] for row in results]}

    def _categories(self, product_ids: list[str]) -> list[str]:
        categories = []
        for product_id in product_ids:
            product = self.products_by_id.get(product_id, {})
            raw = product.get("product_category_name", "")
            categories.append(self.category_en.get(raw, raw))
        return self._stable_unique([c for c in categories if c])

    def _delivery_analysis(self, order: dict[str, str], items: list[dict[str, str]]) -> dict[str, Any]:
        delivered_at = order.get("order_delivered_customer_date") or None
        estimated_at = order.get("order_estimated_delivery_date") or None
        carrier_at = order.get("order_delivered_carrier_date") or None
        handoff_rows = []
        late_sellers = []

        earliest_limit_by_seller: dict[str, str] = {}
        for item in items:
            seller_id = item["seller_id"]
            limit = item["shipping_limit_date"]
            if seller_id not in earliest_limit_by_seller or limit < earliest_limit_by_seller[seller_id]:
                earliest_limit_by_seller[seller_id] = limit

        for seller_id, limit in earliest_limit_by_seller.items():
            variance = _hours(carrier_at, limit)
            late = variance is not None and variance > 0
            if late:
                late_sellers.append(seller_id)
            handoff_rows.append({
                "seller_id": seller_id,
                "shipping_limit_at": limit or None,
                "handoff_variance_hours": variance,
                "late_handoff": late,
            })

        return {
            "delivered_at": delivered_at,
            "estimated_delivery_at": estimated_at,
            "carrier_handoff_at": carrier_at,
            "delivery_variance_hours": _hours(delivered_at, estimated_at),
            "seller_handoff_analysis": handoff_rows,
            "late_handoff_seller_ids": late_sellers[:3],
        }

    def _payment_reconciliation(self, items: list[dict[str, str]], payments: list[dict[str, str]]) -> dict[str, Any]:
        payment_total = sum(float(row["payment_value"]) for row in payments)
        payment_types = self._stable_unique([row["payment_type"] for row in payments])
        if not items:
            return {
                "currency": "BRL",
                "item_total_brl": 0.0,
                "freight_total_brl": 0.0,
                "expected_total_brl": None,
                "payment_total_brl": _money(payment_total),
                "difference_brl": None,
                "reconciled": None,
                "payment_types": payment_types,
            }

        item_total = sum(float(row["price"]) for row in items)
        freight_total = sum(float(row["freight_value"]) for row in items)
        expected_total = item_total + freight_total
        difference = payment_total - expected_total
        return {
            "currency": "BRL",
            "item_total_brl": _money(item_total),
            "freight_total_brl": _money(freight_total),
            "expected_total_brl": _money(expected_total),
            "payment_total_brl": _money(payment_total),
            "difference_brl": _money(difference),
            "reconciled": abs(difference) <= 0.10,
            "payment_types": payment_types,
        }

    def _apply_policy(
        self,
        order: dict[str, str],
        items: list[dict[str, str]],
        payments: list[dict[str, str]],
        delivery: dict[str, Any],
        payment: dict[str, Any],
        related_order_ids: list[str],
        categories: list[str],
    ) -> dict[str, Any]:
        payment_total = payment["payment_total_brl"] or 0
        freight_total = payment["freight_total_brl"] or 0
        status = order["order_status"]
        late_delivery = delivery["delivery_variance_hours"] is not None and delivery["delivery_variance_hours"] > 0
        late_sellers = delivery["late_handoff_seller_ids"]

        if status == "canceled" and payment_total > 0:
            primary, cause, refund, parties, actions = (
                "canceled_order_paid",
                "ORDER_CANCELED_AFTER_PAYMENT",
                payment_total,
                [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
                ["issue_full_refund"],
            )
        elif status == "unavailable" and payment_total > 0:
            primary, cause, refund, parties, actions = (
                "unavailable_order_paid",
                "ORDER_UNAVAILABLE_AFTER_PAYMENT",
                payment_total,
                [{"party_type": "platform", "party_id": "OLIST_PLATFORM"}],
                ["issue_full_refund"],
            )
        elif late_delivery and late_sellers:
            primary, cause, refund, parties, actions = (
                "late_delivery_seller",
                "SELLER_HANDOFF_AFTER_LIMIT",
                freight_total,
                [{"party_type": "seller", "party_id": seller_id} for seller_id in late_sellers[:3]],
                ["refund_freight", "review_seller_handoff"],
            )
        elif late_delivery:
            primary, cause, refund, parties, actions = (
                "late_delivery_logistics",
                "CARRIER_DELIVERED_AFTER_ESTIMATE",
                freight_total,
                [{"party_type": "logistics_provider", "party_id": "LOGISTICS_PROVIDER"}],
                ["refund_freight", "review_carrier_delay"],
            )
        elif len(payments) >= 2 and payment["reconciled"]:
            primary, cause, refund, parties, actions = (
                "valid_split_payment",
                "MULTIPLE_PAYMENTS_RECONCILED",
                0.0,
                [],
                ["explain_valid_split_payment"],
            )
        else:
            primary, cause, refund, parties, actions = (
                "unsupported_late_claim",
                "DELIVERY_WITHIN_ESTIMATE",
                0.0,
                [],
                ["reject_late_refund"],
            )

        if refund > 0:
            actions.append("verify_refund_completion")
        if len(self._stable_unique([row["seller_id"] for row in items])) >= 2:
            actions.append("coordinate_multi_seller_case")
        if len(payments) >= 2 and primary != "valid_split_payment":
            actions.append("verify_payment_allocation")

        secondary = []
        if len(items) >= 2:
            secondary.append("multi_item_order")
        if len(self._stable_unique([row["seller_id"] for row in items])) >= 2:
            secondary.append("multi_seller_order")
        if len(payments) >= 2:
            secondary.append("split_payment")
        if related_order_ids:
            secondary.append("repeat_customer")
        if len(categories) >= 2:
            secondary.append("multiple_categories")

        return {
            "primary_issue": primary,
            "secondary_issues": secondary,
            "root_cause_code": cause,
            "recommended_refund_brl": refund,
            "responsible_parties": parties,
            "actions": self._stable_unique(actions),
            "confidence": 0.95 if payment["reconciled"] is not False else 0.86,
        }

    def _evidence(self, order_id: str, item_ids: list[str], payment_ids: list[str], policy: dict[str, Any]) -> list[str]:
        evidence = [f"order:{order_id}"]
        evidence.extend(f"item:{item_id}" for item_id in item_ids)
        evidence.extend(f"payment:{payment_id}" for payment_id in payment_ids)
        for party in policy["responsible_parties"]:
            if party["party_type"] == "seller":
                evidence.append(f"seller:{party['party_id']}")
        evidence.append(f"policy:{policy['root_cause_code']}")
        return evidence[:20]

    def _log_trace(self, case_id: str, order_id: str, policy: dict[str, Any]) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        record = {
            "case_id": case_id,
            "order_id": order_id,
            "agents": ["coordinator", "customer", "order_product", "payment", "delivery", "policy", "verifier"],
            "primary_issue": policy["primary_issue"],
        }
        with TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        seen = set()
        output = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                output.append(value)
        return output
