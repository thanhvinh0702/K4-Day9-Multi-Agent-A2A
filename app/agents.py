from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Any

from app.data_store import OlistDataStore
from app.schemas import (
    AffectedEntities,
    CaseAssessment,
    CaseInput,
    CaseOutput,
    CustomerContext,
    DeliveryAnalysis,
    FinancialResolution,
    PaymentReconciliation,
    ProductContext,
    RankedCause,
    ResponsibleParty,
    RootCauseAnalysis,
    SellerHandoff,
)


def money(value: float) -> float:
    return round(value + 0.0000001, 2)


def parse_money(value: str) -> float:
    return float(value or 0)


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def hours_between(later: str | None, earlier: str | None) -> float | None:
    later_dt = parse_ts(later)
    earlier_dt = parse_ts(earlier)
    if not later_dt or not earlier_dt:
        return None
    return round((later_dt - earlier_dt).total_seconds() / 3600, 2)


def stable_unique(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(v for v in values if v))


class CustomerAgent:
    def run(self, records: dict[str, Any], store: OlistDataStore) -> CustomerContext:
        customer = records["customer"]
        if not customer:
            return CustomerContext(customer_unique_id=None, related_order_ids=[])
        unique_id = customer["customer_unique_id"]
        current_order_id = records["order"]["order_id"]
        related = [
            order_id
            for order_id in store.orders_by_customer_unique_id.get(unique_id, [])
            if order_id != current_order_id
        ][:5]
        return CustomerContext(customer_unique_id=unique_id, related_order_ids=related)


class OrderProductAgent:
    def run(self, records: dict[str, Any]) -> ProductContext:
        items = records["items"]
        products = records["products"]
        product_ids = stable_unique([row["product_id"] for row in items])[:5]
        categories = stable_unique([row.get("product_category_name", "") for row in products])[:5]
        return ProductContext(product_ids=product_ids, category_names=categories)


class PaymentAgent:
    def run(self, records: dict[str, Any]) -> PaymentReconciliation:
        items = records["items"]
        payments = records["payments"]
        payment_total = money(sum(parse_money(row["payment_value"]) for row in payments))
        payment_types = stable_unique([row["payment_type"] for row in payments])

        if not items:
            return PaymentReconciliation(
                item_total_brl=None,
                freight_total_brl=None,
                expected_total_brl=None,
                payment_total_brl=payment_total,
                difference_brl=None,
                reconciled=None,
                payment_types=payment_types,
            )

        item_total = money(sum(parse_money(row["price"]) for row in items))
        freight_total = money(sum(parse_money(row["freight_value"]) for row in items))
        expected_total = money(item_total + freight_total)
        difference = money(payment_total - expected_total)
        return PaymentReconciliation(
            item_total_brl=item_total,
            freight_total_brl=freight_total,
            expected_total_brl=expected_total,
            payment_total_brl=payment_total,
            difference_brl=difference,
            reconciled=abs(difference) <= 0.10,
            payment_types=payment_types,
        )


class DeliveryAgent:
    def run(self, records: dict[str, Any]) -> DeliveryAnalysis:
        order = records["order"]
        carrier_at = order.get("order_delivered_carrier_date") or None
        delivered_at = order.get("order_delivered_customer_date") or None
        estimated_at = order.get("order_estimated_delivery_date") or None

        by_seller: OrderedDict[str, list[str]] = OrderedDict()
        for item in records["items"]:
            by_seller.setdefault(item["seller_id"], []).append(item.get("shipping_limit_date") or "")

        handoffs: list[SellerHandoff] = []
        late_sellers: list[str] = []
        for seller_id, limits in by_seller.items():
            valid_limits = [limit for limit in limits if limit]
            shipping_limit_at = min(valid_limits) if valid_limits else None
            variance = hours_between(carrier_at, shipping_limit_at)
            late = bool(variance is not None and variance > 0)
            if late:
                late_sellers.append(seller_id)
            handoffs.append(
                SellerHandoff(
                    seller_id=seller_id,
                    shipping_limit_at=shipping_limit_at,
                    handoff_variance_hours=variance,
                    late_handoff=late,
                )
            )

        return DeliveryAnalysis(
            delivered_at=delivered_at,
            estimated_delivery_at=estimated_at,
            carrier_handoff_at=carrier_at,
            delivery_variance_hours=hours_between(delivered_at, estimated_at),
            seller_handoff_analysis=handoffs,
            late_handoff_seller_ids=late_sellers,
        )


