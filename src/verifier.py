from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import math

from src.datastore import OlistDataStore
from src.policy import POLICY
from src.utils import hours_between, is_after, money, unique


LIMITS = {
    ("affected_entities", "order_ids"): 5,
    ("affected_entities", "item_ids"): 5,
    ("affected_entities", "seller_ids"): 3,
    ("affected_entities", "payment_ids"): 5,
    ("customer_context", "related_order_ids"): 5,
    ("product_context", "product_ids"): 5,
    ("product_context", "category_names"): 5,
    ("root_cause_analysis", "ranked_causes"): 3,
    ("root_cause_analysis", "responsible_parties"): 3,
}

EXPECTED_KEYS = {
    "case_id",
    "case_assessment",
    "affected_entities",
    "customer_context",
    "product_context",
    "delivery_analysis",
    "payment_reconciliation",
    "root_cause_analysis",
    "evidence_ids",
    "financial_resolution",
    "resolution_actions",
}
NESTED_KEYS = {
    "case_assessment": {"primary_issue", "secondary_issues", "case_status", "confidence"},
    "affected_entities": {"order_ids", "item_ids", "seller_ids", "payment_ids"},
    "customer_context": {"customer_unique_id", "related_order_ids"},
    "product_context": {"product_ids", "category_names"},
    "delivery_analysis": {
        "delivered_at",
        "estimated_delivery_at",
        "carrier_handoff_at",
        "delivery_variance_hours",
        "seller_handoff_analysis",
        "late_handoff_seller_ids",
    },
    "payment_reconciliation": {
        "currency",
        "item_total_brl",
        "freight_total_brl",
        "expected_total_brl",
        "payment_total_brl",
        "difference_brl",
        "reconciled",
        "payment_types",
    },
    "root_cause_analysis": {"ranked_causes", "responsible_parties"},
    "financial_resolution": {"currency", "recommended_refund_brl"},
}


def normalize_llm_decision(
    deterministic: dict, llm_decision: dict | None
) -> tuple[dict, bool]:
    """Accept only LLM confidence when every business field matches code policy."""
    result = deepcopy(deterministic)
    if llm_decision is None:
        return result, False
    expected = {
        "primary_issue": deterministic["primary_issue"],
        "cause_code": deterministic["cause_code"],
        "responsible_parties": deterministic["responsible_parties"],
        "recommended_refund_brl": deterministic["recommended_refund_brl"],
        "primary_action": deterministic["actions"][0],
    }
    if any(llm_decision.get(key) != value for key, value in expected.items()):
        return result, False
    try:
        result["confidence"] = round(
            min(1.0, max(0.0, float(llm_decision["confidence"]))), 2
        )
    except (KeyError, TypeError, ValueError):
        return deepcopy(deterministic), False
    return result, True


