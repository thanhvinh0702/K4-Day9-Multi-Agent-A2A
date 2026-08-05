"""Deterministic domain calculations.

Every number that ends up in the final output must be produced here, not
invented by an LLM. Domain agents and the policy engine both call these same
functions so there is only one implementation of each formula (README.md
section 4).
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from langchain_core.tools import tool

from .data_layer import get_data


def _ts_to_str(ts) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _hours_diff(a, b) -> float | None:
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return round((a - b).total_seconds() / 3600, 2)


def build_customer_context(claimed_order_id: str) -> dict[str, Any]:
    data = get_data()
    order = data.get_order(claimed_order_id)
    if order is None:
        raise ValueError(f"Unknown order_id: {claimed_order_id}")
    customer = data.get_customer(order["customer_id"])
    cuid = customer["customer_unique_id"] if customer else None
    related = data.get_related_order_ids(cuid, claimed_order_id, limit=5) if cuid else []
    return {"customer_unique_id": cuid, "related_order_ids": related}


def build_order_product_context(claimed_order_id: str) -> dict[str, Any]:
    data = get_data()
    items = data.get_items(claimed_order_id)

    item_ids = [f"{claimed_order_id}:{it['order_item_id']}" for it in items]

    seller_ids_all: list[str] = []
    for it in items:
        if it["seller_id"] not in seller_ids_all:
            seller_ids_all.append(it["seller_id"])

    product_ids_all: list[str] = []
    for it in items:
        if it["product_id"] not in product_ids_all:
            product_ids_all.append(it["product_id"])

    category_names: list[str] = []
    for pid in product_ids_all:
        prod = data.get_product(pid)
        cat = data.category_name_english(prod["product_category_name"]) if prod else None
        if cat and cat not in category_names:
            category_names.append(cat)

    return {
        "order_ids": [claimed_order_id],
        "item_ids": item_ids[:5],
        "seller_ids": seller_ids_all[:3],
        "product_ids": product_ids_all[:5],
        "category_names": category_names[:5],
        # unlimited, for internal policy calc only (not part of output schema)
        "all_seller_ids": seller_ids_all,
        "item_count": len(items),
    }


def build_payment_reconciliation(claimed_order_id: str) -> dict[str, Any]:
    data = get_data()
    items = data.get_items(claimed_order_id)
    payments = data.get_payments(claimed_order_id)

    item_total = round(sum(it["price"] for it in items), 2)
    freight_total = round(sum(it["freight_value"] for it in items), 2)
    payment_total = round(sum(p["payment_value"] for p in payments), 2)

    payment_ids = [f"{claimed_order_id}:{p['payment_sequential']}" for p in payments]

    payment_types: list[str] = []
    for p in payments:
        if p["payment_type"] not in payment_types:
            payment_types.append(p["payment_type"])

    if len(items) == 0:
        expected_total = None
        difference = None
        reconciled = None
    else:
        expected_total = round(item_total + freight_total, 2)
        difference = round(payment_total - expected_total, 2)
        reconciled = abs(difference) <= 0.10

    return {
        "payment_ids": payment_ids[:5],
        "payment_count": len(payments),
        "payment_reconciliation": {
            "currency": "BRL",
            "item_total_brl": item_total,
            "freight_total_brl": freight_total,
            "expected_total_brl": expected_total,
            "payment_total_brl": payment_total,
            "difference_brl": difference,
            "reconciled": reconciled,
            "payment_types": payment_types,
        },
    }


def build_delivery_analysis(claimed_order_id: str) -> dict[str, Any]:
    data = get_data()
    order = data.get_order(claimed_order_id)
    if order is None:
        raise ValueError(f"Unknown order_id: {claimed_order_id}")
    items = data.get_items(claimed_order_id)

    delivered = order["order_delivered_customer_date"]
    estimated = order["order_estimated_delivery_date"]
    carrier_handoff = order["order_delivered_carrier_date"]
    delivery_variance = _hours_diff(delivered, estimated)

    per_seller_limits: dict[str, list] = {}
    for it in items:
        per_seller_limits.setdefault(it["seller_id"], []).append(it["shipping_limit_date"])

    seller_handoff_analysis = []
    late_handoff_seller_ids: list[str] = []
    for sid, limits in per_seller_limits.items():
        earliest_limit = min(limits)
        variance = _hours_diff(carrier_handoff, earliest_limit)
        late = bool(variance is not None and variance > 0)
        seller_handoff_analysis.append(
            {
                "seller_id": sid,
                "shipping_limit_at": _ts_to_str(earliest_limit),
                "handoff_variance_hours": variance,
                "late_handoff": late,
            }
        )
        if late:
            late_handoff_seller_ids.append(sid)

    return {
        "delivered_at": _ts_to_str(delivered),
        "estimated_delivery_at": _ts_to_str(estimated),
        "carrier_handoff_at": _ts_to_str(carrier_handoff),
        "delivery_variance_hours": delivery_variance,
        "seller_handoff_analysis": seller_handoff_analysis,
        "late_handoff_seller_ids": late_handoff_seller_ids,
    }


def gather_case_facts(claimed_order_id: str) -> dict[str, Any]:
    """Single source of truth used by the policy engine (src/policy_rules.py)."""
    data = get_data()
    order = data.get_order(claimed_order_id)
    if order is None:
        raise ValueError(f"Unknown order_id: {claimed_order_id}")
    return {
        "order_id": claimed_order_id,
        "order_status": order["order_status"],
        "customer_context": build_customer_context(claimed_order_id),
        "order_product_context": build_order_product_context(claimed_order_id),
        **build_payment_reconciliation(claimed_order_id),
        "delivery_analysis": build_delivery_analysis(claimed_order_id),
    }


# ---- LangChain tool wrappers (bound to the LLM domain agents) -------------


@tool
def get_customer_context(claimed_order_id: str) -> dict:
    """Return customer_unique_id and up to 5 related_order_ids for the given order_id."""
    return build_customer_context(claimed_order_id)


@tool
def get_order_product_context(claimed_order_id: str) -> dict:
    """Return affected order/item/seller/product ids and category names for the given order_id."""
    ctx = build_order_product_context(claimed_order_id)
    return {k: v for k, v in ctx.items() if k not in ("all_seller_ids", "item_count")}


@tool
def get_payment_reconciliation(claimed_order_id: str) -> dict:
    """Return payment ids and the item/freight/payment reconciliation for the given order_id."""
    ctx = build_payment_reconciliation(claimed_order_id)
    return {k: v for k, v in ctx.items() if k != "payment_count"}


@tool
def get_delivery_analysis(claimed_order_id: str) -> dict:
    """Return delivery variance and per-seller handoff variance for the given order_id."""
    return build_delivery_analysis(claimed_order_id)