class PolicyAgent:
    def run(
        self,
        records: dict[str, Any],
        customer_context: CustomerContext,
        product_context: ProductContext,
        delivery: DeliveryAnalysis,
        payment: PaymentReconciliation,
    ) -> dict[str, Any]:
        order = records["order"]
        items = records["items"]
        payments = records["payments"]
        seller_ids = stable_unique([row["seller_id"] for row in items])
        category_names = product_context.category_names

        secondary = []
        if len(items) >= 2:
            secondary.append("multi_item_order")
        if len(seller_ids) >= 2:
            secondary.append("multi_seller_order")
        if len(payments) >= 2:
            secondary.append("split_payment")
        if customer_context.related_order_ids:
            secondary.append("repeat_customer")
        if len(category_names) >= 2:
            secondary.append("multiple_categories")

        status = order["order_status"]
        payment_total = payment.payment_total_brl
        delivery_late = bool(delivery.delivery_variance_hours is not None and delivery.delivery_variance_hours > 0)
        has_late_seller = bool(delivery.late_handoff_seller_ids)
        reconciled = payment.reconciled

        if status == "canceled" and payment_total > 0:
            primary = "canceled_order_paid"
            cause = "ORDER_CANCELED_AFTER_PAYMENT"
            parties = [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")]
            refund = payment_total
            action = "issue_full_refund"
            confidence = 0.98
        elif status == "unavailable" and payment_total > 0:
            primary = "unavailable_order_paid"
            cause = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
            parties = [ResponsibleParty(party_type="platform", party_id="OLIST_PLATFORM")]
            refund = payment_total
            action = "issue_full_refund"
            confidence = 0.98
        elif delivery_late and has_late_seller:
            primary = "late_delivery_seller"
            cause = "SELLER_HANDOFF_AFTER_LIMIT"
            parties = [
                ResponsibleParty(party_type="seller", party_id=seller_id)
                for seller_id in delivery.late_handoff_seller_ids[:3]
            ]
            refund = payment.freight_total_brl or 0
            action = "refund_freight"
            confidence = 0.94
        elif delivery_late:
            primary = "late_delivery_logistics"
            cause = "CARRIER_DELIVERED_AFTER_ESTIMATE"
            parties = [ResponsibleParty(party_type="logistics_provider", party_id="LOGISTICS_PROVIDER")]
            refund = payment.freight_total_brl or 0
            action = "refund_freight"
            confidence = 0.92
        elif len(payments) >= 2 and reconciled is True:
            primary = "valid_split_payment"
            cause = "MULTIPLE_PAYMENTS_RECONCILED"
            parties = []
            refund = 0
            action = "explain_valid_split_payment"
            confidence = 0.90
        else:
            primary = "unsupported_late_claim"
            cause = "DELIVERY_WITHIN_ESTIMATE"
            parties = []
            refund = 0
            action = "reject_late_refund"
            confidence = 0.86 if reconciled is not False else 0.76

        actions = [action]
        if primary == "late_delivery_seller":
            actions.append("review_seller_handoff")
        if primary == "late_delivery_logistics":
            actions.append("review_carrier_delay")
        if refund > 0:
            actions.append("verify_refund_completion")
        if "multi_seller_order" in secondary:
            actions.append("coordinate_multi_seller_case")
        if "split_payment" in secondary and primary != "valid_split_payment":
            actions.append("verify_payment_allocation")

        return {
            "assessment": CaseAssessment(
                primary_issue=primary,
                secondary_issues=secondary,
                case_status="action_required" if refund > 0 else "no_action",
                confidence=confidence,
            ),
            "root": RootCauseAnalysis(
                ranked_causes=[RankedCause(cause_code=cause, rank=1)],
                responsible_parties=parties,
            ),
            "refund": money(refund),
            "actions": actions[:5],
        }


class VerifierAgent:
    def run(
        self,
        case: CaseInput,
        records: dict[str, Any],
        customer_context: CustomerContext,
        product_context: ProductContext,
        delivery: DeliveryAnalysis,
        payment: PaymentReconciliation,
        policy: dict[str, Any],
    ) -> CaseOutput:
        order_id = records["order"]["order_id"]
        items = records["items"]
        payments = records["payments"]
        seller_ids = stable_unique([row["seller_id"] for row in items])
        responsible_sellers = [
            party.party_id
            for party in policy["root"].responsible_parties
            if party.party_type == "seller"
        ]
        affected_sellers = responsible_sellers or seller_ids
        item_ids = [f"{order_id}:{row['order_item_id']}" for row in items]
        payment_ids = [f"{order_id}:{row['payment_sequential']}" for row in payments]

        evidence = [f"order:{order_id}"]
        evidence.extend(f"item:{item_id}" for item_id in item_ids)
        evidence.extend(f"payment:{payment_id}" for payment_id in payment_ids)
        evidence.extend(f"seller:{seller_id}" for seller_id in responsible_sellers[:3])
        evidence.extend(f"policy:{cause.cause_code}" for cause in policy["root"].ranked_causes)

        return CaseOutput(
            case_id=case.case_id,
            case_assessment=policy["assessment"],
            affected_entities=AffectedEntities(
                order_ids=[order_id],
                item_ids=item_ids[:5],
                seller_ids=affected_sellers[:3],
                payment_ids=payment_ids[:5],
            ),
            customer_context=customer_context,
            product_context=product_context,
            delivery_analysis=delivery,
            payment_reconciliation=payment,
            root_cause_analysis=policy["root"],
            evidence_ids=evidence[:20],
            financial_resolution=FinancialResolution(recommended_refund_brl=policy["refund"]),
            resolution_actions=policy["actions"],
        )