class VerifierAgent:
    name = "verifier_agent"

    def __init__(self, store: OlistDataStore):
        self.store = store

    def build_output(
        self,
        case: dict,
        order_seller: dict,
        payment: dict,
        delivery: dict,
        customer: dict,
        decision: dict,
    ) -> dict:
        order_id = order_seller["order_id"]
        cause = decision["cause_code"]
        item_ids = order_seller["item_ids"][:5]
        payment_ids = payment["payment_ids"][:5]
        evidence = [f"order:{order_id}"]
        evidence.extend(f"item:{value}" for value in item_ids)
        evidence.extend(f"payment:{value}" for value in payment_ids)
        if decision["primary_issue"] == "late_delivery_seller":
            evidence.extend(
                f"seller:{seller_id}"
                for seller_id in order_seller["late_handoff_seller_ids"][:3]
            )
        evidence.append(f"policy:{cause}")
        output = {
            "case_id": case["case_id"],
            "case_assessment": {
                "primary_issue": decision["primary_issue"],
                "secondary_issues": decision["secondary_issues"],
                "case_status": decision["case_status"],
                "confidence": decision["confidence"],
            },
            "affected_entities": {
                "order_ids": [order_id],
                "item_ids": item_ids,
                "seller_ids": order_seller["seller_ids"][:3],
                "payment_ids": payment_ids,
            },
            "customer_context": {
                "customer_unique_id": customer["customer_unique_id"],
                "related_order_ids": customer["related_order_ids"][:5],
            },
            "product_context": {
                "product_ids": order_seller["product_ids"][:5],
                "category_names": order_seller["category_names"][:5],
            },
            "delivery_analysis": {
                "delivered_at": delivery["delivered_at"],
                "estimated_delivery_at": delivery["estimated_delivery_at"],
                "carrier_handoff_at": order_seller["carrier_handoff_at"],
                "delivery_variance_hours": delivery["delivery_variance_hours"],
                "seller_handoff_analysis": order_seller["seller_handoff_analysis"][:3],
                "late_handoff_seller_ids": order_seller["late_handoff_seller_ids"][:3],
            },
            "payment_reconciliation": {
                "currency": "BRL",
                "item_total_brl": payment["item_total_brl"],
                "freight_total_brl": payment["freight_total_brl"],
                "expected_total_brl": payment["expected_total_brl"],
                "payment_total_brl": payment["payment_total_brl"],
                "difference_brl": payment["difference_brl"],
                "reconciled": payment["reconciled"],
                "payment_types": payment["payment_types"],
            },
            "root_cause_analysis": {
                "ranked_causes": [{"cause_code": cause, "rank": 1}],
                "responsible_parties": decision["responsible_parties"][:3],
            },
            "evidence_ids": evidence[:20],
            "financial_resolution": {
                "currency": "BRL",
                "recommended_refund_brl": decision["recommended_refund_brl"],
            },
            "resolution_actions": decision["actions"][:5],
        }
        self.verify_output(case, output)
        return output

    def verify_output(self, case: dict, output: dict) -> None:
        errors: list[str] = []
        order_id = case["customer_request"]["claimed_order_id"]
        if set(output) != EXPECTED_KEYS:
            errors.append("top-level schema keys mismatch")
        for section, keys in NESTED_KEYS.items():
            if set(output.get(section, {})) != keys:
                errors.append(f"{section} schema keys mismatch")
        if self._has_non_finite_number(output):
            errors.append("output contains NaN or Infinity")
        if output["case_id"] != case["case_id"]:
            errors.append("case_id mismatch")
        if output["affected_entities"]["order_ids"] != [order_id]:
            errors.append("affected order must be claimed order only")
        if not 0 <= output["case_assessment"]["confidence"] <= 1:
            errors.append("confidence outside [0,1]")
        refund = output["financial_resolution"]["recommended_refund_brl"]
        expected_status = "action_required" if refund > 0 else "no_action"
        if output["case_assessment"]["case_status"] != expected_status:
            errors.append("case_status does not match refund")
        if len(output["evidence_ids"]) > 20 or len(output["resolution_actions"]) > 5:
            errors.append("evidence/action limit exceeded")
        for path, limit in LIMITS.items():
            if len(output[path[0]][path[1]]) > limit:
                errors.append(f"{'.'.join(path)} exceeds {limit}")
        if order_id in output["customer_context"]["related_order_ids"]:
            errors.append("claimed order appears in customer history")

        order = self.store.orders[order_id]
        item_rows = self.store.items_by_order.get(order_id, [])
        payment_rows = self.store.payments_by_order.get(order_id, [])
        expected_items = [f"{order_id}:{row['order_item_id']}" for row in item_rows][
            :5
        ]
        expected_payments = [
            f"{order_id}:{row['payment_sequential']}"
            for row in payment_rows
        ][:5]
        expected_sellers = unique(row["seller_id"] for row in item_rows)[:3]
        expected_products = unique(row["product_id"] for row in item_rows)[:5]
        expected_categories = unique(
            product["product_category_name"]
            for product_id in unique(row["product_id"] for row in item_rows)
            if (product := self.store.products.get(product_id))
            and product["product_category_name"]
        )[:5]
        affected = output["affected_entities"]
        if affected["item_ids"] != expected_items:
            errors.append("item IDs are incomplete, invalid, or out of order")
        if affected["payment_ids"] != expected_payments:
            errors.append("payment IDs are incomplete, invalid, or out of order")
        if affected["seller_ids"] != expected_sellers:
            errors.append("seller IDs are incomplete, invalid, or out of order")
        if output["product_context"]["product_ids"] != expected_products:
            errors.append("product IDs mismatch")
        if output["product_context"]["category_names"] != expected_categories:
            errors.append("category names mismatch")

        customer = self.store.customers[order["customer_id"]]
        unique_id = customer["customer_unique_id"]
        related = [
            value
            for value in self.store.orders_by_customer_unique.get(unique_id, [])
            if value != order_id
        ][:5]
        if output["customer_context"] != {
            "customer_unique_id": unique_id,
            "related_order_ids": related,
        }:
            errors.append("customer context mismatch")

        item_total = sum((Decimal(row["price"]) for row in item_rows), Decimal("0"))
        freight_total = sum(
            (Decimal(row["freight_value"]) for row in item_rows), Decimal("0")
        )
        payment_total = sum(
            (Decimal(row["payment_value"]) for row in payment_rows), Decimal("0")
        )
        expected_total = item_total + freight_total if item_rows else None
        difference = payment_total - expected_total if expected_total is not None else None
        reconciliation = output["payment_reconciliation"]
        expected_reconciliation = {
            "currency": "BRL",
            "item_total_brl": money(item_total),
            "freight_total_brl": money(freight_total),
            "expected_total_brl": money(expected_total) if expected_total is not None else None,
            "payment_total_brl": money(payment_total),
            "difference_brl": money(difference) if difference is not None else None,
            "reconciled": abs(difference) <= Decimal("0.10") if difference is not None else None,
            "payment_types": unique(row["payment_type"] for row in payment_rows),
        }
        if reconciliation != expected_reconciliation:
            errors.append("payment reconciliation mismatch")
        if not item_rows:
            for field in ("expected_total_brl", "difference_brl", "reconciled"):
                if reconciliation[field] is not None:
                    errors.append(f"{field} must be null without items")

        delivery = output["delivery_analysis"]
        delivered = order["order_delivered_customer_date"] or None
        estimated = order["order_estimated_delivery_date"] or None
        carrier = order["order_delivered_carrier_date"] or None
        expected_handoffs = []
        for seller_id in unique(row["seller_id"] for row in item_rows):
            limits = [
                row["shipping_limit_date"]
                for row in item_rows
                if row["seller_id"] == seller_id and row["shipping_limit_date"]
            ]
            limit = min(limits) if limits else None
            expected_handoffs.append(
                {
                    "seller_id": seller_id,
                    "shipping_limit_at": limit,
                    "handoff_variance_hours": hours_between(carrier or "", limit or ""),
                    "late_handoff": is_after(carrier, limit),
                }
            )
        expected_late_sellers = [
            row["seller_id"] for row in expected_handoffs if row["late_handoff"]
        ][:3]
        expected_delivery = {
            "delivered_at": delivered,
            "estimated_delivery_at": estimated,
            "carrier_handoff_at": carrier,
            "delivery_variance_hours": hours_between(delivered or "", estimated or ""),
            "seller_handoff_analysis": expected_handoffs[:3],
            "late_handoff_seller_ids": expected_late_sellers,
        }
        if delivery != expected_delivery:
            errors.append("delivery analysis mismatch")
        for timestamp in (delivered, estimated, carrier):
            if timestamp:
                try:
                    datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    errors.append("timestamp format mismatch")

        secondary = []
        if len(item_rows) >= 2:
            secondary.append("multi_item_order")
        if len(unique(row["seller_id"] for row in item_rows)) >= 2:
            secondary.append("multi_seller_order")
        if len(payment_rows) >= 2:
            secondary.append("split_payment")
        if related:
            secondary.append("repeat_customer")
        if len(unique(
            self.store.products[row["product_id"]]["product_category_name"]
            for row in item_rows
            if self.store.products[row["product_id"]]["product_category_name"]
        )) >= 2:
            secondary.append("multiple_categories")
        if output["case_assessment"]["secondary_issues"] != secondary:
            errors.append("secondary issues mismatch")

        status = order["order_status"]
        delivered_late = is_after(delivered, estimated)
        reconciled = expected_reconciliation["reconciled"]
        if status == "canceled" and payment_total > 0:
            expected_issue = "canceled_order_paid"
        elif status == "unavailable" and payment_total > 0:
            expected_issue = "unavailable_order_paid"
        elif delivered_late and expected_late_sellers:
            expected_issue = "late_delivery_seller"
        elif delivered_late:
            expected_issue = "late_delivery_logistics"
        elif len(payment_rows) >= 2 and reconciled is True:
            expected_issue = "valid_split_payment"
        elif delivered and estimated and not delivered_late and reconciled is True:
            expected_issue = "unsupported_late_claim"
        else:
            expected_issue = None
            errors.append("source data does not match any policy")

        issue = output["case_assessment"]["primary_issue"]
        if issue != expected_issue:
            errors.append("primary issue does not match source policy")
        cause = output["root_cause_analysis"]["ranked_causes"][0]["cause_code"]
        if issue not in POLICY or cause != POLICY[issue]["cause"]:
            errors.append("primary issue and root cause mismatch")
        expected_evidence = [f"order:{order_id}"]
        expected_evidence.extend(f"item:{value}" for value in expected_items)
        expected_evidence.extend(f"payment:{value}" for value in expected_payments)
        if issue == "late_delivery_seller":
            expected_evidence.extend(
                f"seller:{value}"
                for value in expected_late_sellers
            )
        expected_evidence.append(f"policy:{cause}")
        if output["evidence_ids"] != expected_evidence[:20]:
            errors.append("evidence is incomplete, invalid, or out of order")

        if issue == "late_delivery_seller":
            expected_parties = [
                {"party_type": "seller", "party_id": value}
                for value in expected_late_sellers
            ]
        elif issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_parties = [
                {"party_type": "platform", "party_id": "OLIST_PLATFORM"}
            ]
        elif issue == "late_delivery_logistics":
            expected_parties = [
                {
                    "party_type": "logistics_provider",
                    "party_id": "LOGISTICS_PROVIDER",
                }
            ]
        else:
            expected_parties = []
        if output["root_cause_analysis"]["responsible_parties"] != expected_parties:
            errors.append("responsible parties mismatch")
        if issue in {"canceled_order_paid", "unavailable_order_paid"}:
            expected_refund = money(payment_total)
        elif issue in {"late_delivery_seller", "late_delivery_logistics"}:
            expected_refund = money(freight_total)
        else:
            expected_refund = 0.0
        if refund != expected_refund:
            errors.append("recommended refund mismatch")

        actions = [POLICY[issue]["action"]]
        if issue == "late_delivery_seller":
            actions.append("review_seller_handoff")
        elif issue == "late_delivery_logistics":
            actions.append("review_carrier_delay")
        if refund > 0:
            actions.append("verify_refund_completion")
        if len(expected_sellers) >= 2:
            actions.append("coordinate_multi_seller_case")
        if len(payment_rows) >= 2 and issue != "valid_split_payment":
            actions.append("verify_payment_allocation")
        if output["resolution_actions"] != actions[:5]:
            errors.append("resolution actions mismatch")
        if errors:
            raise ValueError(f"Verification failed for {case['case_id']}: {errors}")

    @classmethod
    def _has_non_finite_number(cls, value: object) -> bool:
        if isinstance(value, float):
            return not math.isfinite(value)
        if isinstance(value, dict):
            return any(cls._has_non_finite_number(item) for item in value.values())
        if isinstance(value, list):
            return any(cls._has_non_finite_number(item) for item in value)
        return False
